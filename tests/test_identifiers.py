from credential_vault.identifiers import next_record_id
from credential_vault.models import RecordType


def test_next_record_id_increments_within_same_type() -> None:
    record_id = next_record_id(
        RecordType.WEB_LOGIN,
        ["rec_api_001", "rec_web_001", "rec_web_004", "rec_mch_002"],
    )

    assert record_id == "rec_web_005"
