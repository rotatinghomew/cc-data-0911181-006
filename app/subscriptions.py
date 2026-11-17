"""Persisted subscription definitions.

A saved view captures only the subscription definition (scope filters,
grouping, recipient, cadence). Temporary drilldown expansions are GET queries
on /api/metrics and are never written here, so weekly materials stay anchored
to a stable definition.
"""
from .metrics import GROUP_DIMENSIONS, Scope, _check_filters
from .storage import DataError

KIND = 'subscription_view'
CADENCES = ('weekly', 'monthly')


def save(store, journal, payload):
    view = payload.get('view')
    if not isinstance(view, str) or not view:
        raise DataError('view required')
    recipient = payload.get('recipient')
    if not isinstance(recipient, str) or not recipient:
        raise DataError('recipient required')
    cadence = payload.get('cadence')
    if cadence not in CADENCES:
        raise DataError('unsupported cadence: ' + str(cadence))
    group_by = payload.get('group_by')
    if group_by is not None and group_by not in GROUP_DIMENSIONS:
        raise DataError('unsupported group_by: ' + str(group_by))

    def cleaned(name):
        values = payload.get(name) or []
        if not isinstance(values, list) or not all(
                isinstance(value, str) and value for value in values):
            raise DataError(name + ' must be a list of nonempty strings')
        if len(set(values)) != len(values):
            raise DataError('duplicate filter value: ' + name)
        return sorted(values)

    scope = Scope(cleaned('directions'), cleaned('campuses'),
                  cleaned('terms'), group_by,
                  bool(payload.get('detail', False)),
                  bool(payload.get('total', True)))
    _check_filters(store, scope)
    with journal.transaction():
        try:
            journal.get(KIND, view)
        except DataError:
            pass
        else:
            raise DataError('subscription view already exists: ' + view)
        row = {'view': view, 'recipient': recipient, 'cadence': cadence,
               'filters': scope.filters()}
        return journal.put(KIND, view, row)


def load(journal, view):
    return journal.get(KIND, view)


def list_views(journal):
    return journal.all(KIND)
