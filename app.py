import streamlit as st

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
        [data-testid="stFileUploader"],
        [data-testid="stTextInput"],
        [data-testid="stTextArea"],
        [data-testid="stNumberInput"],
        [data-testid="stSelectbox"] {
            background: transparent;
        }
        .stButton > button {
            background: #0f4c81;
            color: #ffffff;
            border: 1px solid #0f4c81;
            border-radius: 10px;
            padding: 0.6rem 1rem;
            font-weight: 600;
        }
        .stButton > button:hover {
            background: #0c3d68;
            border-color: #0c3d68;
            color: #ffffff;
        }
        .stInfo, .stSuccess, .stWarning, .stError {
            border-radius: 12px;
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
            grid-template-columns: repeat(5, minmax(0, 1fr));
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
        }
        .ux-steps {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0.75rem;
            margin: 0.75rem 0 1rem 0;
        }
        .ux-step {
            background: #ffffff;
            border: 1px solid #d9e2ef;
            border-radius: 14px;
            padding: 0.85rem 0.9rem;
            min-height: 110px;
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
            color: #5a6f8d;
            font-size: 0.82rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }
        .ux-step-title {
            color: #10243f;
            font-size: 1rem;
            font-weight: 700;
            margin-bottom: 0.3rem;
        }
        .ux-step-body {
            color: #42556f;
            font-size: 0.94rem;
            line-height: 1.45;
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
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_panels() -> None:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            """
            <div class="ux-panel">
                <div class="ux-kicker">Workflow</div>
                <div class="ux-title">Accredited Investor Check</div>
                <div class="ux-body">Use this for document intake, AI criteria review, HNW validation, and approval handoff.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            """
            <div class="ux-panel">
                <div class="ux-kicker">Workflow</div>
                <div class="ux-title">USD Payment Check</div>
                <div class="ux-body">Use this for TT, MT103, remittance, and payment-proof review with amount and reference matching.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            """
            <div class="ux-panel">
                <div class="ux-kicker">Review Tip</div>
                <div class="ux-title">Manual Review Still Matters</div>
                <div class="ux-body">OCR can miss values on blurry scans, so key amounts and names should still be confirmed by staff.</div>
            </div>
            """,
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
        st.markdown("### Decision")
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
        ("1", "New", "Case created and waiting for NB admin intake."),
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
    ribbon_html = f"""
    <div class="ux-ribbon">
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Client</div><div class="ux-ribbon-value">{selected_case['client_name']}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Status</div><div class="ux-ribbon-value">{selected_case['status']}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Assignee</div><div class="ux-ribbon-value">{selected_case['assignee_name']}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Last updated</div><div class="ux-ribbon-value">{selected_case.get('updated_at', '-')}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Alert</div><div class="ux-ribbon-value">{selected_case['alert_level'].upper()}</div></div>
    </div>
    """
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
            f"""
            <div class="{css_class}">
                <div class="ux-step-number">Step {number}</div>
                <div class="ux-step-title">{title}</div>
                <div class="ux-step-body">{body}</div>
            </div>
            """
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
                {"Field": "Queue", "Value": selected_case["queue"]},
                {"Field": "Assignee", "Value": selected_case["assignee_name"]},
            ]
        )

    with workflow_col:
        st.markdown("### Workflow notes")
        st.write(f"- Summary: {selected_case['summary']}")
        st.write(f"- Current queue: {selected_case['queue']}")
        if selected_case["manual_review_reasons"]:
            for reason in selected_case["manual_review_reasons"]:
                st.write(f"- {reason}")
        else:
            st.write("- No manual review reasons recorded.")


