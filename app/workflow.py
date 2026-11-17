from . import targets
from . import followups
from . import deliveries
from . import subscriptions

OPERATIONS={
    'targets.evaluate':targets.evaluate,
    'targets.evaluate_scope':targets.evaluate_scope,
    'followups.assign':followups.assign,
    'followups.assign_scope':followups.assign_scope,
    'followups.close':followups.close,
    'deliveries.prepare':deliveries.prepare,
    'deliveries.prepare_scope':deliveries.prepare_scope,
    'views.save':subscriptions.save,
}
