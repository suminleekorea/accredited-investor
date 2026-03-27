import streamlit as st

from utils.ocr import analyze_documents
from utils.payment import validate_payment_workflow
from utils.validator import validate_investor_workflow

st.set_page_config(page_title="Insurance Review Assistant", layout="wide")

STATUS_TO_TONE = {
    "Review passed": "success",
    "Needs manual review": "warning",
    "Insufficient evidence": "error",
}


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


def render_guides() -> None:
    st.title("Insurance Review Assistant")
    st.caption(
        "Assistive review for operations teams. The app highlights extracted evidence and "
        "manual-review triggers; it does not replace compliance or approval checks."
    )

    st.markdown("### How to use this")
    st.write("- Use **Accredited Investor Check** for financial-supporting documents.")
    st.write("- Use **USD Payment Check** for TT, MT103, remittance, or payment proof PDFs.")
    st.write("- Upload one or more PDFs, then review the extracted fields and evidence snippets.")
    st.write("- Escalate when the app shows missing evidence, low confidence, or conflicting values.")

    card1, card2, card3 = st.columns(3)
    with card1:
        st.info(
            "**Accredited Investor Check**\n\n"
            "Looks for applicant name, annual income, net worth, and financial-document signals."
        )
    with card2:
        st.info(
            "**USD Payment Check**\n\n"
            "Looks for currency, remittance amount, policy/reference number, and payment-proof signals."
        )
    with card3:
        st.info(
            "**Why OCR may still need manual review**\n\n"
            "Scanned PDFs can contain blurry text, cut-off fields, or OCR errors that change numbers."
        )


def main() -> None:
    render_guides()
    investor_tab, payment_tab = st.tabs(["Accredited Investor Check", "USD Payment Check"])

    with investor_tab:
        st.subheader("Accredited Investor Check")
        st.caption("Upload supporting financial PDFs to review income and net-worth evidence.")

        investor_files = st.file_uploader(
            "Upload investor supporting documents (PDF)",
            type=["pdf"],
            accept_multiple_files=True,
            key="investor_files",
        )

        if investor_files:
            documents = analyze_documents(investor_files)
            result = validate_investor_workflow(documents)

            metric1, metric2 = st.columns(2)
            metric1.metric("Best annual income", result["fields"]["annual_income_display"])
            metric2.metric("Best net worth", result["fields"]["net_worth_display"])

            render_result(result)

    with payment_tab:
        st.subheader("USD Payment Check")
        st.caption("Upload TT, MT103, remittance, or payment proof PDFs for policy-payment review.")

        expected_amount, expected_reference = st.columns([1, 1])
        with expected_amount:
            amount = st.number_input("Expected amount (USD)", min_value=0.0, value=10000.0, step=100.0)
        with expected_reference:
            reference = st.text_input("Expected policy/reference", placeholder="Policy12345")

        payment_files = st.file_uploader(
            "Upload payment proof documents (PDF)",
            type=["pdf"],
            accept_multiple_files=True,
            key="payment_files",
        )

        if payment_files:
            documents = analyze_documents(payment_files)
            result = validate_payment_workflow(documents, expected_amount=amount, expected_reference=reference)

            metric1, metric2 = st.columns(2)
            metric1.metric("Best extracted amount", result["fields"]["amount_display"])
            metric2.metric("Reference match", result["fields"]["reference_match"])

            render_result(result)


if __name__ == "__main__":
    main()