def render_conversation_list(messages: list[dict]) -> None:
    if not messages:
        st.write("No email thread yet.")
        return

    items = []
    for message in messages:
        preview = message["message"].replace("\n", " ").strip()
        if len(preview) > 140:
            preview = preview[:137] + "..."
        items.append(
            f"""
            <div class="ux-mail-item">
                <div class="ux-mail-head">
                    <div class="ux-mail-from">{message['sender']} to {message['recipient']}</div>
                    <div class="ux-mail-time">{message['timestamp']}</div>
                </div>
                <div class="ux-mail-subject">{message['subject']}</div>
                <div class="ux-mail-preview">{preview}</div>
            </div>
            """
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
    ribbon_html = f"""
    <div class="ux-ribbon">
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Client</div><div class="ux-ribbon-value">{selected_case['client_name']}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Status</div><div class="ux-ribbon-value">{selected_case['status']}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Assignee</div><div class="ux-ribbon-value">{selected_case['assignee_name']}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Last updated</div><div class="ux-ribbon-value">{selected_case.get('updated_at', '-')}</div></div>
        <div class="ux-ribbon-card"><div class="ux-ribbon-label">Alert</div><div class="ux-ribbon-value">{selected_case['alert_level'].upper()}</div></div>
    </div>
    """
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
            f"""
            <div class="{css_class}">
                <div class="ux-step-number">Step {number}</div>
                <div class="ux-step-title">{title}</div>
                <div class="ux-step-body">{body}</div>
            </div>
            """
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
        st.markdown("### Workflow notes")
        st.write(f"- Summary: {selected_case['summary']}")
        st.write(f"- Current queue: {selected_case['queue']}")
        reasons = selected_case.get("manual_review_reasons", [])
        if reasons:
            for reason in reasons:
                st.write(f"- {reason}")
        else:
            st.write("- No manual review reasons recorded.")


def render_guides() -> None:
    seed_workflow_data()
    inject_styles()
    st.title("Insurance Review Assistant")
    st.caption(
        "Assistive review for operations teams. The app highlights extracted evidence and "
        "manual-review triggers; it does not replace HNW validation or team-lead approval."
    )

    st.markdown("### How to use this")
    st.write("- Use **Accredited Investor Check** for documents supporting DBS AI eligibility criteria.")
    st.write("- Use **USD Payment Check** for TT, MT103, remittance, or payment proof PDFs.")
    st.write("- Upload one or more PDFs, then review the extracted fields and evidence snippets.")
    st.write("- For USD payments, enter the expected amount and policy/reference before reviewing the match.")
    st.write("- For Accredited Investor onboarding, use the workflow queue to move cases from NB admin to HNW review, lead approval, and policy tagging.")
    st.write("- Escalate when the app shows missing evidence, low confidence, or conflicting values.")
    render_panels()


def main() -> None:
    render_guides()
    investor_tab, payment_tab = st.tabs(["Accredited Investor Check", "USD Payment Check"])

    with investor_tab:
        st.subheader("Accredited Investor Check")
        st.caption(
            "Upload supporting financial PDFs to review DBS accredited-investor evidence. "
            "This tab also creates and routes workflow cases for NB admin, HNW review, team-lead approval, and policy tagging."
        )

        st.markdown("### Workflow setup")
        clients = list_clients()
        client_lookup = {f"{client['name']} ({client['email']})": client for client in clients}
        client_choice = st.selectbox("Client in system", options=list(client_lookup.keys()), key="investor_client")
        selected_client = client_lookup[client_choice]

        investor_files = st.file_uploader(
            "Upload investor supporting documents (PDF)",
            type=["pdf"],
            accept_multiple_files=True,
            key="investor_files",
        )

        if investor_files:
            documents = analyze_documents(investor_files)
            result = validate_investor_workflow(documents)

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

            if st.button("Create investor workflow case", key="create_investor_workflow_case"):
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
        st.subheader("Accredited investor workflow queue")
        investor_cases = [case for case in list_cases() if case.get("case_type") == "accredited_investor"]

        if not investor_cases:
            st.info("No accredited-investor workflow cases yet. Create one from a review above.")
        else:
            case_labels = [
                f"{case['id']} | {case.get('applicant_name', case['client_name'])} | {case['status']} | {case['assignee_name']}"
                for case in investor_cases
            ]
            selected_label = st.selectbox("Open investor case", options=case_labels, key="open_investor_case")
            selected_case = investor_cases[case_labels.index(selected_label)]

            alert_tone = {"high": st.error, "medium": st.warning, "low": st.info}.get(
                selected_case["alert_level"], st.info
            )
            alert_tone(
                f"Alert: {selected_case['alert_level'].upper()} | Queue: {selected_case['queue']} | "
                f"Assignee: {selected_case['assignee_name']}"
            )

            queue_col, owner_col, status_col = st.columns(3)
            with queue_col:
                new_queue = st.selectbox(
                    "Queue",
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
                    "Assignee",
                    options=owner_labels,
                    index=default_owner_index,
                    key=f"investor_owner_{selected_case['id']}",
                )
            with status_col:
                new_status = st.selectbox(
                    "Case status",
                    options=INVESTOR_STATUS_OPTIONS,
                    index=INVESTOR_STATUS_OPTIONS.index(selected_case["status"])
                    if selected_case["status"] in INVESTOR_STATUS_OPTIONS
                    else 0,
                    key=f"investor_status_{selected_case['id']}",
                )

            if st.button("Save investor case updates", key=f"save_investor_{selected_case['id']}"):
                updated = update_case(
                    selected_case["id"],
                    assignee_email=user_options[new_owner_label]["email"],
                    queue=new_queue,
                    status=new_status,
                )
                if updated:
                    st.success(f"Updated {updated['id']}.")
                st.rerun()

            st.markdown("**Role-based actions**")
            role = selected_case.get("assignee_role", "")
            action_cols = st.columns(3)
            if role == "nb_admin":
                if action_cols[0].button("Request more docs", key=f"req_docs_{selected_case['id']}"):
                    updated, template = apply_investor_action(selected_case, "request_more_documents")
                    if updated and template:
                        add_case_message(
                            selected_case["id"],
                            sender_name=selected_case["assignee_name"],
                            sender_email=selected_case["assignee_email"],
                            recipient=selected_case["client_email"],
                            subject=template[0],
                            message=template[1],
                        )
                        st.success("Requested more documents and logged the template.")
                        st.rerun()
                if action_cols[1].button("Forward to HNW", key=f"to_hnw_{selected_case['id']}"):
                    updated, _ = apply_investor_action(selected_case, "forward_to_hnw")
                    if updated:
                        st.success("Case forwarded to HNW review.")
                        st.rerun()
            elif role == "hnw_reviewer":
                if action_cols[0].button("AI criteria met, pending approval", key=f"pending_approval_{selected_case['id']}"):
                    updated, template = apply_investor_action(selected_case, "criteria_met_pending_approval")
                    if updated and template:
                        add_case_message(
                            selected_case["id"],
                            sender_name=selected_case["assignee_name"],
                            sender_email=selected_case["assignee_email"],
                            recipient=updated["assignee_email"],
                            subject=template[0],
                            message=template[1],
                        )
                        st.success("Forwarded to team lead and logged the approval template.")
                        st.rerun()
                if action_cols[1].button("Reject case", key=f"hnw_reject_{selected_case['id']}"):
                    updated, _ = apply_investor_action(selected_case, "reject_case")
                    if updated:
                        st.success("Case rejected.")
                        st.rerun()
            elif role == "team_lead":
                if action_cols[0].button("Approve", key=f"lead_approve_{selected_case['id']}"):
                    updated, _ = apply_investor_action(selected_case, "approve_case")
                    if updated:
                        st.success("Case approved and sent to policy admin.")
                        st.rerun()
                if action_cols[1].button("Reject", key=f"lead_reject_{selected_case['id']}"):
                    updated, _ = apply_investor_action(selected_case, "reject_case")
                    if updated:
                        st.success("Case rejected.")
                        st.rerun()
            elif role == "policy_admin":
                if action_cols[0].button("Mark tagged in policy system", key=f"policy_tag_{selected_case['id']}"):
                    updated, _ = apply_investor_action(selected_case, "mark_tagged")
                    if updated:
                        st.success("Case marked complete.")
                        st.rerun()

            render_investor_case_overview(selected_case)

            st.markdown("**Email / follow-up thread**")
            messages = list_case_messages(selected_case["id"])
            render_conversation_list(messages)

            sender_col, recipient_col = st.columns(2)
            with sender_col:
                sender_options = list_users() + [{"name": "Client", "email": selected_case["client_email"], "role": "external"}]
                sender_map = {
                    f"{user['name']} ({user['role']})" if user.get("role") else user["name"]: user for user in sender_options
                }
                sender_label = st.selectbox(
                    "Sender",
                    options=list(sender_map.keys()),
                    key=f"investor_sender_{selected_case['id']}",
                )
            with recipient_col:
                recipient = st.text_input(
                    "Recipient",
                    value=selected_case["assignee_email"] or selected_case["client_email"],
                    key=f"investor_recipient_{selected_case['id']}",
                )

            subject = st.text_input(
                "Email subject",
                value=f"{selected_case['id']} accredited investor review update",
                key=f"investor_subject_{selected_case['id']}",
            )
            template_choice = st.selectbox(
                "Email template",
                options=["Manual", "Request more documents", "AI criteria met, pending approval"],
                key=f"investor_template_{selected_case['id']}",
            )
            template_key = (
                "request_more_documents"
                if template_choice == "Request more documents"
                else "criteria_met_pending_approval"
                if template_choice == "AI criteria met, pending approval"
                else ""
            )
            if template_key:
                subject = investor_email_template(template_key, selected_case)[0]
            body = st.text_area(
                "Email body / follow-up note",
                value=investor_email_template(template_key, selected_case)[1] if template_key else "",
                placeholder="Add the follow-up message or internal note here.",
                key=f"investor_body_{selected_case['id']}",
            )

            if st.button("Add message to investor thread", key=f"investor_message_{selected_case['id']}") and body.strip():
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

    with payment_tab:
        st.subheader("USD Payment Check")
        st.caption(
            "Upload TT, MT103, remittance, or payment proof PDFs for policy-payment review. "
            "This tab also supports the finance-to-cashier workflow for USD policies."
        )

        st.markdown("### Workflow setup")
        clients = list_clients()
        client_lookup = {f"{client['name']} ({client['email']})": client for client in clients}
        client_choice = st.selectbox("Client in system", options=list(client_lookup.keys()), key="usd_client")
        selected_client = client_lookup[client_choice]
        expected_amount, expected_reference = st.columns([1, 1])
        with expected_amount:
            amount = st.number_input("Expected amount (USD)", min_value=0.0, value=10000.0, step=100.0)
        with expected_reference:
            reference = st.text_input("Policy/reference number", placeholder="POLICY12345")

        payment_files = st.file_uploader(
            "Upload payment proof documents (PDF)",
            type=["pdf"],
            accept_multiple_files=True,
            key="payment_files",
        )

        if payment_files:
            documents = analyze_documents(payment_files)
            result = validate_payment_workflow(documents, expected_amount=amount, expected_reference=reference)

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
                        {"Field": "Extracted amount", "Value": result["fields"]["amount_display"]},
                        {"Field": "Reference match", "Value": result["fields"]["reference_match"]},
                        {"Field": "Extracted reference", "Value": result["fields"]["reference"]},
                    ]
                )

            with st.expander("Show detailed payment evidence", expanded=False):
                render_result(result)

            if st.button("Create USD workflow case", key="create_usd_workflow_case"):
                if not reference.strip():
                    st.error("Policy/reference number is required before creating a USD workflow case.")
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
        st.subheader("USD payment workflow queue")
        usd_cases = [case for case in list_cases() if case.get("case_type") == "usd_payment"]

        if not usd_cases:
            st.info("No USD workflow cases yet. Create one from a payment review above.")
        else:
            case_labels = [
                f"{case['id']} | {case.get('policy_number', 'No policy')} | {case['status']} | {case['assignee_name']}"
                for case in usd_cases
            ]
            selected_label = st.selectbox("Open USD case", options=case_labels, key="open_usd_case")
            selected_case = usd_cases[case_labels.index(selected_label)]

            alert_tone = {"high": st.error, "medium": st.warning, "low": st.info}.get(
                selected_case["alert_level"], st.info
            )
            alert_tone(
                f"Alert: {selected_case['alert_level'].upper()} | Queue: {selected_case['queue']} | "
                f"Assignee: {selected_case['assignee_name']}"
            )

            queue_col, owner_col, status_col = st.columns(3)
            with queue_col:
                new_queue = st.selectbox(
                    "Queue",
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
                    "Assignee",
                    options=owner_labels,
                    index=default_owner_index,
                    key=f"usd_owner_{selected_case['id']}",
                )
            with status_col:
                new_status = st.selectbox(
                    "Case status",
                    options=USD_STATUS_OPTIONS,
                    index=USD_STATUS_OPTIONS.index(selected_case["status"]) if selected_case["status"] in USD_STATUS_OPTIONS else 0,
                    key=f"usd_status_{selected_case['id']}",
                )

            if st.button("Save USD case updates", key=f"save_usd_{selected_case['id']}"):
                updated = update_case(
                    selected_case["id"],
                    assignee_email=user_options[new_owner_label]["email"],
                    queue=new_queue,
                    status=new_status,
                )
                if updated:
                    st.success(f"Updated {updated['id']}.")
                st.rerun()

            st.markdown("**Role-based actions**")
            role = selected_case.get("assignee_role", "")
            action_cols = st.columns(3)
            if role == "finance":
                if action_cols[0].button("Funds sighted", key=f"funds_sighted_{selected_case['id']}"):
                    updated, _ = apply_usd_action(selected_case, "funds_sighted")
                    if updated:
                        st.success("Finance confirmed funds were sighted.")
                        st.rerun()
                if action_cols[1].button("Notify cashier", key=f"notify_cashier_{selected_case['id']}"):
                    updated, template = apply_usd_action(selected_case, "notify_cashier")
                    if updated and template:
                        add_case_message(
                            selected_case["id"],
                            sender_name=selected_case["assignee_name"],
                            sender_email=selected_case["assignee_email"],
                            recipient=updated["assignee_email"],
                            subject=template[0],
                            message=template[1],
                        )
                        st.success("Cashier notified and email logged.")
                        st.rerun()
                if action_cols[2].button("Reject payment", key=f"reject_usd_{selected_case['id']}"):
                    updated, template = apply_usd_action(selected_case, "reject_payment")
                    if updated and template:
                        add_case_message(
                            selected_case["id"],
                            sender_name=selected_case["assignee_name"],
                            sender_email=selected_case["assignee_email"],
                            recipient=selected_case["client_email"],
                            subject=template[0],
                            message=template[1],
                        )
                        st.success("Payment case rejected and clarification email logged.")
                        st.rerun()
            elif role == "cashier":
                if action_cols[0].button("Premium posted", key=f"premium_posted_{selected_case['id']}"):
                    updated, _ = apply_usd_action(selected_case, "premium_posted")
                    if updated:
                        st.success("Premium marked as posted in policy admin.")
                        st.rerun()

            render_usd_case_overview(selected_case)

            st.markdown("**Email / follow-up thread**")
            messages = list_case_messages(selected_case["id"])
            render_conversation_list(messages)

            sender_col, recipient_col = st.columns(2)
            with sender_col:
                sender_options = list_users() + [{"name": "Client", "email": selected_case["client_email"], "role": "external"}]
                sender_map = {
                    f"{user['name']} ({user['role']})" if user.get("role") else user["name"]: user for user in sender_options
                }
                sender_label = st.selectbox("Sender", options=list(sender_map.keys()), key=f"usd_sender_{selected_case['id']}")
            with recipient_col:
                recipient = st.text_input(
                    "Recipient",
                    value=selected_case["assignee_email"] or selected_case["client_email"],
                    key=f"usd_recipient_{selected_case['id']}",
                )

            subject = st.text_input(
                "Email subject",
                value=f"{selected_case['id']} USD payment workflow update",
                key=f"usd_subject_{selected_case['id']}",
            )
            template_choice = st.selectbox(
                "Email template",
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
                "Email body / follow-up note",
                value=usd_email_template(template_key, selected_case)[1] if template_key else "",
                placeholder="Add the follow-up message or internal note here.",
                key=f"usd_body_{selected_case['id']}",
            )

            if st.button("Add message to USD thread", key=f"usd_message_{selected_case['id']}") and body.strip():
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


if __name__ == "__main__":
    main()
