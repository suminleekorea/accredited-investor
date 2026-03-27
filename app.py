import streamlit as st
from html import escape
from textwrap import dedent

from utils.ocr import analyze_documents
from utils.payment import validate_payment_workflow
from utils.validator import validate_investor_workflow
from utils.workflow import (
    INVESTOR_QUEUE_OPTIONS,
    INVESTOR_STATUS_OPTIONS,
    USD_QUEUE_OPTIONS,
    USD_STATUS_OPTIONS,
    add_case_message,
    create_investor_case,
    create_usd_case,
    list_case_messages,
    list_cases,
    list_clients,
    list_users,
    seed_workflow_data,
    update_case,
)

st.set_page_config(page_title="Insurance Review Assistant", layout="wide")

STATUS_TO_TONE = {
    "Review passed": "success",
    "Needs manual review": "warning",
    "Insufficient evidence": "error",
}

INVESTOR_ROLE_VIEWS = [
    ("all", "All investor cases"),
    ("nb_admin", "New Business Administration inbox"),
    ("hnw_reviewer", "HNW inbox"),
    ("team_lead", "HNW Lead inbox"),
    ("policy_admin", "Policy Admin inbox"),
]

USD_ROLE_VIEWS = [
    ("all", "All payment cases"),
    ("finance", "Finance inbox"),
    ("cashier", "Cashier inbox"),
]


def html_block(markup: str) -> str:
    return dedent(markup).strip()


def safe_html(value: object) -> str:
    return escape("" if value is None else str(value), quote=True)


