def prepare(store,journal,payload):
    with journal.transaction():
        assessment=journal.get('target_assessment',payload['assessment'])
        view=store.find('views',view=assessment['view'])
        related=[case for case in journal.all('followup') if case['assessment']==assessment['assessment']]
        row=dict(delivery=payload['delivery'],view=view['view'],recipient=view['recipient'],
                 basis=assessment['basis'],followups=related,status='prepared')
        return journal.put('delivery',row['delivery'],row)
