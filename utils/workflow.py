from __future__ import annotations

from datetime import datetime, UTC
from typing import Any
import uuid

from utils.data_store import load_json, save_json


USERS_FILE = "users.json"
CLIENTS_FILE = "clients.json"
EMAIL_LOGS_FILE = "email_logs.json"
CASES_FILE = "workflow_cases.json"

DEFAULT_USERS = {
    "users": [
        {"id": "u-nb-1", "name": "Abby Tan", "email": "abby.tan@example.com", "role": "nb_admin", "active": True},
        {"id": "u-nb-2", "name": "Joie Lim", "email": "joie.lim@example.com", "role": "nb_admin", "active": True},
        {"id": "u-hnw-1", "name": "Shaun HNW", "email": "shaun.hnw@example.com", "role": "hnw_reviewer", "active": True},
        {"id": "u-lead-1", "name": "Claudia Lead", "email": "claudia.lead@example.com", "role": "team_lead", "active": True},
        {"id": "u-policy-1", "name": "Policy Admin", "email": "policy.admin@example.com", "role": "policy_admin", "active": True},
        {"id": "u-fin-1", "name": "Finance Ops", "email": "finance.ops@example.com", "role": "finance", "active": True},
        {"id": "u-cash-1", "name": "Cashier Ops", "email": "cashier.ops@example.com", "role": "cashier", "active": True},
    ]
}

DEFAULT_CLIENTS = {
    "clients": [
        {"id": "c-001", "name": "John Tan", "email": "john.tan@example.com"},
        {"id": "c-002", "name": "Sarah Lim", "email": "sarah.lim@example.com"},
        {"id": "c-003", "name": "Alice Tan", "email": "alice.tan@example.com"},
    ]
}

INVESTOR_STATUS_OPTIONS = ["New", "Pending docs", "HNW review", "Approved", "Rejected"]
INVESTOR_QUEUE_OPTIONS = [
    "NB admin review",
    "Awaiting customer documents",
    "Pending HNW validation",
    "Pending team lead approval",
    "Pending policy admin tagging",
    "Completed",
    "Closed",
]
USD_STATUS_OPTIONS = ["MT103 received", "Funds sighted", "Cashier notified", "Premium posted", "Rejected"]
USD_QUEUE_OPTIONS = [
    "Finance review",
    "Awaiting funds sighting",
    "Pending cashier posting",
    "Completed",
    "Closed",
]


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def seed_workflow_data() -> None:
    users = load_json(USERS_FILE, {})
    if not users or not users.get("users"):
        save_json(USERS_FILE, DEFAULT_USERS)

    clients = load_json(CLIENTS_FILE, {})
    if not clients or not clients.get("clients"):
        save_json(CLIENTS_FILE, DEFAULT_CLIENTS)

    email_logs = load_json(EMAIL_LOGS_FILE, None)
    if email_logs is None:
        save_json(EMAIL_LOGS_FILE, [])

    cases = load_json(CASES_FILE, None)
    if cases is None:
        save_json(CASES_FILE, [])


def list_users(role: str | None = None) -> list[dict]:
    seed_workflow_data()
    users = load_json(USERS_FILE, DEFAULT_USERS).get("users", [])
    if role:
        return [user for user in users if user["role"] == role and user.get("active", True)]
    return [user for user in users if user.get("active", True)]


def list_clients() -> list[dict]:
    seed_workflow_data()
    return load_json(CLIENTS_FILE, DEFAULT_CLIENTS).get("clients", [])


def list_cases() -> list[dict]:
    seed_workflow_data()
    cases = load_json(CASES_FILE, [])
    return sorted(cases, key=lambda item: item.get("updated_at", ""), reverse=True)


def list_case_messages(case_id: str) -> list[dict]:
    seed_workflow_data()
    logs = load_json(EMAIL_LOGS_FILE, [])
    return [item for item in logs if item.get("case_id") == case_id]


def _select_assignee(role: str) -> dict | None:
    candidates = list_users(role)
    return candidates[0] if candidates else None


def _routing(result: dict) -> tuple[str, str, str]:
    reasons = " ".join(result.get("manual_review_reasons", [])).lower()
    if result["status"] == "Review passed":
        return "medium", "finance", "Finance review"
    if any(
        phrase in reasons
        for phrase in (
            "reference does not match",
            "amount does not match",
            "no policy/reference number found",
            "expected policy/reference was not provided",
        )
    ):
        return "high", "finance", "Finance review"
    if result["status"] == "Insufficient evidence":
        return "high", "finance", "Awaiting funds sighting"
    return "medium", "finance", "Finance review"


def _investor_routing(result: dict) -> tuple[str, str, str]:
    reasons = " ".join(result.get("manual_review_reasons", [])).lower()
    if result["status"] == "Review passed":
        return "medium", "nb_admin", "NB admin review"
    if any(
        phrase in reasons
        for phrase in (
            "conflicting annual income values",
            "conflicting net-worth values",
            "conflicting net financial asset values",
            "unsupported or unclear document type",
        )
    ):
        return "high", "nb_admin", "NB admin review"
    if result["status"] == "Insufficient evidence":
        return "high", "nb_admin", "Awaiting customer documents"
    return "medium", "nb_admin", "NB admin review"


