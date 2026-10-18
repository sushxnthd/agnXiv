"""AgnXiv: executable verification for computational research."""

from .models import Claim, Verdict, VerificationPolicy, VerificationRecord
from .verify import verify_numeric_claim

__all__ = [
    "Claim",
    "Verdict",
    "VerificationPolicy",
    "VerificationRecord",
    "verify_numeric_claim",
]

__version__ = "0.1.0"
