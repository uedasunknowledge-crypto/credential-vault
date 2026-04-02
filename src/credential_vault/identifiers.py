from __future__ import annotations

import re
from collections.abc import Iterable

from credential_vault.models import RecordType


PREFIX_BY_TYPE = {
    RecordType.API_SECRET: "rec_api",
    RecordType.WEB_LOGIN: "rec_web",
    RecordType.MACHINE_SECRET: "rec_mch",
    RecordType.MAILBOX_ACCOUNT: "rec_mbx",
    RecordType.SMTP_ACCOUNT: "rec_smtp",
}


def next_record_id(record_type: RecordType, existing_ids: Iterable[str]) -> str:
    prefix = PREFIX_BY_TYPE[record_type]
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    max_number = 0

    for record_id in existing_ids:
        match = pattern.match(record_id)
        if match:
            max_number = max(max_number, int(match.group(1)))

    return f"{prefix}_{max_number + 1:03d}"


def normalize_alias(alias: str) -> str:
    return alias.strip()