def create_usd_case(
    *,
    client_name: str,
    client_email: str,
    policy_number: str,
    expected_amount: float,
    result: dict,
) -> dict:
    seed_workflow_data()
    alert_level, owner_role, queue = _routing(result)
    assignee = _select_assignee(owner_role)

    case = {
        "id": f"USD-{uuid.uuid4().hex[:8].upper()}",
        "case_type": "usd_payment",
        "client_name": client_name,
        "client_email": client_email,
        "policy_number": policy_number,
        "expected_amount": expected_amount,
        "status": "MT103 received",
        "alert_level": alert_level,
        "queue": queue,
        "assignee_role": owner_role,
        "assignee_name": assignee["name"] if assignee else "Unassigned",
        "assignee_email": assignee["email"] if assignee else "",
        "summary": result["summary"],
        "manual_review_reasons": result.get("manual_review_reasons", []),
        "matched_evidence": result.get("matched_evidence", []),
        "fields": result.get("fields", {}),
        "created_at": _now(),
        "updated_at": _now(),
    }

    cases = load_json(CASES_FILE, [])
    cases.append(case)
    save_json(CASES_FILE, cases)

    logs = load_json(EMAIL_LOGS_FILE, [])
    logs.append(
        {
            "case_id": case["id"],
            "timestamp": _now(),
            "sender": "system",
            "sender_email": "system@local",
            "recipient": case["assignee_email"] or "unassigned",
            "subject": f"{case['id']} created for policy {policy_number}",
            "message": (
                f"USD payment workflow created. Queue: {queue}. Alert: {alert_level}. "
                f"Status: {case['status']}. Finance should sight incoming funds before cashier posting."
            ),
        }
    )
    save_json(EMAIL_LOGS_FILE, logs)
    return case


def create_investor_case(
    *,
    client_name: str,
    client_email: str,
    applicant_name: str,
    result: dict,
) -> dict:
    seed_workflow_data()
    alert_level, owner_role, queue = _investor_routing(result)
    assignee = _select_assignee(owner_role)

    case = {
        "id": f"AI-{uuid.uuid4().hex[:8].upper()}",
        "case_type": "accredited_investor",
        "client_name": client_name,
        "client_email": client_email,
        "applicant_name": applicant_name,
        "status": "New",
        "alert_level": alert_level,
        "queue": queue,
        "assignee_role": owner_role,
        "assignee_name": assignee["name"] if assignee else "Unassigned",
        "assignee_email": assignee["email"] if assignee else "",
        "summary": result["summary"],
        "manual_review_reasons": result.get("manual_review_reasons", []),
        "matched_evidence": result.get("matched_evidence", []),
        "fields": result.get("fields", {}),
        "created_at": _now(),
        "updated_at": _now(),
    }

    cases = load_json(CASES_FILE, [])
    cases.append(case)
    save_json(CASES_FILE, cases)

    logs = load_json(EMAIL_LOGS_FILE, [])
    logs.append(
        {
            "case_id": case["id"],
            "timestamp": _now(),
            "sender": "system",
            "sender_email": "system@local",
            "recipient": case["assignee_email"] or "unassigned",
            "subject": f"{case['id']} created for applicant {applicant_name or client_name}",
            "message": (
                f"Accredited investor workflow created. Queue: {queue}. Alert: {alert_level}. "
                f"Status: {case['status']}. New Business admin should review the submitted documents first."
            ),
        }
    )
    save_json(EMAIL_LOGS_FILE, logs)
    return case


def update_case(case_id: str, *, assignee_email: str | None = None, queue: str | None = None, status: str | None = None) -> dict | None:
    cases = load_json(CASES_FILE, [])
    users = {user["email"]: user for user in list_users()}
    updated_case = None
    for case in cases:
        if case["id"] != case_id:
            continue
        if assignee_email:
            user = users.get(assignee_email)
            case["assignee_email"] = assignee_email
            case["assignee_name"] = user["name"] if user else assignee_email
            case["assignee_role"] = user["role"] if user else case.get("assignee_role", "operator")
        if queue:
            case["queue"] = queue
        if status:
            case["status"] = status
        case["updated_at"] = _now()
        updated_case = case
        break
    save_json(CASES_FILE, cases)
    return updated_case


def add_case_message(
    case_id: str,
    *,
    sender_name: str,
    sender_email: str,
    recipient: str,
    subject: str,
    message: str,
) -> None:
    logs = load_json(EMAIL_LOGS_FILE, [])
    logs.append(
        {
            "case_id": case_id,
            "timestamp": _now(),
            "sender": sender_name,
            "sender_email": sender_email,
            "recipient": recipient,
            "subject": subject,
            "message": message,
        }
    )
    save_json(EMAIL_LOGS_FILE, logs)

    cases = load_json(CASES_FILE, [])
    for case in cases:
        if case["id"] == case_id:
            case["updated_at"] = _now()
            break
    save_json(CASES_FILE, cases)


def get_case(case_id: str) -> dict | None:
    for case in list_cases():
        if case["id"] == case_id:
            return case
    return None