def render_next_step_box(title: str, summary: str, actions: list[str]) -> None:
    action_lines = "".join(f"<li>{safe_html(action)}</li>" for action in actions)
    st.markdown(
        html_block(
            f"""
            <div class="ux-panel">
                <div class="ux-kicker">What should I do next?</div>
                <div class="ux-title">{safe_html(title)}</div>
                <div class="ux-body">{safe_html(summary)}</div>
                <div class="ux-body">
                    <ul>{action_lines}</ul>
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


def render_copilot_panel(summary: str, recommendation: str, reasons: list[str], handoff_label: str) -> None:
    st.markdown("### Copilot")
    panel_col, action_col = st.columns([1.5, 1])
    with panel_col:
        st.markdown("**Copilot summary**")
        st.write(summary)
        st.markdown("**Recommended next action**")
        st.write(recommendation)
        st.markdown("**Why this recommendation**")
        if reasons:
            for reason in reasons:
                st.write(f"- {reason}")
        else:
            st.write("- Copilot did not detect any blocking issues.")
    with action_col:
        st.markdown("**One-click handoff**")
        st.info(handoff_label)


def render_recommended_badge(show: bool) -> None:
    label = "Recommended" if show else "Available action"
    css_class = "ux-badge recommended" if show else "ux-badge"
    st.markdown(
        html_block(f'<div class="{css_class}">{safe_html(label)}</div>'),
        unsafe_allow_html=True,
    )


def set_pending_action(case_id: str, action_name: str) -> None:
    st.session_state[f"pending_action_{case_id}"] = action_name


def clear_pending_action(case_id: str) -> None:
    st.session_state.pop(f"pending_action_{case_id}", None)


def get_pending_action(case_id: str) -> str | None:
    return st.session_state.get(f"pending_action_{case_id}")


def filter_cases_for_role(cases: list[dict], role_filter: str) -> list[dict]:
    if role_filter == "all":
        return cases
    return [case for case in cases if case.get("assignee_role") == role_filter]


def get_recommended_investor_action(case: dict) -> str | None:
    role = case.get("assignee_role", "")
    if role == "nb_admin":
        return "forward_to_hnw" if case.get("manual_review_reasons") == [] else "request_more_documents"
    if role == "hnw_reviewer":
        return "criteria_met_pending_approval"
    if role == "team_lead":
        return "approve_case"
    if role == "policy_admin":
        return "mark_tagged"
    return None


def get_recommended_usd_action(case: dict) -> str | None:
    role = case.get("assignee_role", "")
    if role == "finance":
        return "notify_cashier" if case.get("status") == "Funds sighted" else "funds_sighted"
    if role == "cashier":
        return "premium_posted"
    return None


def get_case_guidance(case_type: str, role: str, status: str, queue: str) -> tuple[str, str, list[str]]:
    step = queue or status
    if case_type == "investor":
        if role == "nb_admin":
            return (
                "Initial document check",
                f"This case is at '{step}'. Check whether the submitted documents are complete before sending it forward.",
                [
                    "Use 'Ask for more documents' if key evidence is missing.",
                    "Use 'Send to HNW review' when the file is ready for detailed review.",
                ],
            )
        if role == "hnw_reviewer":
            return (
                "Detailed investor review",
                f"This case is at '{step}'. Review the evidence and decide whether it should move to final approval.",
                [
                    "Use 'Send for final approval' if the criteria appear to be met.",
                    "Use 'Reject case' if the evidence is not enough.",
                ],
            )
        if role == "team_lead":
            return (
                "Final approval",
                f"This case is at '{step}'. Confirm the review outcome and decide whether to approve the case.",
                [
                    "Approve if the case is ready for policy admin processing.",
                    "Reject if the case should be closed.",
                ],
            )
        if role == "policy_admin":
            return (
                "Complete the process",
                f"This case is at '{step}'. Finish the back-office update and mark the case as done.",
                [
                    "Use 'Mark as completed' after the policy system is updated.",
                ],
            )
        return (
            "Review this case",
            f"This case is at '{step}'. Check the summary and follow the next available action.",
            ["Use the case controls below if you need to update owner, step, or status."],
        )

    if role == "finance":
        return (
            "Finance review",
            f"This case is at '{step}'. Confirm whether the payment reached the account and matches the expected details.",
            [
                "Use 'Confirm funds received' when the money is visible in the account.",
                "Use 'Notify cashier' after finance is ready for posting.",
                "Use 'Reject payment' if the proof or payment details do not match.",
            ],
        )
    if role == "cashier":
        return (
            "Post the premium",
            f"This case is at '{step}'. Record the payment in the policy system when posting is complete.",
            [
                "Use 'Mark premium as posted' after the posting is done.",
            ],
        )
    return (
        "Review this payment case",
        f"This case is at '{step}'. Check the summary and follow the next available action.",
        ["Use the case controls below if you need to update owner, step, or status."],
    )


def get_investor_copilot_content(case: dict) -> tuple[str, str, list[str], str]:
    role = case.get("assignee_role", "")
    reasons = list(case.get("manual_review_reasons", []))
    summary = case.get("summary", "Review the uploaded investor evidence and decide the next step.")

    if role == "nb_admin":
        recommendation = "Check whether the document set is complete, then either ask for more documents or send the case to HNW review."
        handoff_label = "Use the action buttons below to request documents or send to HNW review."
    elif role == "hnw_reviewer":
        recommendation = "Review the extracted evidence and decide whether the case is ready for final approval."
        handoff_label = "Use the action buttons below to send for final approval or reject the case."
    elif role == "team_lead":
        recommendation = "Confirm the review outcome and give the final approval decision."
        handoff_label = "Use the action buttons below to approve or reject the case."
    elif role == "policy_admin":
        recommendation = "Record the final back-office update and complete the case."
        handoff_label = "Use the action button below to mark the case as completed."
    else:
        recommendation = "Review the case details and choose the correct next handoff."
        handoff_label = "Use the case controls below to update the case."

    if not reasons:
        reasons = [
            f"Current step: {case.get('queue', '-')}",
            f"Current status: {case.get('status', '-')}",
            f"Current owner: {case.get('assignee_name', '-')}",
        ]

    return summary, recommendation, reasons, handoff_label


def get_usd_copilot_content(case: dict) -> tuple[str, str, list[str], str]:
    role = case.get("assignee_role", "")
    reasons = list(case.get("manual_review_reasons", []))
    summary = case.get("summary", "Review the payment evidence and decide the next step.")

    if role == "finance":
        recommendation = "Check the insurer USD account, confirm whether funds were received, and then notify cashier if the payment is valid."
        handoff_label = "Use the action buttons below to confirm funds, notify cashier, or reject the payment."
    elif role == "cashier":
        recommendation = "Post the premium manually in the policy admin system for the policy."
        handoff_label = "Use the action button below after the premium has been posted."
    else:
        recommendation = "Review the payment case details and choose the correct next handoff."
        handoff_label = "Use the case controls below to update the case."

    if not reasons:
        reasons = [
            f"Current step: {case.get('queue', '-')}",
            f"Current status: {case.get('status', '-')}",
            f"Policy number: {case.get('policy_number', '-')}",
        ]

    return summary, recommendation, reasons, handoff_label


def confirm_investor_action(case: dict, action: str) -> None:
    updated, template = apply_investor_action(case, action)
    if action == "request_more_documents" and updated and template:
        add_case_message(
            case["id"],
            sender_name=case["assignee_name"],
            sender_email=case["assignee_email"],
            recipient=case["client_email"],
            subject=template[0],
            message=template[1],
        )
        st.success("Requested more documents and logged the template.")
    elif action == "forward_to_hnw" and updated:
        st.success("Case forwarded to HNW review.")
    elif action == "criteria_met_pending_approval" and updated and template:
        add_case_message(
            case["id"],
            sender_name=case["assignee_name"],
            sender_email=case["assignee_email"],
            recipient=updated["assignee_email"],
            subject=template[0],
            message=template[1],
        )
        st.success("Forwarded to team lead and logged the approval template.")
    elif action == "approve_case" and updated:
        st.success("Case approved and sent to policy admin.")
    elif action == "reject_case" and updated:
        st.success("Case rejected.")
    elif action == "mark_tagged" and updated:
        st.success("Case marked complete.")

    if updated:
        clear_pending_action(case["id"])
        st.rerun()


def confirm_usd_action(case: dict, action: str) -> None:
    updated, template = apply_usd_action(case, action)
    if action == "funds_sighted" and updated:
        st.success("Finance confirmed funds were sighted.")
    elif action == "notify_cashier" and updated and template:
        add_case_message(
            case["id"],
            sender_name=case["assignee_name"],
            sender_email=case["assignee_email"],
            recipient=updated["assignee_email"],
            subject=template[0],
            message=template[1],
        )
        st.success("Cashier notified and email logged.")
    elif action == "reject_payment" and updated and template:
        add_case_message(
            case["id"],
            sender_name=case["assignee_name"],
            sender_email=case["assignee_email"],
            recipient=case["client_email"],
            subject=template[0],
            message=template[1],
        )
        st.success("Payment case rejected and clarification email logged.")
    elif action == "premium_posted" and updated:
        st.success("Premium marked as posted in policy admin.")

    if updated:
        clear_pending_action(case["id"])
        st.rerun()


def investor_email_template(template_key: str, case: dict) -> tuple[str, str]:
    applicant = case.get("applicant_name", case["client_name"])
    case_id = case["id"]
    if template_key == "request_more_documents":
        return (
            f"{case_id} - Request for additional accredited investor documents",
            (
                f"Dear {applicant},\n\n"
                "We reviewed your accredited investor submission and need additional supporting documents "
                "to complete the assessment.\n\n"
                "Please send updated proof of income, net personal assets, financial assets, or joint-account evidence.\n\n"
                "Regards,\nNew Business Administration"
            ),
        )
    if template_key == "criteria_met_pending_approval":
        return (
            f"{case_id} - AI criteria met, pending approval",
            (
                f"The HNW review for {applicant} is complete.\n\n"
                "The submitted documents indicate that the accredited investor criteria appear to be met. "
                "Please review and confirm approval by email.\n\n"
                "Regards,\nHNW Review Team"
            ),
        )
    return ("", "")


def apply_investor_action(case: dict, action: str) -> tuple[dict | None, tuple[str, str] | None]:
    if action == "request_more_documents":
        updated = update_case(case["id"], queue="Awaiting customer documents", status="Pending docs")
        return updated, investor_email_template(action, case)
    if action == "forward_to_hnw":
        hnw_users = list_users("hnw_reviewer")
        assignee_email = hnw_users[0]["email"] if hnw_users else case["assignee_email"]
        updated = update_case(case["id"], assignee_email=assignee_email, queue="Pending HNW validation", status="HNW review")
        return updated, None
    if action == "criteria_met_pending_approval":
        lead_users = list_users("team_lead")
        assignee_email = lead_users[0]["email"] if lead_users else case["assignee_email"]
        updated = update_case(case["id"], assignee_email=assignee_email, queue="Pending team lead approval", status="HNW review")
        return updated, investor_email_template(action, case)
    if action == "approve_case":
        policy_users = list_users("policy_admin")
        assignee_email = policy_users[0]["email"] if policy_users else case["assignee_email"]
        updated = update_case(case["id"], assignee_email=assignee_email, queue="Pending policy admin tagging", status="Approved")
        return updated, None
    if action == "reject_case":
        nb_users = list_users("nb_admin")
        assignee_email = nb_users[0]["email"] if nb_users else case["assignee_email"]
        updated = update_case(case["id"], assignee_email=assignee_email, queue="Closed", status="Rejected")
        return updated, None
    if action == "mark_tagged":
        updated = update_case(case["id"], queue="Completed", status="Approved")
        return updated, None
    return None, None


def usd_email_template(template_key: str, case: dict) -> tuple[str, str]:
    case_id = case["id"]
    policy = case.get("policy_number", "Unknown policy")
    if template_key == "notify_cashier":
        return (
            f"{case_id} - Premium received for policy {policy}",
            (
                f"Finance has sighted incoming USD funds for policy {policy}.\n\n"
                "Please post the premium in the policy admin system to enforce the policy.\n\n"
                "Regards,\nFinance Team"
            ),
        )
    if template_key == "request_payment_clarification":
        return (
            f"{case_id} - Clarification required for MT103 / payment proof",
            (
                "We reviewed the submitted payment proof and need clarification on the amount or policy number.\n\n"
                "Please send an updated MT103 or supporting remittance proof for follow-up review.\n\n"
                "Regards,\nFinance Team"
            ),
        )
    return ("", "")


def apply_usd_action(case: dict, action: str) -> tuple[dict | None, tuple[str, str] | None]:
    if action == "funds_sighted":
        updated = update_case(case["id"], queue="Finance review", status="Funds sighted")
        return updated, None
    if action == "notify_cashier":
        cashier_users = list_users("cashier")
        assignee_email = cashier_users[0]["email"] if cashier_users else case["assignee_email"]
        updated = update_case(case["id"], assignee_email=assignee_email, queue="Pending cashier posting", status="Cashier notified")
        return updated, usd_email_template(action, case)
    if action == "premium_posted":
        updated = update_case(case["id"], queue="Completed", status="Premium posted")
        return updated, None
    if action == "reject_payment":
        finance_users = list_users("finance")
        assignee_email = finance_users[0]["email"] if finance_users else case["assignee_email"]
        updated = update_case(case["id"], assignee_email=assignee_email, queue="Closed", status="Rejected")
        return updated, usd_email_template("request_payment_clarification", case)
    return None, None


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: #f7f9fc;
            color: #172033;
        }
        .block-container {
            max-width: 1200px;
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }
        h1, h2, h3 {
            color: #0f2747;
            letter-spacing: -0.01em;
        }
        p, li, label, div {
            font-size: 1rem;
            line-height: 1.55;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
            background: #ffffff;
            border: 1px solid #d9e2ef;
            border-radius: 12px;
            padding: 0.4rem;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 10px;
            height: 3rem;
            padding-left: 1rem;
            padding-right: 1rem;
            font-weight: 600;
            color: #3b4f6a;
        }
        .stTabs [aria-selected="true"] {
            background: #e8f0fb;
            color: #0f4c81;
        }
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #d9e2ef;
            border-radius: 14px;
            padding: 1rem 1.1rem;
            box-shadow: 0 4px 14px rgba(16, 36, 94, 0.04);
        }
        [data-testid="stExpander"] {
            background: #ffffff;
            border: 1px solid #d9e2ef;
            border-radius: 12px;
        }
        [data-testid="stExpander"] details,
        [data-testid="stExpander"] summary {
            background: #ffffff !important;
            color: #172033 !important;
        }
        [data-testid="stExpander"] summary:hover,
        [data-testid="stExpander"] summary:focus {
            background: #f3f7fc !important;
            color: #172033 !important;
        }
        [data-testid="stExpander"] summary *,
        [data-testid="stExpander"] summary svg {
            color: #172033 !important;
            fill: #172033 !important;
            stroke: #172033 !important;
            -webkit-text-fill-color: #172033 !important;
        }
        [data-testid="stFileUploader"],
        [data-testid="stTextInput"],
        [data-testid="stTextArea"],
        [data-testid="stNumberInput"],
        [data-testid="stSelectbox"] {
            background: transparent;
        }
        [data-baseweb="select"] > div {
            background: #ffffff !important;
            border: 1px solid #c8d6e8 !important;
            color: #172033 !important;
            box-shadow: none !important;
        }
        [data-baseweb="select"] > div:hover,
        [data-baseweb="select"] > div:focus-within {
            background: #ffffff !important;
            border-color: #0f4c81 !important;
        }
        input, textarea, [data-baseweb="select"] *, [data-testid="stTextInput"] *, [data-testid="stTextArea"] *,
        [data-testid="stNumberInput"] *, [data-testid="stSelectbox"] *, [data-testid="stMarkdownContainer"] {
            color: #172033 !important;
            -webkit-text-fill-color: #172033 !important;
        }
        [data-baseweb="select"] > div,
        [data-baseweb="select"] span,
        [role="listbox"] [role="option"],
        [role="listbox"] [role="option"] * {
            color: #172033 !important;
            -webkit-text-fill-color: #172033 !important;
        }
        [role="listbox"] [role="option"][aria-selected="true"] {
            background: #dcecff !important;
            color: #0f2747 !important;
            font-weight: 700 !important;
        }
        [data-baseweb="popover"] [role="listbox"],
        div[data-baseweb="popover"] ul,
        div[data-baseweb="popover"] li {
            background: #ffffff !important;
            color: #172033 !important;
        }
        [data-baseweb="select"] svg,
        [data-testid="stSelectbox"] svg,
        [data-testid="stNumberInput"] svg {
            fill: #172033 !important;
            stroke: #172033 !important;
        }
        table, thead, tbody, tr, th, td {
            color: #172033 !important;
            -webkit-text-fill-color: #172033 !important;
        }
        [data-testid="stTable"] th,
        [data-testid="stTable"] td,
        [data-testid="stTable"] div,
        [data-testid="stDataFrame"] th,
        [data-testid="stDataFrame"] td,
        [data-testid="stDataFrame"] div {
            color: #172033 !important;
            -webkit-text-fill-color: #172033 !important;
        }
        input::placeholder, textarea::placeholder {
            color: #5a6f8d !important;
            -webkit-text-fill-color: #5a6f8d !important;
        }
        .stButton > button {
            background: #0f4c81;
            color: #ffffff;
            border: 1px solid #0f4c81;
            border-radius: 10px;
            padding: 0.6rem 1rem;
            font-weight: 600;
        }
        .stButton > button *,
        .stButton > button p,
        .stButton > button span {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }
        .stButton > button:hover {
            background: #0c3d68;
            border-color: #0c3d68;
            color: #ffffff;
        }
        .stButton > button:hover * {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }
        .stInfo, .stSuccess, .stWarning, .stError {
            border-radius: 12px;
        }
        .ux-badge {
            display: inline-block;
            margin-bottom: 0.45rem;
            padding: 0.2rem 0.55rem;
            border-radius: 999px;
            background: #edf2f7;
            color: #40566f;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }
        .ux-badge.recommended {
            background: #dff1e7;
            color: #1f6a43;
        }
        .ux-panel {
            background: #ffffff;
            border: 1px solid #d9e2ef;
            border-radius: 16px;
            padding: 1rem 1.1rem;
            margin-bottom: 1rem;
            box-shadow: 0 4px 14px rgba(16, 36, 94, 0.04);
        }
        .ux-kicker {
            color: #5a6f8d;
            font-size: 0.92rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.35rem;
        }
        .ux-title {
            color: #10243f;
            font-size: 1.1rem;
            font-weight: 700;
            margin-bottom: 0.45rem;
        }
        .ux-body {
            color: #31445f;
            font-size: 1rem;
        }
        .ux-ribbon {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 0.75rem;
            margin: 0.5rem 0 1rem 0;
        }
        .ux-ribbon-card {
            background: #ffffff;
            border: 1px solid #d9e2ef;
            border-radius: 14px;
            padding: 0.9rem 1rem;
            box-shadow: 0 4px 14px rgba(16, 36, 94, 0.04);
        }
        .ux-ribbon-label {
            color: #6b7d97;
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 0.25rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .ux-ribbon-value {
            color: #10243f;
            font-size: 1rem;
            font-weight: 700;
            overflow-wrap: anywhere;
        }
        .ux-steps {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 0.75rem;
            margin: 0.75rem 0 1rem 0;
            align-items: stretch;
        }
        .ux-step {
            position: relative;
            background: #ffffff;
            border: 1px solid #d9e2ef;
            border-radius: 14px;
            padding: 0.8rem 0.85rem;
            min-height: 96px;
            box-shadow: 0 4px 14px rgba(16, 36, 94, 0.04);
        }
        .ux-step::after {
            content: "";
            position: absolute;
            top: 22px;
            right: -0.75rem;
            width: 0.75rem;
            height: 2px;
            background: #c9d8ea;
        }
        .ux-step:last-child::after {
            display: none;
        }
        .ux-step.active {
            border: 2px solid #0f4c81;
            background: #e8f0fb;
        }
        .ux-step.done {
            border-color: #9dc0e3;
            background: #f5faff;
        }
        .ux-step-number {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 34px;
            height: 34px;
            border-radius: 999px;
            background: #eef3f9;
            color: #34506f;
            font-size: 0.84rem;
            font-weight: 700;
            margin-bottom: 0.55rem;
            border: 1px solid #d6e0ec;
        }
        .ux-step.active .ux-step-number {
            background: #0f4c81;
            color: #ffffff;
            border-color: #0f4c81;
        }
        .ux-step.done .ux-step-number {
            background: #d7e8f8;
            color: #0f4c81;
            border-color: #9dc0e3;
        }
        .ux-step-title {
            color: #10243f;
            font-size: 1rem;
            font-weight: 700;
            margin-bottom: 0.3rem;
        }
        .ux-step-body {
            color: #42556f;
            font-size: 0.92rem;
            line-height: 1.45;
        }
        @media (max-width: 900px) {
            .ux-ribbon,
            .ux-steps {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .ux-step::after {
                display: none;
            }
        }
        @media (max-width: 640px) {
            .ux-ribbon,
            .ux-steps {
                grid-template-columns: 1fr;
            }
        }
        .ux-mail-list {
            background: #ffffff;
            border: 1px solid #d9e2ef;
            border-radius: 14px;
            overflow: hidden;
            margin-bottom: 1rem;
        }
        .ux-mail-item {
            border-bottom: 1px solid #e8edf5;
            padding: 0.85rem 1rem;
        }
        .ux-mail-item:last-child {
            border-bottom: none;
        }
        .ux-mail-head {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 0.25rem;
        }
        .ux-mail-from {
            color: #10243f;
            font-weight: 700;
        }
        .ux-mail-time {
            color: #6b7d97;
            font-size: 0.9rem;
            white-space: nowrap;
        }
        .ux-mail-subject {
            color: #27496d;
            font-weight: 600;
            margin-bottom: 0.35rem;
        }
        .ux-mail-preview {
            color: #44566e;
            font-size: 0.95rem;
        }
        .ux-confirm {
            background: #fffaf0;
            border: 1px solid #f1d8a8;
            border-radius: 14px;
            padding: 0.9rem 1rem;
            margin: 0.75rem 0 1rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_panels() -> None:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            html_block(
                """
            <div class="ux-panel">
                <div class="ux-kicker">Workflow</div>
                <div class="ux-title">Investor Review</div>
                <div class="ux-body">Use this for document intake, evidence review, approval, and completion.</div>
            </div>
            """
            ),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            html_block(
                """
            <div class="ux-panel">
                <div class="ux-kicker">Workflow</div>
                <div class="ux-title">USD Payment Review</div>
                <div class="ux-body">Use this for TT, MT103, remittance, and payment-proof checks.</div>
            </div>
            """
            ),
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            html_block(
                """
            <div class="ux-panel">
                <div class="ux-kicker">Review Tip</div>
                <div class="ux-title">Manual Review Still Matters</div>
                <div class="ux-body">OCR can miss values on blurry scans, so key amounts and names should still be confirmed by staff.</div>
            </div>
            """
            ),
            unsafe_allow_html=True,
        )


def render_status(status: str, summary: str) -> None:
    tone = STATUS_TO_TONE.get(status, "info")
    getattr(st, tone)(f"{status}: {summary}")


def render_result(result: dict) -> None:
    render_status(result["status"], result["summary"])

    left, right = st.columns(2)
    with left:
        st.markdown("**Matched evidence**")
        if result["matched_evidence"]:
            for item in result["matched_evidence"]:
                st.write(f"- {item}")
        else:
            st.write("No matched evidence found.")

        st.markdown("**Structured fields**")
        st.json(result["fields"])

    with right:
        st.markdown("**Missing evidence**")
        if result["missing_evidence"]:
            for item in result["missing_evidence"]:
                st.write(f"- {item}")
        else:
            st.write("No missing evidence flagged.")

        st.markdown("**Manual review reasons**")
        if result["manual_review_reasons"]:
            for item in result["manual_review_reasons"]:
                st.write(f"- {item}")
        else:
            st.write("No manual review reasons.")

    st.markdown("**Document breakdown**")
    for document in result["documents"]:
        with st.expander(f"{document['filename']} ({document['document_type']})", expanded=False):
            st.caption(
                f"Extraction method: {document['extraction_method']} | "
                f"Text quality: {document['text_quality']} | "
                f"Confidence: {document['confidence']:.0%}"
            )
            if document["warnings"]:
                st.markdown("**Warnings**")
                for warning in document["warnings"]:
                    st.write(f"- {warning}")
            if document["evidence"]:
                st.markdown("**Evidence snippets**")
                for snippet in document["evidence"]:
                    st.write(f"- {snippet['label']}: {snippet['value']}")
                    st.caption(snippet["snippet"])
            else:
                st.write("No structured evidence extracted from this file.")


def render_field_summary(result: dict) -> None:
    fields = result["fields"]
    summary_rows = [
        {"Field": "Annual income", "Value": fields.get("annual_income_display", "Not found")},
        {"Field": "Adjusted net personal assets", "Value": fields.get("adjusted_net_personal_assets_display", "Not found")},
        {"Field": "Net financial assets", "Value": fields.get("net_financial_assets_display", "Not found")},
        {
            "Field": "Joint account with accredited investor",
            "Value": "Yes" if fields.get("joint_account_with_accredited_investor") else "No",
        },
    ]
    st.table(summary_rows)


def render_investor_review_layout(result: dict, selected_client: dict) -> None:
    customer_col, decision_col = st.columns([1, 1.2])
    with customer_col:
        st.markdown("### Customer")
        st.table(
            [
                {"Field": "Client in system", "Value": selected_client["name"]},
                {"Field": "Client email", "Value": selected_client["email"]},
                {
                    "Field": "Applicant name",
                    "Value": next(
                        (document["fields"].get("applicant_name") for document in result["documents"] if document["fields"].get("applicant_name")),
                        "Not found",
                    ),
                },
            ]
        )

        st.markdown("### Documents")
        doc_rows = [
            {
                "File": document["filename"],
                "Type": document["document_type"],
                "Method": document["extraction_method"],
                "Quality": document["text_quality"],
            }
            for document in result["documents"]
        ]
        st.table(doc_rows)

    with decision_col:
        st.markdown("### Review result")
        render_status(result["status"], result["summary"])
        st.markdown("**Extracted financial summary**")
        render_field_summary(result)

        st.markdown("**Matched DBS criteria**")
        if result["fields"]["qualifying_criteria"]:
            for criterion in result["fields"]["qualifying_criteria"]:
                st.write(f"- {criterion}")
        else:
            st.write("No DBS criterion clearly met yet.")

        st.markdown("**Review flags**")
        flags = result["manual_review_reasons"] or result["missing_evidence"]
        if flags:
            for flag in flags:
                st.write(f"- {flag}")
        else:
            st.write("No review flags.")


def render_investor_case_overview(selected_case: dict) -> None:
    current_status = selected_case["status"]
    current_queue = selected_case["queue"]
    workflow_steps = [
        ("1", "New", "Case created and waiting for New Business Administration intake."),
        ("2", "Pending docs", "Missing items are requested from the customer."),
        ("3", "HNW review", "HNW team validates evidence against AI criteria."),
        ("4", "Approved", "Lead approval and policy-admin tagging are completed."),
        ("5", "Rejected", "Case is closed because criteria were not met."),
    ]
    active_map = {
        "New": "New",
        "NB admin review": "New",
        "Pending docs": "Pending docs",
        "Awaiting customer documents": "Pending docs",
        "HNW review": "HNW review",
        "Pending HNW validation": "HNW review",
        "Pending team lead approval": "Approved",
        "Pending policy admin tagging": "Approved",
        "Completed": "Approved",
        "Approved": "Approved",
        "Rejected": "Rejected",
        "Closed": "Rejected",
    }
    active_step = active_map.get(current_status, active_map.get(current_queue, "New"))

    st.markdown("### Workflow")
    ribbon_html = html_block(f"""
    <div class="ux-ribbon">
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Client</div><div class="ux-ribbon-value">{safe_html(selected_case['client_name'])}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Status</div><div class="ux-ribbon-value">{safe_html(selected_case['status'])}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Owner</div><div class="ux-ribbon-value">{safe_html(selected_case['assignee_name'])}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Last updated</div><div class="ux-ribbon-value">{safe_html(selected_case.get('updated_at', '-'))}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Priority</div><div class="ux-ribbon-value">{safe_html(selected_case['alert_level'].upper())}</div></div>
    </div>
    """)
    st.markdown(ribbon_html, unsafe_allow_html=True)

    step_order = ["New", "Pending docs", "HNW review", "Approved", "Rejected"]
    active_index = step_order.index(active_step) if active_step in step_order else 0
    step_cards = []
    for index, (number, title, body) in enumerate(workflow_steps):
        css_class = "ux-step"
        if index < active_index:
            css_class += " done"
        if title == active_step:
            css_class += " active"
        step_cards.append(
            html_block(f"""
            <div class="{css_class}">
                <div class="ux-step-number">{safe_html(number)}</div>
                <div class="ux-step-title">{safe_html(title)}</div>
                <div class="ux-step-body">{safe_html(body)}</div>
            </div>
            """)
        )
    st.markdown(f"<div class='ux-steps'>{''.join(step_cards)}</div>", unsafe_allow_html=True)

    customer_col, workflow_col = st.columns([1, 1.2])
    with customer_col:
        st.markdown("### Customer")
        st.table(
            [
                {"Field": "Client", "Value": selected_case["client_name"]},
                {"Field": "Client email", "Value": selected_case["client_email"]},
                {"Field": "Applicant", "Value": selected_case.get("applicant_name", "Not found")},
            ]
        )

        st.markdown("### Decision")
        st.table(
            [
                {"Field": "Case ID", "Value": selected_case["id"]},
                {"Field": "Status", "Value": selected_case["status"]},
                {"Field": "Current step", "Value": selected_case["queue"]},
                {"Field": "Owner", "Value": selected_case["assignee_name"]},
            ]
        )

    with workflow_col:
        st.markdown("### What this case needs")
        st.write(f"- Summary: {selected_case['summary']}")
        st.write(f"- Current step: {selected_case['queue']}")
        if selected_case["manual_review_reasons"]:
            for reason in selected_case["manual_review_reasons"]:
                st.write(f"- {reason}")
        else:
            st.write("- No review flags recorded.")


def render_conversation_list(messages: list[dict]) -> None:
    if not messages:
        st.write("No messages yet.")
        return

    items = []
    for message in messages:
        preview = message["message"].replace("\n", " ").strip()
        if len(preview) > 140:
            preview = preview[:137] + "..."
        items.append(
            html_block(f"""
            <div class="ux-mail-item">
                <div class="ux-mail-head">
                    <div class="ux-mail-from">{safe_html(message['sender'])} to {safe_html(message['recipient'])}</div>
                    <div class="ux-mail-time">{safe_html(message['timestamp'])}</div>
                </div>
                <div class="ux-mail-subject">{safe_html(message['subject'])}</div>
                <div class="ux-mail-preview">{safe_html(preview)}</div>
            </div>
            """)
        )
    st.markdown(f"<div class='ux-mail-list'>{''.join(items)}</div>", unsafe_allow_html=True)

    for index, message in enumerate(messages):
        with st.expander(f"Open message {index + 1}: {message['subject']}", expanded=False):
            st.write(message["message"])


def render_usd_case_overview(selected_case: dict) -> None:
    active_map = {
        "MT103 received": "MT103 received",
        "Funds sighted": "Funds sighted",
        "Cashier notified": "Cashier notified",
        "Premium posted": "Premium posted",
        "Rejected": "Rejected",
        "Finance review": "MT103 received",
        "Awaiting funds sighting": "MT103 received",
        "Pending cashier posting": "Cashier notified",
        "Completed": "Premium posted",
        "Closed": "Rejected",
    }
    active_step = active_map.get(selected_case["status"], active_map.get(selected_case["queue"], "MT103 received"))
    steps = [
        ("1", "MT103 received", "Customer submits MT103 with amount and policy number."),
        ("2", "Funds sighted", "Finance confirms funds arrived in the USD account."),
        ("3", "Cashier notified", "Finance informs cashier that premium is received."),
        ("4", "Premium posted", "Cashier posts the premium in the policy admin system."),
        ("5", "Rejected", "Case is closed due to mismatch or insufficient evidence."),
    ]

    st.markdown("### Workflow")
    ribbon_html = html_block(f"""
    <div class="ux-ribbon">
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Client</div><div class="ux-ribbon-value">{safe_html(selected_case['client_name'])}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Status</div><div class="ux-ribbon-value">{safe_html(selected_case['status'])}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Owner</div><div class="ux-ribbon-value">{safe_html(selected_case['assignee_name'])}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Last updated</div><div class="ux-ribbon-value">{safe_html(selected_case.get('updated_at', '-'))}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Priority</div><div class="ux-ribbon-value">{safe_html(selected_case['alert_level'].upper())}</div></div>
    </div>
    """)
    st.markdown(ribbon_html, unsafe_allow_html=True)

    order = [title for _, title, _ in steps]
    active_index = order.index(active_step) if active_step in order else 0
    cards = []
    for index, (number, title, body) in enumerate(steps):
        css_class = "ux-step"
        if index < active_index:
            css_class += " done"
        if title == active_step:
            css_class += " active"
        cards.append(
            html_block(f"""
            <div class="{css_class}">
                <div class="ux-step-number">{safe_html(number)}</div>
                <div class="ux-step-title">{safe_html(title)}</div>
                <div class="ux-step-body">{safe_html(body)}</div>
            </div>
            """)
        )
    st.markdown(f"<div class='ux-steps'>{''.join(cards)}</div>", unsafe_allow_html=True)

    left, right = st.columns([1, 1.2])
    with left:
        st.markdown("### Customer")
        st.table(
            [
                {"Field": "Client", "Value": selected_case["client_name"]},
                {"Field": "Client email", "Value": selected_case["client_email"]},
                {"Field": "Policy number", "Value": selected_case.get("policy_number", "Not found")},
                {"Field": "Expected amount", "Value": f"USD {selected_case.get('expected_amount', 0):,.2f}"},
            ]
        )
    with right:
        st.markdown("### What this case needs")
        st.write(f"- Summary: {selected_case['summary']}")
        st.write(f"- Current step: {selected_case['queue']}")
        reasons = selected_case.get("manual_review_reasons", [])
        if reasons:
            for reason in reasons:
                st.write(f"- {reason}")
        else:
            st.write("- No review flags recorded.")


def render_glossary(case_type: str) -> None:
    st.markdown("### Terms used on this page")
    if case_type == "investor":
        st.write("- **Current step**: Where the case is in the process right now.")
        st.write("- **Status**: The latest decision or progress label for the case.")
        st.write("- **Owner**: The person currently responsible for the next action.")
        st.write("- **Priority**: High means the case needs closer attention.")
        st.write("- **NB admin**: New Business Administration team handling first intake.")
        st.write("- **HNW review**: High Net Worth review of accredited investor evidence.")
        st.write("- **Team lead approval**: Final internal sign-off before completion.")
        st.write("- **Policy admin tagging**: Final back-office update in the policy system.")
    else:
        st.write("- **Current step**: Where the payment case is in the process right now.")
        st.write("- **Status**: The latest decision or progress label for the case.")
        st.write("- **Owner**: The person currently responsible for the next action.")
        st.write("- **Priority**: High means the case needs closer attention.")
        st.write("- **Funds sighted**: Finance confirmed the money reached the account.")
        st.write("- **Cashier notified**: Finance asked cashier to post the premium.")
        st.write("- **Premium posted**: The payment was recorded in the policy system.")
        st.write("- **Rejected**: The payment proof was not sufficient or did not match.")


def render_investor_workflow_guide() -> None:
    st.markdown("### Workflow")
    st.write("1. Customer uploads documents")
    st.write("2. New Business Administration checks completeness")
    st.write("3. HNW Team reviews the evidence")
    st.write("4. HNW Team Lead approves or rejects")
    st.write("5. Policy Admin completes the final system update")


def render_usd_workflow_guide() -> None:
    st.markdown("### Workflow")
    st.write("1. Customer submits proof of payment")
    st.write("2. Finance checks amount and policy number")
    st.write("3. Finance confirms funds in the insurer USD account")
    st.write("4. Finance informs Cashier that premium is received")
    st.write("5. Cashier posts the premium in the policy admin system")


def render_guides() -> None:
    seed_workflow_data()
    inject_styles()
    st.title("Insurance Review Assistant")
    st.caption(
        "Assistive review for operations teams. The app highlights extracted evidence and "
        "manual-review triggers; it does not replace HNW validation or team-lead approval."
    )

    st.markdown("### Quick start")
    st.write("- Use **Investor Review** to check accredited investor documents.")
    st.write("- Use **USD Payment Review** to check TT, MT103, remittance, payment proof PDFs, or receipt images.")
    st.write("- Upload one or more files, then review the extracted fields and evidence snippets.")
    st.write("- For USD payments, enter the expected amount and policy/reference before checking the match.")
    st.write("- Move a case step by step using the action buttons and the case controls below.")
    st.write("- Escalate when the app shows missing evidence, low confidence, or conflicting values.")
    render_panels()


def main() -> None:
    render_guides()
    investor_tab, payment_tab = st.tabs(["Investor Review", "USD Payment Review"])

    with investor_tab:
        st.subheader("Investor Review")
        st.caption(
            "Upload financial PDFs to review accredited investor evidence. "
            "You can also create and move cases through the review process here."
        )

        st.markdown("### Start a new review")
        clients = list_clients()
        client_lookup = {f"{client['name']} ({client['email']})": client for client in clients}
        client_choice = st.selectbox("Client", options=list(client_lookup.keys()), key="investor_client")
        selected_client = client_lookup[client_choice]

        investor_files = st.file_uploader(
            "Upload investor documents (PDF)",
            type=["pdf"],
            accept_multiple_files=True,
            key="investor_files",
        )

        if investor_files:
            documents = analyze_documents(investor_files)
            result = validate_investor_workflow(documents)

            copilot_reasons = list(result["manual_review_reasons"] or result["missing_evidence"])
            if result["status"] == "Review passed":
                recommendation = "Create the review case and send it forward for the next human approval step."
                handoff_label = "Create review case"
            elif result["status"] == "Needs manual review":
                recommendation = "Check the flagged evidence, then decide whether to request more documents or continue the review."
                handoff_label = "Review flags before creating the case"
            else:
                recommendation = "Do not move forward yet. Ask the customer for clearer or additional documents."
                handoff_label = "Request more evidence before moving forward"

            render_copilot_panel(
                result["summary"],
                recommendation,
                copilot_reasons,
                handoff_label,
            )
            render_investor_workflow_guide()

            metric1, metric2, metric3 = st.columns(3)
            metric1.metric("Best annual income", result["fields"]["annual_income_display"])
            metric2.metric("Adjusted net personal assets", result["fields"]["adjusted_net_personal_assets_display"])
            metric3.metric("Net financial assets", result["fields"]["net_financial_assets_display"])

            if result["fields"]["qualifying_criteria"]:
                st.markdown("**Matched DBS criteria**")
                for criterion in result["fields"]["qualifying_criteria"]:
                    st.write(f"- {criterion}")

            render_investor_review_layout(result, selected_client)

            with st.expander("Show detailed evidence and extracted snippets", expanded=False):
                render_result(result)

            if st.button("Create review case", key="create_investor_workflow_case"):
                applicant_name = result["documents"][0]["fields"].get("applicant_name") if result["documents"] else ""
                case = create_investor_case(
                    client_name=selected_client["name"],
                    client_email=selected_client["email"],
                    applicant_name=applicant_name or selected_client["name"],
                    result=result,
                )
                st.success(
                    f"Created case {case['id']} in '{case['queue']}' and assigned it to {case['assignee_name']}."
                )
                st.rerun()

        st.divider()
        st.subheader("Open investor cases")
        investor_cases = [case for case in list_cases() if case.get("case_type") == "accredited_investor"]
        investor_role_labels = {value: label for value, label in INVESTOR_ROLE_VIEWS}
        investor_role_choice = st.selectbox(
            "Role view",
            options=list(investor_role_labels.keys()),
            format_func=lambda value: investor_role_labels[value],
            key="investor_role_view",
        )
        investor_cases = filter_cases_for_role(investor_cases, investor_role_choice)

        if not investor_cases:
            st.info("No investor cases in this role view yet. Create one from the review above or switch the role view.")
        else:
            case_labels = [
                f"{case['id']} | {case.get('applicant_name', case['client_name'])} | {case['status']} | {case['assignee_name']}"
                for case in investor_cases
            ]
            selected_label = st.selectbox("Choose a case", options=case_labels, key="open_investor_case")
            selected_case = investor_cases[case_labels.index(selected_label)]

            alert_tone = {"high": st.error, "medium": st.warning, "low": st.info}.get(
                selected_case["alert_level"], st.info
            )
            alert_tone(
                f"Priority: {selected_case['alert_level'].upper()} | Current step: {selected_case['queue']} | "
                f"Owner: {selected_case['assignee_name']}"
            )

            guidance = get_case_guidance(
                "investor",
                selected_case.get("assignee_role", ""),
                selected_case["status"],
                selected_case["queue"],
            )
            render_investor_case_overview(selected_case)
            render_next_step_box(*guidance)
            render_copilot_panel(*get_investor_copilot_content(selected_case))

            st.markdown("**Suggested next actions**")
            role = selected_case.get("assignee_role", "")
            recommended_action = get_recommended_investor_action(selected_case)
            action_cols = st.columns(3)
            if role == "nb_admin":
                with action_cols[0]:
                    render_recommended_badge(recommended_action == "request_more_documents")
                    if st.button("Ask for more documents", key=f"req_docs_{selected_case['id']}"):
                        set_pending_action(selected_case["id"], "request_more_documents")
                with action_cols[1]:
                    render_recommended_badge(recommended_action == "forward_to_hnw")
                    if st.button("Send to HNW review", key=f"to_hnw_{selected_case['id']}"):
                        set_pending_action(selected_case["id"], "forward_to_hnw")
            elif role == "hnw_reviewer":
                with action_cols[0]:
                    render_recommended_badge(recommended_action == "criteria_met_pending_approval")
                    if st.button("Send for final approval", key=f"pending_approval_{selected_case['id']}"):
                        set_pending_action(selected_case["id"], "criteria_met_pending_approval")
                with action_cols[1]:
                    render_recommended_badge(recommended_action == "reject_case")
                    if st.button("Reject case", key=f"hnw_reject_{selected_case['id']}"):
                        set_pending_action(selected_case["id"], "reject_case")
            elif role == "team_lead":
                with action_cols[0]:
                    render_recommended_badge(recommended_action == "approve_case")
                    if st.button("Approve", key=f"lead_approve_{selected_case['id']}"):
                        set_pending_action(selected_case["id"], "approve_case")
                with action_cols[1]:
                    render_recommended_badge(recommended_action == "reject_case")
                    if st.button("Reject", key=f"lead_reject_{selected_case['id']}"):
                        set_pending_action(selected_case["id"], "reject_case")
            elif role == "policy_admin":
                with action_cols[0]:
                    render_recommended_badge(recommended_action == "mark_tagged")
                    if st.button("Mark as completed", key=f"policy_tag_{selected_case['id']}"):
                        set_pending_action(selected_case["id"], "mark_tagged")

            pending_action = get_pending_action(selected_case["id"])
            if pending_action:
                st.markdown(
                    html_block(
                        f"""
                        <div class="ux-confirm">
                            <strong>Confirm before moving case</strong><br/>
                            You are about to run: {safe_html(pending_action)}
                        </div>
                        """
                    ),
                    unsafe_allow_html=True,
                )
                confirm_col, cancel_col = st.columns(2)
                with confirm_col:
                    if st.button("Confirm action", key=f"confirm_investor_{selected_case['id']}"):
                        confirm_investor_action(selected_case, pending_action)
                with cancel_col:
                    if st.button("Cancel", key=f"cancel_investor_{selected_case['id']}"):
                        clear_pending_action(selected_case["id"])
                        st.rerun()

            with st.expander("Advanced case settings", expanded=False):
                queue_col, owner_col, status_col = st.columns(3)
                with queue_col:
                    new_queue = st.selectbox(
                        "Current step",
                        options=INVESTOR_QUEUE_OPTIONS,
                        index=INVESTOR_QUEUE_OPTIONS.index(selected_case["queue"])
                        if selected_case["queue"] in INVESTOR_QUEUE_OPTIONS
                        else 0,
                        key=f"investor_queue_{selected_case['id']}",
                    )
                with owner_col:
                    available_users = list_users()
                    user_options = {f"{user['name']} ({user['role']})": user for user in available_users}
                    owner_labels = list(user_options.keys())
                    default_owner_index = next(
                        (idx for idx, label in enumerate(owner_labels) if user_options[label]["email"] == selected_case["assignee_email"]),
                        0,
                    )
                    new_owner_label = st.selectbox(
                        "Owner",
                        options=owner_labels,
                        index=default_owner_index,
                        key=f"investor_owner_{selected_case['id']}",
                    )
                with status_col:
                    new_status = st.selectbox(
                        "Status",
                        options=INVESTOR_STATUS_OPTIONS,
                        index=INVESTOR_STATUS_OPTIONS.index(selected_case["status"])
                        if selected_case["status"] in INVESTOR_STATUS_OPTIONS
                        else 0,
                        key=f"investor_status_{selected_case['id']}",
                    )

                if st.button("Save changes", key=f"save_investor_{selected_case['id']}"):
                    updated = update_case(
                        selected_case["id"],
                        assignee_email=user_options[new_owner_label]["email"],
                        queue=new_queue,
                        status=new_status,
                    )
                    if updated:
                        st.success(f"Updated {updated['id']}.")
                    st.rerun()

            with st.expander("Messages and follow-up", expanded=False):
                messages = list_case_messages(selected_case["id"])
                render_conversation_list(messages)

                sender_col, recipient_col = st.columns(2)
                with sender_col:
                    sender_options = list_users() + [{"name": "Client", "email": selected_case["client_email"], "role": "external"}]
                    sender_map = {
                        f"{user['name']} ({user['role']})" if user.get("role") else user["name"]: user for user in sender_options
                    }
                    sender_label = st.selectbox(
                        "From",
                        options=list(sender_map.keys()),
                        key=f"investor_sender_{selected_case['id']}",
                    )
                with recipient_col:
                    recipient = st.text_input(
                        "To",
                        value=selected_case["assignee_email"] or selected_case["client_email"],
                        key=f"investor_recipient_{selected_case['id']}",
                    )

                subject = st.text_input(
                    "Subject",
                    value=f"{selected_case['id']} accredited investor review update",
                    key=f"investor_subject_{selected_case['id']}",
                )
                template_choice = st.selectbox(
                    "Message template",
                    options=["Manual", "Request more documents", "Send for final approval"],
                    key=f"investor_template_{selected_case['id']}",
                )
                template_key = (
                    "request_more_documents"
                    if template_choice == "Request more documents"
                    else "criteria_met_pending_approval"
                    if template_choice == "Send for final approval"
                    else ""
                )
                if template_key:
                    subject = investor_email_template(template_key, selected_case)[0]
                body = st.text_area(
                    "Message",
                    value=investor_email_template(template_key, selected_case)[1] if template_key else "",
                    placeholder="Write the message or internal note here.",
                    key=f"investor_body_{selected_case['id']}",
                )

                if st.button("Add message", key=f"investor_message_{selected_case['id']}") and body.strip():
                    sender = sender_map[sender_label]
                    add_case_message(
                        selected_case["id"],
                        sender_name=sender["name"],
                        sender_email=sender["email"],
                        recipient=recipient,
                        subject=subject,
                        message=body.strip(),
                    )
                    st.success("Message added to workflow thread.")
                    st.rerun()

            with st.expander("Terms used on this page", expanded=False):
                render_glossary("investor")

    with payment_tab:
        st.subheader("USD Payment Review")
        st.caption(
            "Upload TT, MT103, remittance, payment proof PDFs, or receipt images for payment review. "
            "You can also create and move payment cases here."
        )
        st.info(
            "Good case: bank-originated payment proof with a clear printed policy number, amount, and transaction details. "
            "Bad case: handwritten or blurry receipt where OCR may miss or misread the policy number, so staff should manually review it."
        )
        with st.expander("Upload remarks for staff and customers", expanded=True):
            st.write("- Please upload a clear, straight, and full image of the receipt.")
            st.write("- Make sure the policy number, amount, and transaction details are visible.")
            st.write("- Avoid blur, shadows, cropped edges, handwriting over key fields, and folded paper.")
            st.write("- If available, upload the bank-generated receipt or statement instead of a handwritten deposit slip.")
        with st.expander("Before you submit", expanded=False):
            st.write("- Prefer bank-originated proof over handwritten forms.")
            st.write("- Upload the receipt together with the supporting bank Excel or reference file if available.")
            st.write("- OCR is assistive only. Final approval still needs staff review.")
            st.write("- Keep the original uploaded image for audit and follow-up.")
        with st.expander("Examples", expanded=False):
            st.write("- Good upload: clear bank receipt with printed policy number and amount.")
            st.write("- Bad upload: dark, tilted, blurry, cropped, or handwritten receipt.")

        st.markdown("### Start a new review")
        clients = list_clients()
        client_lookup = {f"{client['name']} ({client['email']})": client for client in clients}
        client_choice = st.selectbox("Client", options=list(client_lookup.keys()), key="usd_client")
        selected_client = client_lookup[client_choice]
        expected_amount, expected_reference = st.columns([1, 1])
        with expected_amount:
            amount = st.number_input("Expected amount (USD)", min_value=0.0, value=10000.0, step=100.0)
        with expected_reference:
            reference = st.text_input(
                "Policy/reference number",
                placeholder="POLICY12345",
                help="Required. Enter the expected policy or bank reference even if OCR will also try to find it.",
            )

        payment_files = st.file_uploader(
            "Upload payment documents (PDF, PNG, JPG, JPEG)",
            type=["pdf", "png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key="payment_files",
        )
        st.caption("Tip: clear, upright, uncropped bank receipts usually give the best OCR result.")

        if payment_files:
            documents = analyze_documents(payment_files)
            result = validate_payment_workflow(documents, expected_amount=amount, expected_reference=reference)

            copilot_reasons = list(result["manual_review_reasons"] or result["missing_evidence"])
            if result["status"] == "Review passed":
                recommendation = "Check the insurer USD account. If the funds are there, create the payment case and continue with finance review."
                handoff_label = "Create payment case"
            elif result["status"] == "Needs manual review":
                recommendation = "Review the amount and policy match carefully before moving forward."
                handoff_label = "Review mismatch before creating the case"
            else:
                recommendation = "Ask for corrected payment proof before moving forward."
                handoff_label = "Request corrected proof"

            render_copilot_panel(
                result["summary"],
                recommendation,
                copilot_reasons,
                handoff_label,
            )
            render_usd_workflow_guide()

            metric1, metric2, metric3 = st.columns(3)
            metric1.metric("Best extracted amount", result["fields"]["amount_display"])
            metric2.metric("Reference match", result["fields"]["reference_match"])
            metric3.metric("Best extracted reference", result["fields"]["reference"])

            customer_col, decision_col = st.columns([1, 1.2])
            with customer_col:
                st.markdown("### Customer")
                st.table(
                    [
                        {"Field": "Client in system", "Value": selected_client["name"]},
                        {"Field": "Client email", "Value": selected_client["email"]},
                        {"Field": "Policy number", "Value": reference or "Not entered"},
                    ]
                )
            with decision_col:
                st.markdown("### Decision")
                render_status(result["status"], result["summary"])
                st.table(
                    [
                        {"Field": "Expected amount", "Value": f"USD {amount:,.2f}"},
                        {"Field": "Detected currency", "Value": result["fields"]["currency"]},
                        {"Field": "Extracted amount", "Value": result["fields"]["amount_display"]},
                        {"Field": "Reference match", "Value": result["fields"]["reference_match"]},
                        {"Field": "Extracted reference", "Value": result["fields"]["reference"]},
                        {"Field": "Account owner", "Value": result["fields"]["account_owner"]},
                        {"Field": "Transaction/ref", "Value": result["fields"]["transaction"]},
                    ]
                )

            with st.expander("Show detailed payment evidence", expanded=False):
                render_result(result)

            if st.button("Create payment case", key="create_usd_workflow_case"):
                if not reference.strip():
                    st.error("Policy/reference number is required before creating a payment case.")
                else:
                    case = create_usd_case(
                        client_name=selected_client["name"],
                        client_email=selected_client["email"],
                        policy_number=reference,
                        expected_amount=amount,
                        result=result,
                    )
                    st.success(
                        f"Created case {case['id']} in '{case['queue']}' and assigned it to {case['assignee_name']}."
                    )
                    st.rerun()

        st.divider()
        st.subheader("Open payment cases")
        usd_cases = [case for case in list_cases() if case.get("case_type") == "usd_payment"]
        usd_role_labels = {value: label for value, label in USD_ROLE_VIEWS}
        usd_role_choice = st.selectbox(
            "Role view",
            options=list(usd_role_labels.keys()),
            format_func=lambda value: usd_role_labels[value],
            key="usd_role_view",
        )
        usd_cases = filter_cases_for_role(usd_cases, usd_role_choice)

        if not usd_cases:
            st.info("No payment cases in this role view yet. Create one from the review above or switch the role view.")
        else:
            case_labels = [
                f"{case['id']} | {case.get('policy_number', 'No policy')} | {case['status']} | {case['assignee_name']}"
                for case in usd_cases
            ]
            selected_label = st.selectbox("Choose a case", options=case_labels, key="open_usd_case")
            selected_case = usd_cases[case_labels.index(selected_label)]

            alert_tone = {"high": st.error, "medium": st.warning, "low": st.info}.get(
                selected_case["alert_level"], st.info
            )
            alert_tone(
                f"Priority: {selected_case['alert_level'].upper()} | Current step: {selected_case['queue']} | "
                f"Owner: {selected_case['assignee_name']}"
            )

            guidance = get_case_guidance(
                "usd",
                selected_case.get("assignee_role", ""),
                selected_case["status"],
                selected_case["queue"],
            )
            render_usd_case_overview(selected_case)
            render_next_step_box(*guidance)
            render_copilot_panel(*get_usd_copilot_content(selected_case))

            st.markdown("**Suggested next actions**")
            role = selected_case.get("assignee_role", "")
            recommended_action = get_recommended_usd_action(selected_case)
            action_cols = st.columns(3)
            if role == "finance":
                with action_cols[0]:
                    render_recommended_badge(recommended_action == "funds_sighted")
                    if st.button("Confirm funds received", key=f"funds_sighted_{selected_case['id']}"):
                        set_pending_action(selected_case["id"], "funds_sighted")
                with action_cols[1]:
                    render_recommended_badge(recommended_action == "notify_cashier")
                    if st.button("Notify cashier", key=f"notify_cashier_{selected_case['id']}"):
                        set_pending_action(selected_case["id"], "notify_cashier")
                with action_cols[2]:
                    render_recommended_badge(recommended_action == "reject_payment")
                    if st.button("Reject payment", key=f"reject_usd_{selected_case['id']}"):
                        set_pending_action(selected_case["id"], "reject_payment")
            elif role == "cashier":
                with action_cols[0]:
                    render_recommended_badge(recommended_action == "premium_posted")
                    if st.button("Mark premium as posted", key=f"premium_posted_{selected_case['id']}"):
                        set_pending_action(selected_case["id"], "premium_posted")

            pending_action = get_pending_action(selected_case["id"])
            if pending_action:
                st.markdown(
                    html_block(
                        f"""
                        <div class="ux-confirm">
                            <strong>Confirm before moving case</strong><br/>
                            You are about to run: {safe_html(pending_action)}
                        </div>
                        """
                    ),
                    unsafe_allow_html=True,
                )
                confirm_col, cancel_col = st.columns(2)
                with confirm_col:
                    if st.button("Confirm action", key=f"confirm_usd_{selected_case['id']}"):
                        confirm_usd_action(selected_case, pending_action)
                with cancel_col:
                    if st.button("Cancel", key=f"cancel_usd_{selected_case['id']}"):
                        clear_pending_action(selected_case["id"])
                        st.rerun()

            with st.expander("Advanced case settings", expanded=False):
                queue_col, owner_col, status_col = st.columns(3)
                with queue_col:
                    new_queue = st.selectbox(
                        "Current step",
                        options=USD_QUEUE_OPTIONS,
                        index=USD_QUEUE_OPTIONS.index(selected_case["queue"]) if selected_case["queue"] in USD_QUEUE_OPTIONS else 0,
                        key=f"usd_queue_{selected_case['id']}",
                    )
                with owner_col:
                    available_users = list_users()
                    user_options = {f"{user['name']} ({user['role']})": user for user in available_users}
                    owner_labels = list(user_options.keys())
                    default_owner_index = next(
                        (idx for idx, label in enumerate(owner_labels) if user_options[label]["email"] == selected_case["assignee_email"]),
                        0,
                    )
                    new_owner_label = st.selectbox(
                        "Owner",
                        options=owner_labels,
                        index=default_owner_index,
                        key=f"usd_owner_{selected_case['id']}",
                    )
                with status_col:
                    new_status = st.selectbox(
                        "Status",
                        options=USD_STATUS_OPTIONS,
                        index=USD_STATUS_OPTIONS.index(selected_case["status"]) if selected_case["status"] in USD_STATUS_OPTIONS else 0,
                        key=f"usd_status_{selected_case['id']}",
                    )

                if st.button("Save changes", key=f"save_usd_{selected_case['id']}"):
                    updated = update_case(
                        selected_case["id"],
                        assignee_email=user_options[new_owner_label]["email"],
                        queue=new_queue,
                        status=new_status,
                    )
                    if updated:
                        st.success(f"Updated {updated['id']}.")
                    st.rerun()

            with st.expander("Messages and follow-up", expanded=False):
                messages = list_case_messages(selected_case["id"])
                render_conversation_list(messages)

                sender_col, recipient_col = st.columns(2)
                with sender_col:
                    sender_options = list_users() + [{"name": "Client", "email": selected_case["client_email"], "role": "external"}]
                    sender_map = {
                        f"{user['name']} ({user['role']})" if user.get("role") else user["name"]: user for user in sender_options
                    }
                    sender_label = st.selectbox("From", options=list(sender_map.keys()), key=f"usd_sender_{selected_case['id']}")
                with recipient_col:
                    recipient = st.text_input(
                        "To",
                        value=selected_case["assignee_email"] or selected_case["client_email"],
                        key=f"usd_recipient_{selected_case['id']}",
                    )

                subject = st.text_input(
                    "Subject",
                    value=f"{selected_case['id']} USD payment workflow update",
                    key=f"usd_subject_{selected_case['id']}",
                )
                template_choice = st.selectbox(
                    "Message template",
                    options=["Manual", "Notify cashier to post premium", "Request payment clarification"],
                    key=f"usd_template_{selected_case['id']}",
                )
                template_key = (
                    "notify_cashier"
                    if template_choice == "Notify cashier to post premium"
                    else "request_payment_clarification"
                    if template_choice == "Request payment clarification"
                    else ""
                )
                if template_key:
                    subject = usd_email_template(template_key, selected_case)[0]
                body = st.text_area(
                    "Message",
                    value=usd_email_template(template_key, selected_case)[1] if template_key else "",
                    placeholder="Write the message or internal note here.",
                    key=f"usd_body_{selected_case['id']}",
                )

                if st.button("Add message", key=f"usd_message_{selected_case['id']}") and body.strip():
                    sender = sender_map[sender_label]
                    add_case_message(
                        selected_case["id"],
                        sender_name=sender["name"],
                        sender_email=sender["email"],
                        recipient=recipient,
                        subject=subject,
                        message=body.strip(),
                    )
                    st.success("Message added to USD workflow thread.")
                    st.rerun()

            with st.expander("Terms used on this page", expanded=False):
                render_glossary("usd")


if __name__ == "__main__":
    main()
