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
        ("Premium amount", r"(?:premium amount|insurance premium|amount s\$|amount ss|amount)\s*[:\-]?\s*(?:sgd|s\$)?\s*([\d,]+(?:\.\d{2})?)"),
        ("Credit amount", r"(?:credit amount|credited amount|deposit amount)\s*[:\-]?\s*(?:sgd|usd|s\$)?\s*([\d,]+(?:\.\d{2})?)"),
    ]
    for label, pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = next(group for group in match.groups()[::-1] if group)
            return {
                "label": label,
                "value": value,
                "snippet": _snippet(text, match.group(0)),
            }
    return None


def _find_reference(text: str) -> dict | None:
    patterns = [
        ("Policy/reference", r"(?:policy number|policy no\.?|reference|ref no\.?|transaction reference|uetr)\s*[:\-]?\s*([A-Z0-9\-\/]{5,})"),
        ("Policy/reference", r"(?:statement details|remarks|narration|description)\s*[:\-]?\s*([A-Z0-9\-\/ ]{5,80})"),
        ("Policy/reference", r"\b(\d{9})\b"),
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
    account_owner = _find_party(
        text,
        "Account owner",
        r"(?:proposer name|account owner|account holder|name)\s*[:\-]?\s*([A-Z][A-Z0-9 ,.&'-]{3,60})",
    )
    transaction = _find_party(
        text,
        "Transaction",
        r"(?:transaction(?: reference)?|transaction no\.?|txn|uetr)\s*[:\-]?\s*([A-Z0-9\-\/]{5,40})",
    )

    document["evidence"] = [item for item in (amount, reference, payer, payee, account_owner, transaction) if item]
    currency = None
    lowered = text.lower()
    if any(token in lowered for token in ("sgd", "s$", "sgd$")):
        currency = "SGD"
    elif "usd" in lowered:
        currency = "USD"
    return {
        "currency": currency,
        "amount": _parse_amount(amount["value"]) if amount else None,
        "reference": reference["value"] if reference else None,
        "payer": payer["value"] if payer else None,
        "payee": payee["value"] if payee else None,
        "account_owner": account_owner["value"] if account_owner else None,
        "transaction": transaction["value"] if transaction else None,
    }


def _reference_matches(expected_reference: str, extracted_reference: str | None) -> bool:
    if not expected_reference or not extracted_reference:
        return False
    normalized_expected = re.sub(r"[^A-Z0-9]", "", expected_reference.upper())
    normalized_extracted = re.sub(r"[^A-Z0-9]", "", extracted_reference.upper())
    return normalized_expected in normalized_extracted or normalized_extracted in normalized_expected


def _reference_review_status(expected_reference: str, extracted_reference: str | None) -> str:
    if _reference_matches(expected_reference, extracted_reference):
        return "Matched"
    if extracted_reference:
        return "Possible mismatch"
    return "Manual review needed"


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
    reference_required = True

    if best_amount is None:
        missing_evidence.append("No remittance amount found.")
    if not best_reference:
        missing_evidence.append("No policy/reference number found.")
    if best_amount is not None and not amount_matches:
        manual_review_reasons.append("Extracted amount does not match the expected amount.")
    if not expected_reference:
        manual_review_reasons.append("Expected policy/reference was not provided by the reviewer.")
    elif best_reference and not reference_matches:
        manual_review_reasons.append("Extracted reference does not match the expected policy/reference.")

    if not any(document["text"] for document in documents):
        status = "Insufficient evidence"
        summary = "No usable text was extracted from the uploaded payment documents."
    elif amount_matches and reference_matches:
        status = "Review passed" if not manual_review_reasons else "Needs manual review"
        summary = "Payment amount and policy/reference matched the expected input."
    elif best_amount is not None or best_reference:
        status = "Needs manual review"
        summary = "Some payment evidence was found, but the amount/reference match is incomplete."
    else:
        status = "Insufficient evidence"
        summary = "The uploaded files did not contain clear payment fields."

    unique_reasons = list(dict.fromkeys(manual_review_reasons))

    return {
        "status": status,
        "summary": summary,
        "fields": {
            "currency": next(
                (document["fields"]["currency"] for document in documents if "fields" in document and document["fields"]["currency"]),
                "Not found",
            ),
            "amount": best_amount,
            "amount_display": (
                f"{next((document['fields']['currency'] for document in documents if 'fields' in document and document['fields']['currency']), 'USD')} {best_amount:,.2f}"
                if best_amount is not None
                else "Not found"
            ),
            "reference": best_reference or "Not found",
            "reference_required": reference_required,
            "reference_match": _reference_review_status(expected_reference, best_reference),
            "payer": next((document["fields"]["payer"] for document in documents if document["fields"]["payer"]), "Not found"),
            "payee": next((document["fields"]["payee"] for document in documents if document["fields"]["payee"]), "Not found"),
            "account_owner": next(
                (document["fields"]["account_owner"] for document in documents if document["fields"]["account_owner"]),
                "Not found",
            ),
            "transaction": next(
                (document["fields"]["transaction"] for document in documents if document["fields"]["transaction"]),
                "Not found",
            ),
        },
        "matched_evidence": list(dict.fromkeys(matched_evidence)),
        "missing_evidence": missing_evidence,
        "manual_review_reasons": unique_reasons,
        "documents": documents,
    }
