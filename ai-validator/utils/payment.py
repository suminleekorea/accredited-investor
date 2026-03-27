from __future__ import annotations

import re


def _parse_amount(value: str) -> float:
    cleaned = re.sub(r"[^\d.]", "", value)
    return float(cleaned) if cleaned else 0.0


def _format_amount(value: float | None) -> str:
    return f"USD {value:,.2f}" if value else "Not found"


def _snippet(text: str, matched_text: str, radius: int = 80) -> str:
    index = text.lower().find(matched_text.lower())
    if index < 0:
        return matched_text
    start = max(0, index - radius)
    end = min(len(text), index + len(matched_text) + radius)
    return text[start:end].replace("\n", " ").strip()


def _find_payment_amount(text: str) -> dict | None:
    patterns = [
        ("Remittance amount", r"(?:usd|amount|payment amount|instructed amount|32a[:\s])\s*[:\-]?\s*(usd)?\s*([\d,]+(?:\.\d{2})?)"),
    ]
    for label, pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return {
                "label": label,
                "value": match.group(2),
                "snippet": _snippet(text, match.group(0)),
            }
    return None


def _find_reference(text: str) -> dict | None:
    patterns = [
        ("Policy/reference", r"(?:policy number|policy no\.?|reference|ref no\.?|transaction reference|uetr)\s*[:\-]?\s*([A-Z0-9\-\/]{5,})"),
    ]
    for label, pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return {
                "label": label,
                "value": match.group(1),
                "snippet": _snippet(text, match.group(0)),
            }
    return None


def _find_party(text: str, label: str, pattern: str) -> dict | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return {
        "label": label,
        "value": match.group(1).strip(),
        "snippet": _snippet(text, match.group(0)),
    }


def _extract_fields(document: dict) -> dict:
    text = document["text"]
    amount = _find_payment_amount(text)
    reference = _find_reference(text)
    payer = _find_party(text, "Payer", r"(?:ordering customer|payer|remitter)\s*[:\-]?\s*([A-Z0-9 ,.&'-]{3,60})")
    payee = _find_party(text, "Payee", r"(?:beneficiary|payee)\s*[:\-]?\s*([A-Z0-9 ,.&'-]{3,60})")

    document["evidence"] = [item for item in (amount, reference, payer, payee) if item]
    return {
        "currency": "USD" if "usd" in text.lower() else None,
        "amount": _parse_amount(amount["value"]) if amount else None,
        "reference": reference["value"] if reference else None,
        "payer": payer["value"] if payer else None,
        "payee": payee["value"] if payee else None,
    }


def _reference_matches(expected_reference: str, extracted_reference: str | None) -> bool:
    if not expected_reference or not extracted_reference:
        return False
    normalized_expected = re.sub(r"[^A-Z0-9]", "", expected_reference.upper())
    normalized_extracted = re.sub(r"[^A-Z0-9]", "", extracted_reference.upper())
    return normalized_expected in normalized_extracted or normalized_extracted in normalized_expected


def validate_payment_workflow(documents: list[dict], expected_amount: float, expected_reference: str) -> dict:
    matched_evidence = []
    missing_evidence = []
    manual_review_reasons = []
    amounts = []
    references = []

    for document in documents:
        fields = _extract_fields(document)
        document["fields"] = fields

        if fields["amount"] is not None:
            amounts.append(fields["amount"])
            matched_evidence.append(f"{document['filename']}: amount {fields['amount']:,.2f}")
        if fields["reference"]:
            references.append(fields["reference"])
            matched_evidence.append(f"{document['filename']}: reference {fields['reference']}")
        if document["document_type"] != "payment proof":
            manual_review_reasons.append(f"{document['filename']}: document does not clearly look like payment proof.")
        manual_review_reasons.extend(document["warnings"])

    best_amount = max(amounts) if amounts else None
    best_reference = references[0] if references else None
    amount_matches = best_amount is not None and abs(best_amount - expected_amount) < 1
    reference_matches = _reference_matches(expected_reference, best_reference)

    if best_amount is None:
        missing_evidence.append("No remittance amount found.")
    if expected_reference and not best_reference:
        missing_evidence.append("No policy/reference number found.")
    if best_amount is not None and not amount_matches:
        manual_review_reasons.append("Extracted amount does not match the expected amount.")
    if expected_reference and best_reference and not reference_matches:
        manual_review_reasons.append("Extracted reference does not match the expected policy/reference.")

    if not any(document["text"] for document in documents):
        status = "Insufficient evidence"
        summary = "No usable text was extracted from the uploaded payment documents."
    elif amount_matches and (reference_matches or not expected_reference):
        status = "Review passed" if not manual_review_reasons else "Needs manual review"
        summary = "Payment amount matched the expected input."
    elif best_amount is not None or best_reference:
        status = "Needs manual review"
        summary = "Some payment evidence was found, but the match is incomplete."
    else:
        status = "Insufficient evidence"
        summary = "The uploaded files did not contain clear payment fields."

    unique_reasons = list(dict.fromkeys(manual_review_reasons))

    return {
        "status": status,
        "summary": summary,
        "fields": {
            "currency": "USD" if any(document["fields"]["currency"] for document in documents if "fields" in document) else "Not found",
            "amount": best_amount,
            "amount_display": _format_amount(best_amount),
            "reference": best_reference or "Not found",
            "reference_match": "Matched" if reference_matches else "Not matched" if expected_reference else "Not checked",
            "payer": next((document["fields"]["payer"] for document in documents if document["fields"]["payer"]), "Not found"),
            "payee": next((document["fields"]["payee"] for document in documents if document["fields"]["payee"]), "Not found"),
        },
        "matched_evidence": list(dict.fromkeys(matched_evidence)),
        "missing_evidence": missing_evidence,
        "manual_review_reasons": unique_reasons,
        "documents": documents,
    }
