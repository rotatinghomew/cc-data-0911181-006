import json
from pathlib import Path
import shutil
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import threading

from app import deliveries, followups, subscriptions, targets
from app.journal import Journal
from app.service import make_server
from app.storage import DataError, Store

DATA = Path(__file__).parents[1] / 'data'


class ScopeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(DATA)
        self.journal = Journal()

    def tearDown(self):
        self.journal.close()

    def save(self, name, **filters):
        return subscriptions.save(self.store, self.journal, dict(
            view=name, recipient='teaching-office', cadence='weekly', **filters))

    def test_saved_view_is_distinct_from_temporary_drilldown(self):
        view = self.save('v1', terms=['2026-spring'], group_by='campus')
        self.assertEqual(view['filters']['group_by'], 'campus')
        # ad-hoc drilldown goes through read-only metrics and creates no view
        from app.metrics import scope_metrics, Scope
        scope_metrics(self.store, Scope(terms=['2026-spring'], detail=True))
        self.assertEqual([row['view'] for row in subscriptions.list_views(self.journal)],
                         ['v1'])

    def test_no_reminder_without_eligible_denominator_or_when_target_met(self):
        self.save('whole')
        assessment = targets.evaluate_scope(
            self.store, self.journal, {'assessment': 'a-ok', 'view': 'whole'})
        self.assertFalse(assessment['below_target'])
        self.assertEqual(assessment['affected_people'], [])
        with self.assertRaises(DataError):
            followups.assign_scope(self.store, self.journal,
                                   {'assessment': 'a-ok'})

    def test_below_target_scope_follows_learner_caliber(self):
        self.save('spring', terms=['2026-spring'])
        assessment = targets.evaluate_scope(
            self.store, self.journal, {'assessment': 'a-spring', 'view': 'spring'})
        self.assertTrue(assessment['below_target'])
        # affected people are eligible-but-not-completed learners, each once
        self.assertEqual(assessment['affected_people'],
                         sorted(set(assessment['affected_people'])))
        cases = followups.assign_scope(
            self.store, self.journal, {'assessment': 'a-spring'})['followups']
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]['owner'], 'north')

    def test_problem_identity_survives_regrouping_and_close(self):
        self.save('p1', terms=['2026-spring'])
        self.save('p2', terms=['2026-spring'], group_by='campus')
        a1 = targets.evaluate_scope(
            self.store, self.journal, {'assessment': 'a1', 'view': 'p1'})
        a2 = targets.evaluate_scope(
            self.store, self.journal, {'assessment': 'a2', 'view': 'p2'})
        self.assertEqual(a1['problem_key'], a2['problem_key'])
        followups.assign_scope(self.store, self.journal, {'assessment': 'a1'})
        followups.close(self.store, self.journal,
                        {'case': a1['problem_key'] + ':north', 'owner': 'north'})
        # reassigning through the regrouped assessment must not reopen or dup
        again = followups.assign_scope(
            self.store, self.journal, {'assessment': 'a2'})['followups']
        self.assertEqual(len(again), 1)
        self.assertEqual(again[0]['status'], 'closed')

    def test_cross_campus_scope_is_shared_not_full_responsibility(self):
        self.save('joint', campuses=['east', 'west'], group_by='campus')
        assessment = targets.evaluate_scope(
            self.store, self.journal, {'assessment': 'aj', 'view': 'joint'})
        self.assertTrue(assessment['below_target'])
        result = followups.assign_scope(
            self.store, self.journal, {'assessment': 'aj'})
        owners = {case['owner']: case for case in result['followups']}
        self.assertEqual(sorted(owners), ['east', 'west'])
        for case in owners.values():
            self.assertEqual(case['responsibility'], 'shared')
            self.assertNotEqual(set(case['scope_courses']),
                                set(assessment['basis']['basis']['course_ids']))
        # idempotent: second assignment creates no extra cases
        second = followups.assign_scope(
            self.store, self.journal, {'assessment': 'aj'})
        self.assertEqual(second['followups'], result['followups'])

    def test_delivery_keeps_frozen_basis_and_pending_only(self):
        self.save('spring', terms=['2026-spring'])
        assessment = targets.evaluate_scope(
            self.store, self.journal, {'assessment': 'ad', 'view': 'spring'})
        followups.assign_scope(self.store, self.journal, {'assessment': 'ad'})
        delivery = deliveries.prepare_scope(
            self.store, self.journal, {'assessment': 'ad', 'delivery': 'd1'})
        self.assertTrue(delivery['basis_current'])
        # term is closed, so the problem no longer goes out as pending
        self.assertEqual(delivery['closed_terms'], ['2026-spring'])
        self.assertFalse(delivery['problem_still_valid'])
        self.assertEqual(delivery['pending_followups'], [])
        self.assertIn('frozen_basis', delivery)

    def test_stale_basis_is_flagged_after_data_changes(self):
        self.save('spring', terms=['2026-spring'])
        targets.evaluate_scope(
            self.store, self.journal, {'assessment': 'as', 'view': 'spring'})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'data'
            shutil.copytree(DATA, root)
            path = root / 'registrations.json'
            rows = json.loads(path.read_text())
            rows[0]['eligible'] = not rows[0]['eligible']
            path.write_text(json.dumps(rows))
            changed = Store(root)
            delivery = deliveries.prepare_scope(
                changed, self.journal,
                {'assessment': 'as', 'delivery': 'd2'})
            self.assertFalse(delivery['basis_current'])
            self.assertIn('frozen basis', delivery['basis_note'])

    def test_saved_view_validation(self):
        for bad in (
            {'view': 'bad', 'recipient': 'r', 'cadence': 'weekly',
             'directions': ['nope']},
            {'view': 'bad', 'recipient': 'r', 'cadence': 'daily'},
            {'view': 'bad', 'recipient': '', 'cadence': 'weekly'},
            {'view': 'bad', 'recipient': 'r', 'cadence': 'weekly',
             'directions': ['art', 'art']},
        ):
            with self.assertRaises(DataError):
                subscriptions.save(self.store, self.journal, bad)
        self.save('once')
        with self.assertRaises(DataError):
            self.save('once')


class ScopeHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store(DATA)
        cls.server = make_server(cls.store)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def post(self, operation, payload):
        request = Request(self.base + '/api/workflow/' + operation,
                          data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json'},
                          method='POST')
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_metrics_route_and_workflow_over_http(self):
        with urlopen(self.base + '/api/metrics?directions=photo&group_by=direction',
                     timeout=5) as response:
            self.assertEqual(response.status, 200)
            doc = json.load(response)
        self.assertTrue(doc['groups'])
        status, _ = self.post('views.save',
                              {'view': 'http-v', 'recipient': 'ro',
                               'cadence': 'weekly', 'terms': ['2026-spring']})
        self.assertEqual(status, 200)
        status, body = self.post('targets.evaluate_scope',
                                 {'assessment': 'http-a', 'view': 'http-v'})
        self.assertEqual(status, 200)
        self.assertTrue(body['below_target'])
        status, body = self.post('targets.evaluate_scope',
                                 {'assessment': 'x', 'view': 'missing'})
        self.assertEqual(status, 400)
