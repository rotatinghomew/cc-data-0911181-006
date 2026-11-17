from .metrics import saved_scope, scope_metrics, term_status_table
from .subscriptions import load as load_view
from .targets import ASSESSMENT_KIND

SCOPE_DELIVERY_KIND = 'scope_delivery'


def prepare(store,journal,payload):
    with journal.transaction():
        assessment=journal.get('target_assessment',payload['assessment'])
        view=store.find('views',view=assessment['view'])
        related=[case for case in journal.all('followup') if case['assessment']==assessment['assessment']]
        row=dict(delivery=payload['delivery'],view=view['view'],recipient=view['recipient'],
                 basis=assessment['basis'],followups=related,status='prepared')
        return journal.put('delivery',row['delivery'],row)


def prepare_scope(store, journal, payload):
    """Compile weekly material for a saved subscription view.

    The material keeps the assessment's frozen basis and marks whether the
    current data/term state still supports it. Only follow-ups whose problem is
    still open against the current basis are listed as pending; closed problems
    never reappear after regrouping.
    """
    assessment = journal.get(ASSESSMENT_KIND, payload['assessment'])
    view_row = load_view(journal, assessment['view'])
    current = scope_metrics(store, saved_scope(view_row['filters']))

    frozen_basis = assessment['basis']['basis']
    current_basis = current['basis']
    basis_current = (frozen_basis['dataset_fingerprint'] ==
                     current_basis['dataset_fingerprint'])
    statuses = term_status_table(store)
    scoped_terms = current_basis['term_status']
    closed_terms = sorted(term for term, status in scoped_terms.items()
                          if status == 'closed')
    all_terms_closed = bool(scoped_terms) and not (
        set(scoped_terms) - set(closed_terms))

    problem_cases = [case for case in journal.all('followup')
                     if case.get('problem_key') == assessment['problem_key']]
    pending = [case['case'] for case in problem_cases
               if case['status'] == 'open']
    if all_terms_closed:
        pending = []
    still_valid = assessment['below_target'] and basis_current and not all_terms_closed
    followups = [{
        'case': case['case'], 'owner': case['owner'],
        'responsibility': case.get('responsibility', 'sole'),
        'status': case['status'],
        'pending': case['status'] == 'open' and still_valid,
    } for case in problem_cases]

    row = {
        'delivery': payload['delivery'],
        'view': view_row['view'],
        'recipient': view_row['recipient'],
        'cadence': view_row['cadence'],
        'frozen_basis': frozen_basis,
        'current_basis': current_basis,
        'basis_current': basis_current,
        'basis_note': 'material computed on the frozen basis; recompute the '
                      'assessment to act on the current basis'
                      if not basis_current else 'frozen basis matches current data',
        'closed_terms': closed_terms,
        'problem_still_valid': still_valid,
        'pending_followups': pending,
        'followups': followups,
        'status': 'prepared',
    }
    with journal.transaction():
        return journal.put(SCOPE_DELIVERY_KIND, row['delivery'], row)
