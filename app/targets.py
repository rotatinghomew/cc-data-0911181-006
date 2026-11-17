from .domain import course_statistics


def evaluate(store,journal,payload):
    view=store.find('views',view=payload['view'])
    stats=course_statistics(store,view['course'])
    target=store.find('course_targets',course=view['course'])
    rate=stats['completion_fraction']
    row=dict(assessment=payload['assessment'],view=view['view'],course=view['course'],
             below_target=rate is not None and rate<target['minimum'],basis=stats)
    with journal.transaction():
        return journal.put('target_assessment',row['assessment'],row)
