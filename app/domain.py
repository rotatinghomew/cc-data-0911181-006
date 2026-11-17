def course_statistics(store,course):
    store.find('courses',course=course)
    registrations=store.select('registrations',course=course)
    identifiers={row['registration'] for row in registrations}
    eligible={row['registration'] for row in registrations if row['eligible']}
    visits=[row for row in store.table('visits') if row['registration'] in identifiers and row['present']]
    completed={row['registration'] for row in store.table('completions')
               if row['registration'] in eligible and row['completed']}
    return dict(course=course,registered_people=len({row['learner'] for row in registrations}),
                attendance_events=len(visits),eligible_registrations=len(eligible),
                completed_registrations=len(completed),
                completion_fraction=len(completed)/len(eligible) if eligible else None,
                registration_evidence=sorted(identifiers))
