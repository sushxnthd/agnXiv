"""AgnXiv: executable verification for computational research."""

from .models import Claim, VerificationPolicy, VerificationRecord, Verdict
from .verify import verify_numeric_claim

__all__ = [
    "Claim",
    "VerificationPolicy",
    "VerificationRecord",
    "Verdict",
    "verify_numeric_claim",
]

__version__ = "0.1.0"
