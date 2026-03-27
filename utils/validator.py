from __future__ import annotations

import re

INCOME_THRESHOLD = 300000
NET_PERSONAL_ASSETS_THRESHOLD = 2000000
NET_FINANCIAL_ASSETS_THRESHOLD = 1000000
PRIMARY_RESIDENCE_CAP = 1000000


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


def _extract_financial_assets(text: str) -> dict | None:
    return _find_first(
        text,
        [
            ("Net financial assets", r"(?:net financial assets|financial assets|liquid assets|investable assets)\s*[:\-]?\s*(?:sgd|usd|s\$|\$)?\s*([\d,]+(?:\.\d{2})?)"),
        ],
    )


def _extract_primary_residence(text: str) -> dict | None:
    return _find_first(
        text,
        [
            ("Primary residence", r"(?:primary place of residence|primary residence|owner-occupied property)\s*[:\-]?\s*(?:sgd|usd|s\$|\$)?\s*([\d,]+(?:\.\d{2})?)"),
        ],
    )


def _extract_joint_account(text: str) -> dict | None:
    patterns = [
        (
            "Joint account with accredited investor",
            r"(?:joint account(?: holder)?|joint account with an accredited investor|co-held with accredited investor)\s*[:\-]?\s*(yes|true|y)\b",
        ),
    ]
    return _find_first(text, patterns)


