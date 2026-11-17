from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from app.analysis import ROUTES
from app.reporting import report
from app.service import dispatch, make_server
from app.storage import DataError, Store, integer, single

DATA = Path(__file__).parents[1] / 'data'


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(DATA)

    def test_every_table_has_data(self):
        self.assertTrue(all(count > 0 for count in self.store.inventory().values()))

    def test_isolated_reads(self):
        name = next(iter(self.store.schema))
        rows = self.store.table(name)
        rows[0]['accidental_edit'] = True
        self.assertNotIn('accidental_edit', self.store.table(name)[0])

    def test_stable_fingerprint(self):
        self.assertEqual(self.store.fingerprint(), Store(DATA).fingerprint())
        self.assertEqual(len(self.store.fingerprint()), 64)

    def test_duplicate_primary_key_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'data'
            shutil.copytree(DATA, target)
            name = next(iter(self.store.schema))
            path = target / (name + '.json')
            rows = json.loads(path.read_text())
            rows.append(deepcopy(rows[0]))
            path.write_text(json.dumps(rows))
            with self.assertRaises(DataError):
                Store(target)

    def test_missing_required_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'data'
            shutil.copytree(DATA, target)
            name, contract = next(iter(self.store.schema.items()))
            path = target / (name + '.json')
            rows = json.loads(path.read_text())
            del rows[0][contract['required'][0]]
            path.write_text(json.dumps(rows))
            with self.assertRaises(DataError):
                Store(target)

    def test_query_boundaries(self):
        self.assertEqual(integer({}, 'limit', 5), 5)
        for query in [{'limit': ['x']}, {'limit': ['-1']}, {'limit': ['1', '2']}]:
            with self.assertRaises(DataError):
                integer(query, 'limit', 5)


class IntegrationTests(unittest.TestCase):
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

    def test_health_and_routes_over_http(self):
        for path in ['/health', *ROUTES]:
            with self.subTest(path=path), urlopen(self.base + path, timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertIn('application/json', response.headers['Content-Type'])
                self.assertIsInstance(json.load(response), dict)

    def test_unknown_route(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.base + '/does-not-exist', timeout=3)
        self.assertEqual(caught.exception.code, 404)

    def test_bad_table(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.base + '/api/records?table=unknown', timeout=3)
        self.assertEqual(caught.exception.code, 400)

    def test_report_uses_same_analysis(self):
        result = report(self.store)
        self.assertEqual(result['dataset_fingerprint'], self.store.fingerprint())
        for path in ROUTES:
            self.assertEqual(result['sections'][path], dispatch(self.store, path, {}))


from app.domain import course_statistics


class MetricTests(unittest.TestCase):
    def test_course_count_is_distinct_learner(self):
        store=Store(DATA)
        row=course_statistics(store,'C0')
        expected={registration['learner'] for registration in store.select('registrations',course='C0')}
        self.assertEqual(row['registered_people'],len(expected))

    def test_completion_denominator_uses_eligibility(self):
        row=course_statistics(Store(DATA),'C1')
        self.assertEqual(row['eligible_registrations'],8)
        self.assertAlmostEqual(row['completion_fraction'],row['completed_registrations']/8)

    def test_subscription_and_live_share_course_definition(self):
        store=Store(DATA)
        output=report(store)['sections']['/api/subscriptions']['deliveries'][0]
        live=dispatch(store,'/api/statistics',{'course':['C1']})['courses'][0]
        self.assertEqual(output['body'],live)

    def test_event_and_person_counts_are_different_units(self):
        row=course_statistics(Store(DATA),'C2')
        self.assertGreater(row['attendance_events'],row['registered_people'])
