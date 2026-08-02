from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


SCHEMA_VERSION = "rag-source-ledger/v1"


class AdmissionStatus(str, Enum):
    READY = "ready"
    DUPLICATE = "duplicate"
    QUARANTINED = "quarantined"
    CORRUPT = "corrupt"


@dataclass(frozen=True)
class SourceLedgerEntry:
    source_id: str
    relative_path: str
    file_name: str
    size_bytes: int
    sha256: str
    declared_format: str
    detected_format: str
    admission_status: AdmissionStatus
    isolation_reason: str = ""
    duplicate_of_source_id: str = ""
    duplicate_of_path: str = ""
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["admission_status"] = self.admission_status.value
        return payload
