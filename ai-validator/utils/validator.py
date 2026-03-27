from __future__ import annotations

import re

INCOME_THRESHOLD = 300000
NET_WORTH_THRESHOLD = 2000000


def _parse_money(value: str) -> int:
    cleaned = re.sub(r"[^\d.]", "", value)
    if not cleaned:
        return 0
    return int(float(cleaned))


def _format_money(value: int | None) -> str:
    return f"USD {value:,.0f}" if value else "Not found"


def _snippet(text: str, matched_text: str, radius: int = 80) -> str:
    index = text.lower().find(matched_text.lower())
    if index < 0:
        return matched_text
    start = max(0, index - radius)
    end = min(len(text), index + len(matched_text) + radius)
    return text[start:end].replace("\n", " ").strip()


def _find_first(text: str, patterns: list[tuple[str, str]]) -> dict | None:
    for label, pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            return {
                "label": label,
                "value": value,
                "snippet": _snippet(text, match.group(0)),
            }
    return None


def _extract_applicant_name(text: str) -> dict | None:
    return _find_first(
        text,
        [
            ("Applicant name", r"(?:applicant|client|customer|name)\s*[:\-]\s*([A-Z][A-Z ,.'-]{2,60})"),
        ],
    )


def _extract_income(text: str) -> dict | None:
    return _find_first(
        text,
        [
            ("Annual income", r"(?:annual income|gross annual income|income|salary|earnings)\s*[:\-]?\s*(?:sgd|usd|s\$|\$)?\s*([\d,]+(?:\.\d{2})?)"),
        ],
    )


def _extract_net_worth(text: str) -> dict | None:
    return _find_first(
        text,
        [
            ("Net worth", r"(?:net worth|total net worth|assets under management|portfolio value|total assets)\s*[:\-]?\s*(?:sgd|usd|s\$|\$)?\s*([\d,]+(?:\.\d{2})?)"),
        ],
    )


def _extract_fields(document: dict) -> dict:
    text = document["text"]
    name = _extract_applicant_name(text)
    income = _extract_income(text)
    net_worth = _extract_net_worth(text)

    evidence = [item for item in (name, income, net_worth) if item]
    document["evidence"] = evidence

    return {
        "applicant_name": name["value"] if name else None,
        "annual_income": _parse_money(income["value"]) if income else None,
        "net_worth": _parse_money(net_worth["value"]) if net_worth else None,
    }


def _has_conflict(values: list[int]) -> bool:
    unique = sorted(set(values))
    if len(unique) < 2:
        return False
    smallest = unique[0]
    largest = unique[-1]
    if smallest == 0:
        return True
    return (largest - smallest) / smallest > 0.2


def validate_investor_workflow(documents: list[dict]) -> dict:
    all_income = []
    all_net_worth = []
    matched_evidence = []
    manual_review_reasons = []

    for document in documents:
        fields = _extract_fields(document)
        document["fields"] = fields

        if fields["annual_income"]:
            all_income.append(fields["annual_income"])
            matched_evidence.append(f"{document['filename']}: annual income {fields['annual_income']:,.0f}")
        if fields["net_worth"]:
            all_net_worth.append(fields["net_worth"])
            matched_evidence.append(f"{document['filename']}: net worth {fields['net_worth']:,.0f}")
        if document["document_type"] == "unknown":
            manual_review_reasons.append(f"{document['filename']}: unsupported or unclear document type.")
        manual_review_reasons.extend(document["warnings"])

    best_income = max(all_income) if all_income else None
    best_net_worth = max(all_net_worth) if all_net_worth else None

    if _has_conflict(all_income):
        manual_review_reasons.append("Conflicting annual income values were found across documents.")
    if _has_conflict(all_net_worth):
        manual_review_reasons.append("Conflicting net-worth values were found across documents.")

    missing_evidence = []
    if not best_income:
        missing_evidence.append("No annual income found.")
    if not best_net_worth:
        missing_evidence.append("No net worth found.")

    if not any(document["text"] for document in documents):
        status = "Insufficient evidence"
        summary = "No usable text was extracted from the uploaded documents."
    elif best_income and best_income >= INCOME_THRESHOLD and not _has_conflict(all_income):
        status = "Review passed" if not manual_review_reasons else "Needs manual review"
        summary = "Income evidence meets the configured threshold."
    elif best_net_worth and best_net_worth >= NET_WORTH_THRESHOLD and not _has_conflict(all_net_worth):
        status = "Review passed" if not manual_review_reasons else "Needs manual review"
        summary = "Net-worth evidence meets the configured threshold."
    elif best_income or best_net_worth:
        status = "Needs manual review"
        summary = "Financial evidence was found, but it does not clearly meet the configured threshold."
    else:
        status = "Insufficient evidence"
        summary = "The uploaded files did not contain clear income or net-worth fields."

    unique_reasons = list(dict.fromkeys(manual_review_reasons))

    return {
        "status": status,
        "summary": summary,
        "fields": {
            "annual_income": best_income,
            "net_worth": best_net_worth,
            "annual_income_display": _format_money(best_income),
            "net_worth_display": _format_money(best_net_worth),
            "thresholds": {
                "annual_income": INCOME_THRESHOLD,
                "net_worth": NET_WORTH_THRESHOLD,
            },
        },
        "matched_evidence": list(dict.fromkeys(matched_evidence)),
        "missing_evidence": missing_evidence,
        "manual_review_reasons": unique_reasons,
        "documents": documents,
    }
