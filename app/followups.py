from .metrics import saved_scope, select_courses
from .storage import DataError
from .subscriptions import load as load_view
from .targets import ASSESSMENT_KIND


def assign(store,journal,payload):
    with journal.transaction():
        assessment=journal.get('target_assessment',payload['assessment'])
        if not assessment['below_target']:
            raise DataError('target not missed')
        owner_rows = store.select('course_owners', course=assessment['course'])
        if len(owner_rows) != 1:
            raise DataError('single course owner required for legacy followup: '
                            + assessment['course'])
        owner = owner_rows[0]['owner']
        key=assessment['course']
        existing=[row for row in journal.all('followup') if row['case']==key]
        if existing:
            return existing[0]
        return journal.put('followup',key,dict(case=key,assessment=assessment['assessment'],owner=owner,status='open'))


def close(store,journal,payload):
    with journal.transaction():
        case=journal.get('followup',payload['case'])
        if case['owner']!=payload['owner']:
            raise DataError('wrong followup owner')
        case['status']='closed'
        return journal.put('followup',case['case'],case)


def _scope_owners(store, course_ids):
    """Map each responsible campus to its in-scope courses.

    A cross-campus course appears under every owning campus, and each campus
    only receives a shared part of the scope rather than treating the whole
    scope as its own responsibility.
    """
    owners = {}
    for row in store.table('course_owners'):
        if row['course'] in course_ids:
            owners.setdefault(row['owner'], []).append(row['course'])
    return owners


def assign_scope(store, journal, payload):
    with journal.transaction():
        assessment = journal.get(ASSESSMENT_KIND, payload['assessment'])
        if not assessment['below_target']:
            raise DataError('target not missed')
        view_row = load_view(journal, assessment['view'])
        course_ids = set(select_courses(store, saved_scope(view_row['filters'])))
        owner_courses = _scope_owners(store, course_ids)
        if not owner_courses:
            raise DataError('no course owners for selected scope')
        problem_key = assessment['problem_key']
        cases = []
        for owner, courses in sorted(owner_courses.items()):
            case_key = problem_key + ':' + owner
            existing = [row for row in journal.all('followup')
                        if row['case'] == case_key]
            if existing:
                cases.append(existing[0])
                continue
            case = {
                'case': case_key,
                'problem_key': problem_key,
                'assessment': assessment['assessment'],
                'owner': owner,
                'responsibility': 'shared' if len(owner_courses) > 1 else 'sole',
                'scope_courses': sorted(courses),
                'affected_people': assessment['affected_people'],
                'status': 'open',
            }
            cases.append(journal.put('followup', case_key, case))
        return {'problem_key': problem_key, 'followups': cases}
