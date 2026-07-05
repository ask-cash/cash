"""Identity layer for Cash.

A `person_id` is Cash's canonical id for a single human across every platform
they use. Each platform (Discord, Slack, Teams, Telegram, ...) sees its own
`platform_user_id`; we map all of those to one `person_id`.

Public API lives in services.identity.people; storage primitives are in
services.identity.store.
"""

from services.identity.people import (  # noqa: F401
    PERSON_ID_PREFIX,
    Person,
    PlatformIdentity,
    find_by_hint,
    find_platform_identity,
    get_person,
    link_platform_identity,
    list_platform_identities_for_person,
    resolve,
    set_canonical_name,
)
from services.identity.linking import (  # noqa: F401
    canonical_person_id,
    link_identities,
)
from services.identity.store import DB_PATH, ensure_schema  # noqa: F401
from services.identity.summaries import (  # noqa: F401
    PersonSummary,
    build_for_person,
    get_summary_md,
    get_summary_row,
    rebuild_stale,
)
