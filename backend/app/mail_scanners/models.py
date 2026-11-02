"""Provider-neutral evidence contract, with no storage or network access."""
from dataclasses import asdict, dataclass

UNDISCLOSED_EMPLOYER = 'Employer not disclosed'


@dataclass(frozen=True)
class ConfirmationDetails:
    job_title: str | None
    company: str | None
    intermediary: str | None
    kind: str
    matched_text: str | None
    date_applied: str | None
    posting: dict
    reason: str

    def model_dump(self):
        return asdict(self)


@dataclass(frozen=True)
class ScanResult:
    details: ConfirmationDetails
    decision: dict
    scanner: str
    language: str | None
