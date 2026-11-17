from . import targets
from . import followups
from . import deliveries

OPERATIONS={
    'targets.evaluate':targets.evaluate,
    'followups.assign':followups.assign,
    'followups.close':followups.close,
    'deliveries.prepare':deliveries.prepare,
}
