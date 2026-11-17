"""Reusable metric calibers over direction/campus/term scopes.

Caliber rules shared by the multidimensional view, target judgment and
follow-up handoff (see docs/数据契约.md):

* person metrics are distinct learners: a learner is counted once inside the
  selected scope even when courses belong to several directions/campuses or the
  learner studies across classes;
* attendance_events is an additive visit unit, never a person count;
* the learner completion fraction divides distinct learners who completed at
  least one eligible course by distinct learners holding completion
  eligibility inside the scope. Per-class fractions are never averaged;
* group subtotals therefore do not necessarily add up to the total. The overlap
  block explains which learners appear in several groups and why.
"""
from .storage import DataError, single

CALIBER_VERSION = 'learner-scope-v1'
GROUP_DIMENSIONS = ('direction', 'campus', 'term', 'course')
TERM_STATUSES = ('active', 'closed')


def multi(query, name):
    """Parse one comma-separated query parameter into a list.

    Repeated parameters and empty members are invalid, matching the existing
    single-value parameter contract.
    """
    raw = single(query, name, None)
    if raw is None:
        return None
    values = [part.strip() for part in raw.split(',')]
    if not values or any(value == '' for value in values):
        raise DataError('one nonempty value required: ' + name)
    if len(set(values)) != len(values):
        raise DataError('duplicate filter value: ' + name)
    return values


class Scope:
    def __init__(self, directions=None, campuses=None, terms=None,
                 group_by=None, detail=False, total=True):
        self.directions = list(directions or [])
        self.campuses = list(campuses or [])
        self.terms = list(terms or [])
        self.group_by = group_by
        self.detail = detail
        self.total = total

    def filters(self):
        return {'directions': self.directions, 'campuses': self.campuses,
                'terms': self.terms, 'group_by': self.group_by,
                'detail': self.detail, 'total': self.total}


def parse_scope(query):
    group_by = single(query, 'group_by', None)
    if group_by is not None and group_by not in GROUP_DIMENSIONS:
        raise DataError('unsupported group_by: ' + group_by)
    detail = single(query, 'detail', 'false')
    if detail not in ('true', 'false'):
        raise DataError('detail must be true or false')
    show_total = single(query, 'total', 'true')
    if show_total not in ('true', 'false'):
        raise DataError('total must be true or false')
    return Scope(multi(query, 'directions'), multi(query, 'campuses'),
                 multi(query, 'terms'), group_by, detail == 'true',
                 show_total == 'true')


def saved_scope(filters):
    """Rebuild a Scope from a persisted subscription definition."""
    return Scope(filters.get('directions'), filters.get('campuses'),
                 filters.get('terms'), filters.get('group_by'),
                 bool(filters.get('detail', False)),
                 bool(filters.get('total', True)))


def _known(store, field):
    values = set()
    for course in store.table('courses'):
        values.update(course[field])
    return values


def _check_filters(store, scope):
    allowed = {'directions': _known(store, 'directions'),
               'campuses': _known(store, 'campuses'),
               'terms': {row['term'] for row in store.table('courses')}}
    for field, picked in (('directions', scope.directions),
                          ('campuses', scope.campuses),
                          ('terms', scope.terms)):
        unknown = sorted(set(picked) - allowed[field])
        if unknown:
            raise DataError('unknown ' + field.rstrip('s') + ': ' + ','.join(unknown))


def term_status_table(store):
    rows = store.table('term_status')
    statuses = {row['term']: row['status'] for row in rows}
    for term in {row['term'] for row in store.table('courses')}:
        if term not in statuses:
            raise DataError('missing term_status for term: ' + term)
        if statuses[term] not in TERM_STATUSES:
            raise DataError('invalid term status for term: ' + term)
    return statuses


def select_courses(store, scope):
    def matches(course):
        if scope.directions and not set(course['directions']) & set(scope.directions):
            return False
        if scope.campuses and not set(course['campuses']) & set(scope.campuses):
            return False
        if scope.terms and course['term'] not in scope.terms:
            return False
        return True
    return [row['course'] for row in store.table('courses') if matches(row)]


def _facts(store, course_ids):
    """Build the registration/visit/completion facts inside the scope."""
    registrations = [row for row in store.table('registrations')
                     if row['course'] in course_ids]
    by_registration = {row['registration']: row for row in registrations}
    visits = [row for row in store.table('visits')
              if row['registration'] in by_registration]
    completed_rows = {row['registration']: row['completed']
                      for row in store.table('completions')
                      if row['registration'] in by_registration}
    courses = {row['course']: row for row in store.table('courses')
               if row['course'] in course_ids}
    return registrations, by_registration, visits, completed_rows, courses


def _person_sets(registrations, by_registration, completed_rows):
    registered = {row['learner'] for row in registrations}
    eligible = {row['learner'] for row in registrations if row['eligible']}
    completed = set()
    for registration_id, row in by_registration.items():
        if row['eligible'] and completed_rows.get(registration_id):
            completed.add(row['learner'])
    return registered, eligible, completed


def _metric_block(registered, participants, eligible, completed, events, detail=None):
    block = {
        'registered_people': len(registered),
        'participant_people': len(participants),
        'attendance_events': events,
        'eligible_people': len(eligible),
        'completed_people': len(completed),
        'learner_completion_fraction':
            len(completed) / len(eligible) if eligible else None,
    }
    if detail is not None:
        block['detail'] = detail
    return block


def _group_values(course, dimension):
    if dimension == 'course':
        return [course['course']]
    if dimension == 'term':
        return [course['term']]
    return list(course[{'direction': 'directions', 'campus': 'campuses'}[dimension]])


