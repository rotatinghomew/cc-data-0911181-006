from .domain import course_statistics
from .storage import single


def statistics(store,query):
    selected=single(query,'course')
    return {'courses':[course_statistics(store,row['course']) for row in store.table('courses')
                       if selected is None or row['course']==selected],
            'scope':'separate_course_totals'}


def subscriptions(store,query):
    return {'deliveries':[dict(view=row['view'],recipient=row['recipient'],cadence=row['cadence'],
                               body=course_statistics(store,row['course'])) for row in store.table('views')]}


ROUTES={'/api/statistics':statistics,'/api/subscriptions':subscriptions}
