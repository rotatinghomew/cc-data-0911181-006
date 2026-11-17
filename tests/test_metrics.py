from pathlib import Path
import unittest

from app.domain import course_statistics
from app.metrics import Scope, parse_scope, scope_metrics
from app.storage import DataError, Store
from app.service import dispatch

DATA = Path(__file__).parents[1] / 'data'


class ScopeMetricTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(DATA)

    def test_people_are_distinct_inside_scope(self):
        doc = scope_metrics(self.store, Scope())
        total = doc['total']
        # 40 registrations belong to only 17 learners; the scope count is
        # learner-deduped rather than a join row count.
        self.assertEqual(total['registered_people'], 17)
        self.assertEqual(total['participant_people'], 17)
        self.assertEqual(len(self.store.table('registrations')), 40)

    def test_completion_fraction_is_learner_level_not_class_average(self):
        doc = scope_metrics(self.store, Scope())
        fractions = [course_statistics(self.store, course)['completion_fraction']
                     for course in doc['basis']['course_ids']]
        class_average = sum(fractions) / len(fractions)
        self.assertNotAlmostEqual(
            doc['total']['learner_completion_fraction'], class_average)
        self.assertEqual(
            doc['total']['learner_completion_fraction'],
            doc['total']['completed_people'] / doc['total']['eligible_people'])

    def test_attendance_events_accumulate_but_people_do_not(self):
        grouped = scope_metrics(self.store, Scope(group_by='direction'))
        self.assertGreater(
            sum(g['metrics']['attendance_events'] for g in grouped['groups']),
            grouped['total']['attendance_events'])
        self.assertGreater(
            sum(g['metrics']['registered_people'] for g in grouped['groups']),
            grouped['total']['registered_people'])
        self.assertFalse(grouped['additivity']['person_metrics_additive'])
        self.assertTrue(grouped['additivity']['attendance_events_additive'])

    def test_multi_direction_overlap_is_explained(self):
        doc = scope_metrics(self.store, Scope(directions=['photo'],
                                              group_by='direction'))
        # C0 carries both photo and digital, so its learners repeat across
        # groups; the overlap block names them instead of forcing sums.
        self.assertEqual(doc['overlap']['courses_in_multiple_groups'],
                         {'C0': ['digital', 'photo']})
        self.assertTrue(doc['overlap']['learners_in_multiple_groups'])
        for learner, groups in doc['overlap']['learners_in_multiple_groups'].items():
            self.assertEqual(sorted(groups), ['digital', 'photo'])

    def test_filters_share_one_query_and_basis(self):
        doc = scope_metrics(self.store, Scope(directions=['digital'],
                                              campuses=['west'],
                                              terms=['2026-autumn']))
        self.assertEqual(doc['basis']['course_ids'], ['C0', 'C2'])
        self.assertEqual(doc['basis']['term_status'], {'2026-autumn': 'active'})
        self.assertEqual(doc['basis']['caliber_version'], 'learner-scope-v1')
        self.assertEqual(doc['basis']['dataset_fingerprint'],
                         self.store.fingerprint())

    def test_detail_drilldown_lists_learners_and_courses(self):
        doc = scope_metrics(self.store, Scope(detail=True))
        self.assertIn('learners_completed', doc['total']['detail'])
        self.assertEqual(set(doc['total']['detail']['learners_eligible']),
                         set(doc['total']['detail']['learners_registered']))
        self.assertEqual(sorted(doc['course_detail']),
                         doc['basis']['course_ids'])

    def test_total_switch_hides_total_but_keeps_groups(self):
        doc = scope_metrics(self.store, Scope(group_by='campus', total=False))
        self.assertNotIn('total', doc)
        self.assertTrue(doc['groups'])

    def test_query_validation(self):
        for query in (
            {'directions': ['photo', 'digital']},
            {'directions': ['']},
            {'group_by': ['weekday']},
            {'detail': ['maybe']},
        ):
            with self.assertRaises(DataError):
                scope_metrics(self.store, parse_scope(query))
        with self.assertRaises(DataError):
            scope_metrics(self.store, parse_scope({'directions': ['unknown']}))

    def test_empty_scope_returns_zero_denominator_as_none(self):
        # art only runs in autumn, so intersecting with spring matches nothing
        empty = scope_metrics(
            self.store, Scope(directions=['art'], terms=['2026-spring']))
        self.assertEqual(empty['basis']['course_ids'], [])
        self.assertEqual(empty['total']['eligible_people'], 0)
        self.assertIsNone(empty['total']['learner_completion_fraction'])
        self.assertEqual(empty['total']['attendance_events'], 0)

    def test_metrics_route_available_through_dispatch(self):
        doc = dispatch(self.store, '/api/metrics',
                       {'directions': ['photo'], 'group_by': ['direction']})
        self.assertEqual(doc['scope'], 'learner_deduped_scope')
        self.assertTrue(doc['groups'])
