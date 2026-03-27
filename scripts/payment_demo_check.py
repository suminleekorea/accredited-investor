from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.ocr import analyze_document
from utils.payment import validate_payment_workflow


class UploadedFile:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = path.name
        self.type = "application/pdf" if path.suffix.lower() == ".pdf" else "image/jpeg"

    def getvalue(self) -> bytes:
        return self.path.read_bytes()


def run_case(label: str, relative_path: str, expected_amount: float, expected_reference: str) -> None:
    path = ROOT / relative_path
    document = analyze_document(UploadedFile(path))
    result = validate_payment_workflow([document], expected_amount=expected_amount, expected_reference=expected_reference)

    print(f"\n=== {label} ===")
    print(f"file: {path.name}")
    print(f"status: {result['status']}")
    print(f"summary: {result['summary']}")
    print(f"currency: {result['fields']['currency']}")
    print(f"amount: {result['fields']['amount_display']}")
    print(f"reference: {result['fields']['reference']}")
    print(f"reference_match: {result['fields']['reference_match']}")
    print(f"account_owner: {result['fields']['account_owner']}")
    print(f"transaction: {result['fields']['transaction']}")
    if result["manual_review_reasons"]:
        print("manual_review_reasons:")
        for reason in result["manual_review_reasons"]:
            print(f"- {reason}")
    if result["missing_evidence"]:
        print("missing_evidence:")
        for reason in result["missing_evidence"]:
            print(f"- {reason}")


if __name__ == "__main__":
    run_case("good_case_bank_policy_match", "sample_docs/payment_pass_policy_match.pdf", 10000.0, "POLICY12345")
    run_case("bad_case_missing_policy", "sample_docs/payment_missing_policy_manual_review.pdf", 10000.0, "POLICY12345")
    run_case("bad_case_wrong_amount", "sample_docs/payment_wrong_amount.pdf", 10000.0, "POLICY12345")
    run_case("bad_case_wrong_reference", "sample_docs/payment_wrong_reference.pdf", 10000.0, "POLICY12345")
