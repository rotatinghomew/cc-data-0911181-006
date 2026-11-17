from datetime import datetime, timezone
from .analysis import ROUTES
from .service import dispatch


def report(store, journal=None):
    sections = {path: dispatch(store, path, {}, journal)
                for path in ROUTES}
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'dataset_fingerprint': store.fingerprint(),
        'sections': sections,
    }