def _course_detail(course_id, registrations, by_registration, visits, completed_rows):
    own = [row for row in registrations if row['course'] == course_id]
    present_events = sum(1 for row in visits
                         if row['registration'] in by_registration
                         and by_registration[row['registration']]['course'] == course_id
                         and row['present'])
    registered, eligible, completed = _person_sets(own, {
        row['registration']: row for row in own}, completed_rows)
    participants = {by_registration[row['registration']]['learner']
                    for row in visits if row['present']
                    and by_registration[row['registration']]['course'] == course_id}
    return _metric_block(registered, participants, eligible, completed,
                         present_events,
                         detail={'learners_registered': sorted(registered),
                                 'learners_eligible': sorted(eligible),
                                 'learners_completed': sorted(completed)})


def scope_metrics(store, scope):
    """Return the full reusable metric document for a Scope."""
    _check_filters(store, scope)
    statuses = term_status_table(store)
    course_ids = select_courses(store, scope)
    registrations, by_registration, visits, completed_rows, courses = _facts(
        store, set(course_ids))
    registered, eligible, completed = _person_sets(
        registrations, by_registration, completed_rows)
    participants = {by_registration[row['registration']]['learner']
                    for row in visits if row['present']}
    events = sum(1 for row in visits if row['present'])

    def learner_detail(sets):
        return {'learners_registered': sorted(sets[0]),
                'learners_participant': sorted(sets[1]),
                'learners_eligible': sorted(sets[2]),
                'learners_completed': sorted(sets[3])}

    detail = learner_detail((registered, participants, eligible, completed)) \
        if scope.detail else None
    total_block = _metric_block(registered, participants, eligible, completed,
                                events, detail)

    groups = []
    if scope.group_by is not None:
        memberships = []
        for row in registrations:
            course = courses[row['course']]
            for value in _group_values(course, scope.group_by):
                memberships.append((value, row['learner']))
        group_names = sorted({value for value, _ in memberships})
        for value in group_names:
            group_regs = [row for row in registrations
                          if value in _group_values(courses[row['course']],
                                                    scope.group_by)]
            group_reg_ids = {row['registration'] for row in group_regs}
            group_visits = [row for row in visits
                            if row['registration'] in group_reg_ids]
            g_registered, g_eligible, g_completed = _person_sets(
                group_regs, {row['registration']: row for row in group_regs},
                completed_rows)
            g_participants = {by_registration[row['registration']]['learner']
                              for row in group_visits if row['present']}
            g_events = sum(1 for row in group_visits if row['present'])
            g_detail = learner_detail(
                (g_registered, g_participants, g_eligible, g_completed)) \
                if scope.detail else None
            groups.append({
                'group_by': scope.group_by, 'group': value,
                'metrics': _metric_block(g_registered, g_participants,
                                         g_eligible, g_completed, g_events,
                                         g_detail),
            })
        # Overlap explanation: learners/courses appearing in more than one
        # group because of multi-direction or cross-campus attribution.
        learner_groups = {}
        for value, learner in memberships:
            learner_groups.setdefault(learner, set()).add(value)
        shared_learners = {learner: sorted(values)
                           for learner, values in sorted(learner_groups.items())
                           if len(values) > 1}
        shared_courses = {}
        if scope.group_by in ('direction', 'campus'):
            field = {'direction': 'directions', 'campus': 'campuses'}[scope.group_by]
            for course_id in course_ids:
                values = courses[course_id][field]
                if len(values) > 1:
                    shared_courses[course_id] = sorted(values)
        attendance_repeat = scope.group_by in ('direction', 'campus')
        overlap = {
            'learners_in_multiple_groups': shared_learners,
            'courses_in_multiple_groups': shared_courses,
            'note': 'group subtotals are distinct-learner counts inside each '
                    'group and must not be summed to the total',
            'attendance_events_additive_across_groups': attendance_repeat,
        }
        if attendance_repeat:
            overlap['attendance_note'] = (
                'a visit of a multi-attributed course is counted in every '
                'group containing that course; use the total for the scope value')
    else:
        overlap = {'learners_in_multiple_groups': {},
                   'courses_in_multiple_groups': {},
                   'note': 'no grouping requested',
                   'attendance_events_additive_across_groups': False}

    course_breakdown = None
    if scope.detail:
        course_breakdown = {course_id: _course_detail(
            course_id, registrations, by_registration, visits, completed_rows)
            for course_id in course_ids}

    basis = {
        'caliber_version': CALIBER_VERSION,
        'dataset_fingerprint': store.fingerprint(),
        'scope_filters': {'directions': scope.directions,
                          'campuses': scope.campuses, 'terms': scope.terms},
        'course_ids': course_ids,
        'term_status': {term: statuses[term]
                        for term in sorted({courses[c]['term']
                                            for c in course_ids})},
    }
    document = {
        'scope': 'learner_deduped_scope',
        'basis': basis,
        'definitions': store.table('definitions'),
        'groups': groups,
        'overlap': overlap,
        'additivity': {
            'person_metrics_additive': False,
            'attendance_events_additive': True,
            'completion_fraction_rule':
                'completed_people / eligible_people over distinct learners; '
                'never the mean of per-class fractions',
        },
    }
    if scope.total:
        document['total'] = total_block
    if course_breakdown is not None:
        document['course_detail'] = course_breakdown
    return document


def metrics_query(store, query):
    return scope_metrics(store, parse_scope(query))


def target_threshold(store, course_ids):
    """Scope target = strictest minimum among in-scope course targets."""
    targets = store.table('course_targets')
    picked = [row for row in targets if row['course'] in set(course_ids)]
    if not picked:
        raise DataError('no course_targets for selected scope')
    return min(row['minimum'] for row in picked)
