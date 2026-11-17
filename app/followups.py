from .storage import DataError


def assign(store,journal,payload):
    with journal.transaction():
        assessment=journal.get('target_assessment',payload['assessment'])
        if not assessment['below_target']:
            raise DataError('target not missed')
        owner=store.find('course_owners',course=assessment['course'])['owner']
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
