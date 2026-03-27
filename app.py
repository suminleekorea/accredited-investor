import streamlit as st
from utils.ocr import extract_text
from utils.validator import extract_financials, validate
from utils.payment import extract_payment, validate_payment
from utils.risk import risk_flags

st.set_page_config(page_title="AI Validator", layout="wide")

st.title("🏦 AI Validator System")

file = st.file_uploader("Upload Financial Document (PDF)", type=["pdf"])

if file:
    text = extract_text(file)

    income, net_worth = extract_financials(text)
    decision = validate(income, net_worth)

    col1, col2 = st.columns(2)
    col1.metric("Income", f"${income:,}")
    col2.metric("Net Worth", f"${net_worth:,}")

    if decision == "PASS":
        st.success("✅ Accredited Investor")
    else:
        st.error("❌ Not Qualified")

    # Risk flags
    flags = risk_flags(income, net_worth)
    if flags:
        st.warning("⚠️ Risk Flags")
        for f in flags:
            st.write("-", f)

    # Payment verification
    st.divider()
    st.subheader("💸 Payment Verification")

    expected = st.number_input("Expected Amount (USD)", value=10000)
    actual = extract_payment(text)

    st.write("Extracted Amount:", actual)

    if st.button("Verify Payment"):
        result = validate_payment(expected, actual)
        if result == "MATCH":
            st.success("✅ Payment Verified")
        else:
            st.error("❌ Payment Mismatch")
