from hashlib import sha256

from .domain import course_statistics
from .metrics import (_facts, _person_sets, saved_scope, scope_metrics,
                      target_threshold)
from .subscriptions import load as load_view

ASSESSMENT_KIND = 'scope_target_assessment'


def evaluate(store,journal,payload):
    view=store.find('views',view=payload['view'])
    stats=course_statistics(store,view['course'])
    target=store.find('course_targets',course=view['course'])
    rate=stats['completion_fraction']
    row=dict(assessment=payload['assessment'],view=view['view'],course=view['course'],
             below_target=rate is not None and rate<target['minimum'],basis=stats)
    with journal.transaction():
        return journal.put('target_assessment',row['assessment'],row)


def problem_key(filters):
    """Stable identity of a problem across regroupings.

    Display choices (group_by, detail, total) are deliberately excluded so the
    same people under a different grouping keep the same problem and never
    generate a second reminder.
    """
    encoded = repr((tuple(sorted(filters.get('directions', []))),
                    tuple(sorted(filters.get('campuses', []))),
                    tuple(sorted(filters.get('terms', [])))))
    return 'scope-' + sha256(encoded.encode()).hexdigest()[:16]


def evaluate_scope(store, journal, payload):
    """Judge the completion target for a saved subscription view's scope."""
    view_row = load_view(journal, payload['view'])
    scope = saved_scope(view_row['filters'])
    document = scope_metrics(store, scope)
    course_ids = document['basis']['course_ids']
    minimum = target_threshold(store, course_ids)
    fraction = document['total']['learner_completion_fraction']
    # Without eligible people there is no completion-qualified denominator, so
    # no low-completion reminder can be triggered.
    below_target = fraction is not None and fraction < minimum
    affected = []
    if below_target:
        registrations, by_registration, _visits, completed_rows, _courses = _facts(
            store, set(course_ids))
        _registered, eligible, completed = _person_sets(
            registrations, by_registration, completed_rows)
        affected = sorted(eligible - completed)
    key = problem_key(view_row['filters'])
    row = {
        'assessment': payload['assessment'],
        'view': view_row['view'],
        'problem_key': key,
        'below_target': below_target,
        'minimum': minimum,
        'basis': document,
        'affected_people': affected,
    }
    with journal.transaction():
        return journal.put(ASSESSMENT_KIND, row['assessment'], row)