def _extract_fields(document: dict) -> dict:
    text = document["text"]
    name = _extract_applicant_name(text)
    income = _extract_income(text)
    net_worth = _extract_net_worth(text)
    financial_assets = _extract_financial_assets(text)
    primary_residence = _extract_primary_residence(text)
    joint_account = _extract_joint_account(text)

    evidence = [item for item in (name, income, net_worth, financial_assets, primary_residence, joint_account) if item]
    document["evidence"] = evidence

    return {
        "applicant_name": name["value"] if name else None,
        "annual_income": _parse_money(income["value"]) if income else None,
        "net_worth": _parse_money(net_worth["value"]) if net_worth else None,
        "net_financial_assets": _parse_money(financial_assets["value"]) if financial_assets else None,
        "primary_residence_value": _parse_money(primary_residence["value"]) if primary_residence else None,
        "joint_account_with_accredited_investor": bool(joint_account),
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
    all_financial_assets = []
    all_primary_residence = []
    matched_evidence = []
    manual_review_reasons = []
    joint_account_found = False

    for document in documents:
        fields = _extract_fields(document)
        document["fields"] = fields

        if fields["annual_income"]:
            all_income.append(fields["annual_income"])
            matched_evidence.append(f"{document['filename']}: annual income {fields['annual_income']:,.0f}")
        if fields["net_worth"]:
            all_net_worth.append(fields["net_worth"])
            matched_evidence.append(f"{document['filename']}: net worth {fields['net_worth']:,.0f}")
        if fields["net_financial_assets"]:
            all_financial_assets.append(fields["net_financial_assets"])
            matched_evidence.append(
                f"{document['filename']}: net financial assets {fields['net_financial_assets']:,.0f}"
            )
        if fields["primary_residence_value"]:
            all_primary_residence.append(fields["primary_residence_value"])
            matched_evidence.append(
                f"{document['filename']}: primary residence value {fields['primary_residence_value']:,.0f}"
            )
        if fields["joint_account_with_accredited_investor"]:
            joint_account_found = True
            matched_evidence.append(f"{document['filename']}: joint account with accredited investor indicated.")
        if document["document_type"] == "unknown":
            manual_review_reasons.append(f"{document['filename']}: unsupported or unclear document type.")
        manual_review_reasons.extend(document["warnings"])

    best_income = max(all_income) if all_income else None
    best_net_worth = max(all_net_worth) if all_net_worth else None
    best_financial_assets = max(all_financial_assets) if all_financial_assets else None
    best_primary_residence = max(all_primary_residence) if all_primary_residence else None
    capped_primary_residence = (
        min(best_primary_residence, PRIMARY_RESIDENCE_CAP) if best_primary_residence is not None else None
    )
    adjusted_net_personal_assets = best_net_worth
    if best_net_worth is not None and best_primary_residence is not None:
        adjusted_net_personal_assets = best_net_worth - best_primary_residence + capped_primary_residence

    if _has_conflict(all_income):
        manual_review_reasons.append("Conflicting annual income values were found across documents.")
    if _has_conflict(all_net_worth):
        manual_review_reasons.append("Conflicting net-worth values were found across documents.")
    if _has_conflict(all_financial_assets):
        manual_review_reasons.append("Conflicting net financial asset values were found across documents.")

    missing_evidence = []
    if not best_income:
        missing_evidence.append("No annual income found.")
    if not best_net_worth:
        missing_evidence.append("No net personal assets found.")
    if not best_financial_assets:
        missing_evidence.append("No net financial assets found.")
    if not joint_account_found:
        missing_evidence.append("No joint-account-with-accredited-investor evidence found.")

    meets_income = bool(best_income and best_income >= INCOME_THRESHOLD and not _has_conflict(all_income))
    meets_net_personal_assets = bool(
        adjusted_net_personal_assets
        and adjusted_net_personal_assets >= NET_PERSONAL_ASSETS_THRESHOLD
        and not _has_conflict(all_net_worth)
    )
    meets_financial_assets = bool(
        best_financial_assets
        and best_financial_assets >= NET_FINANCIAL_ASSETS_THRESHOLD
        and not _has_conflict(all_financial_assets)
    )
    meets_joint_account = joint_account_found

    qualifying_criteria = []
    if meets_income:
        qualifying_criteria.append("Income >= SGD 300,000 in the last 12 months.")
    if meets_net_personal_assets:
        qualifying_criteria.append("Net personal assets exceed SGD 2,000,000 after primary residence cap.")
    if meets_financial_assets:
        qualifying_criteria.append("Net financial assets exceed SGD 1,000,000.")
    if meets_joint_account:
        qualifying_criteria.append("Joint account with an accredited investor is indicated.")

    if not any(document["text"] for document in documents):
        status = "Insufficient evidence"
        summary = "No usable text was extracted from the uploaded documents."
    elif qualifying_criteria:
        status = "Review passed" if not manual_review_reasons else "Needs manual review"
        summary = "At least one DBS accredited investor criterion was identified in the uploaded evidence."
    elif best_income or best_net_worth or best_financial_assets or joint_account_found:
        status = "Needs manual review"
        summary = "Investor evidence was found, but it does not clearly satisfy a DBS accredited investor criterion."
    else:
        status = "Insufficient evidence"
        summary = "The uploaded files did not contain clear accredited-investor evidence."

    unique_reasons = list(dict.fromkeys(manual_review_reasons))

    return {
        "status": status,
        "summary": summary,
        "fields": {
            "annual_income": best_income,
            "net_personal_assets": best_net_worth,
            "adjusted_net_personal_assets": adjusted_net_personal_assets,
            "net_financial_assets": best_financial_assets,
            "primary_residence_value": best_primary_residence,
            "primary_residence_cap": PRIMARY_RESIDENCE_CAP,
            "joint_account_with_accredited_investor": joint_account_found,
            "annual_income_display": _format_money(best_income),
            "net_personal_assets_display": _format_money(best_net_worth),
            "adjusted_net_personal_assets_display": _format_money(adjusted_net_personal_assets),
            "net_financial_assets_display": _format_money(best_financial_assets),
            "primary_residence_value_display": _format_money(best_primary_residence),
            "qualifying_criteria": qualifying_criteria,
            "thresholds": {
                "annual_income": INCOME_THRESHOLD,
                "net_personal_assets": NET_PERSONAL_ASSETS_THRESHOLD,
                "net_financial_assets": NET_FINANCIAL_ASSETS_THRESHOLD,
                "primary_residence_cap": PRIMARY_RESIDENCE_CAP,
            },
        },
        "matched_evidence": list(dict.fromkeys(matched_evidence)),
        "missing_evidence": missing_evidence,
        "manual_review_reasons": unique_reasons,
        "documents": documents,
    }
