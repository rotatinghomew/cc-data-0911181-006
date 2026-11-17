from .domain import course_statistics
from .metrics import metrics_query
from .storage import single
from .subscriptions import list_views


def statistics(store,query):
    selected=single(query,'course')
    return {'courses':[course_statistics(store,row['course']) for row in store.table('courses')
                       if selected is None or row['course']==selected],
            'scope':'separate_course_totals'}


def subscriptions(store,query):
    return {'deliveries':[dict(view=row['view'],recipient=row['recipient'],cadence=row['cadence'],
                               body=course_statistics(store,row['course'])) for row in store.table('views')]}


def saved_views(store,query,journal=None):
    return {'views': list_views(journal) if journal is not None else []}


ROUTES={'/api/statistics':statistics,'/api/subscriptions':subscriptions,
        '/api/metrics':metrics_query,'/api/saved_views':saved_views}
