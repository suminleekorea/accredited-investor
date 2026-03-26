import streamlit as st
import json
import os
import base64
import uuid
import datetime
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from openai import OpenAI

# ─────────────────────────────────────────────
# CONFIG & CONSTANTS
# ─────────────────────────────────────────────
DATA_FILE = "data/clients.json"
USERS_FILE = "data/users.json"
UPLOAD_DIR = "uploads"

MAS_INCOME_THRESHOLD = 300_000
MAS_FINANCIAL_ASSETS_THRESHOLD = 1_000_000
MAS_PERSONAL_ASSETS_THRESHOLD = 2_000_000
MAS_RESIDENCE_CAP = 1_000_000

CRITERIA_LABELS = {
    "income": "Criterion 1 – Annual Income ≥ SGD 300,000",
    "financial_assets": "Criterion 2 – Net Financial Assets ≥ SGD 1,000,000",
    "personal_assets": "Criterion 3 – Net Personal Assets ≥ SGD 2,000,000",
}

DOCUMENT_TYPES = {
    "income": ["IRAS Notice of Assessment (NOA)", "Payslips (last 3 months)", "Employment Letter"],
    "financial_assets": ["Bank Statement", "Brokerage Account Statement", "CDP Portfolio Statement"],
    "personal_assets": ["Property Title Deed", "Housing Loan Statement", "Valuation Certificate", "Bank Statement"],
}

STATUS_COLORS = {
    "Draft": "🟡",
    "Pending Approval": "🔵",
    "Approved": "🟢",
    "Rejected": "🔴",
}

# ─────────────────────────────────────────────
# DATA HELPERS
# ─────────────────────────────────────────────
def load_data(filepath, default):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return default

def save_data(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)

def get_clients():
    return load_data(DATA_FILE, {})

def save_clients(clients):
    save_data(DATA_FILE, clients)

def get_users():
    default_users = {
        "rm_alice": {"name": "Alice Tan", "password": "password123", "role": "RM", "email": "alice@insurer.sg"},
        "rm_bob": {"name": "Bob Lim", "password": "password123", "role": "RM", "email": "bob@insurer.sg"},
        "compliance_carol": {"name": "Carol Wong", "password": "password123", "role": "Compliance", "email": "carol@insurer.sg"},
        "admin_alvin": {"name": "Alvin IT", "password": "admin123", "role": "Admin", "email": "alvin@insurer.sg"},
    }
    return load_data(USERS_FILE, default_users)

# ─────────────────────────────────────────────
# OCR / AI EXTRACTION
# ─────────────────────────────────────────────
def extract_financial_data_with_ai(file_bytes, filename, criterion_type):
    """Use OpenAI Vision API to extract financial figures from uploaded documents."""
    try:
        client = OpenAI()
        
        # Encode image to base64
        b64 = base64.b64encode(file_bytes).decode("utf-8")
        
        # Determine file type
        ext = filename.lower().split(".")[-1]
        if ext in ["jpg", "jpeg"]:
            media_type = "image/jpeg"
        elif ext == "png":
            media_type = "image/png"
        elif ext == "pdf":
            # For PDFs, we'll use text extraction prompt
            media_type = "image/jpeg"  # fallback
        else:
            media_type = "image/jpeg"
        
        criterion_hints = {
            "income": "annual income, total income, gross income, salary, NOA income amount",
            "financial_assets": "total balance, net assets, portfolio value, account balance, total financial assets",
            "personal_assets": "property value, net equity, total assets, valuation amount",
        }
        
        prompt = f"""You are an expert financial document analyzer for a Singapore insurance company.
Analyze this document and extract the following information:
1. Document type (e.g., NOA, payslip, bank statement, etc.)
2. Client/Account holder name
3. Document date or period
4. The key financial figure relevant to: {criterion_hints.get(criterion_type, 'financial value')}
5. Currency (SGD, USD, etc.)
6. The extracted numeric value (just the number, no commas or currency symbols)

Respond in this exact JSON format:
{{
  "document_type": "...",
  "client_name": "...",
  "document_date": "...",
  "currency": "SGD",
  "extracted_value": 0,
  "description": "Brief description of what was found",
  "confidence": "high/medium/low"
}}

If you cannot determine a value, use 0 for extracted_value and "low" for confidence.
Only respond with the JSON, no other text."""

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{b64}",
                                "detail": "high"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ],
            max_tokens=500
        )
        
        result_text = response.choices[0].message.content.strip()
        # Clean JSON
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()
        
        result = json.loads(result_text)
        return result
        
    except Exception as e:
        return {
            "document_type": "Unknown",
            "client_name": "Unable to extract",
            "document_date": "Unknown",
            "currency": "SGD",
            "extracted_value": 0,
            "description": f"OCR extraction failed: {str(e)}",
            "confidence": "low"
        }

# ─────────────────────────────────────────────
# CRITERIA EVALUATION ENGINE
# ─────────────────────────────────────────────
def evaluate_criteria(client_data):
    """Evaluate MAS AI criteria based on extracted document data."""
    results = {
        "income": {"met": False, "value": 0, "threshold": MAS_INCOME_THRESHOLD, "documents": []},
        "financial_assets": {"met": False, "value": 0, "threshold": MAS_FINANCIAL_ASSETS_THRESHOLD, "documents": []},
        "personal_assets": {"met": False, "value": 0, "threshold": MAS_PERSONAL_ASSETS_THRESHOLD, "documents": []},
    }
    
    documents = client_data.get("documents", [])
    
    for doc in documents:
        criterion = doc.get("criterion_type")
        value = doc.get("extracted_value", 0)
        
        if criterion in results:
            results[criterion]["value"] = max(results[criterion]["value"], value)
            results[criterion]["documents"].append(doc.get("filename", "Unknown"))
    
    # Apply thresholds
    results["income"]["met"] = results["income"]["value"] >= MAS_INCOME_THRESHOLD
    results["financial_assets"]["met"] = results["financial_assets"]["value"] >= MAS_FINANCIAL_ASSETS_THRESHOLD
    results["personal_assets"]["met"] = results["personal_assets"]["value"] >= MAS_PERSONAL_ASSETS_THRESHOLD
    
    # Overall eligibility
    any_met = any(r["met"] for r in results.values())
    
    return results, any_met

# ─────────────────────────────────────────────
# EMAIL WORKFLOW
# ─────────────────────────────────────────────
def send_approval_email(client_data, approver_email, submitter_name, criteria_results, overall_eligible):
    """Send approval request email to compliance team."""
    try:
        client_name = client_data.get("client_name", "Unknown Client")
        client_id = client_data.get("id", "N/A")
        
        status_text = "✅ SYSTEM RECOMMENDS: ELIGIBLE" if overall_eligible else "⚠️ SYSTEM RECOMMENDS: PENDING MANUAL REVIEW"
        
        criteria_html = ""
        for crit_key, crit_data in criteria_results.items():
            label = CRITERIA_LABELS[crit_key]
            value = crit_data["value"]
            threshold = crit_data["threshold"]
            met = crit_data["met"]
            icon = "✅" if met else "❌"
            criteria_html += f"""
            <tr>
                <td style="padding:8px; border:1px solid #ddd;">{label}</td>
                <td style="padding:8px; border:1px solid #ddd;">SGD {value:,.0f}</td>
                <td style="padding:8px; border:1px solid #ddd;">SGD {threshold:,.0f}</td>
                <td style="padding:8px; border:1px solid #ddd;">{icon} {'Met' if met else 'Not Met'}</td>
            </tr>"""
        
        html_body = f"""
        <html><body style="font-family: Arial, sans-serif; max-width:700px; margin:auto;">
        <div style="background:#1a3a5c; color:white; padding:20px; border-radius:8px 8px 0 0;">
            <h2>🏦 AI Validator — Approval Request</h2>
            <p>Submitted by: <strong>{submitter_name}</strong> | {datetime.datetime.now().strftime('%d %b %Y, %H:%M')}</p>
        </div>
        <div style="background:#f8f9fa; padding:20px; border:1px solid #ddd;">
            <h3>Client Information</h3>
            <p><strong>Client Name:</strong> {client_name}</p>
            <p><strong>Case ID:</strong> {client_id}</p>
            <p><strong>NRIC/Passport:</strong> {client_data.get('nric', 'N/A')}</p>
            <p><strong>Nationality:</strong> {client_data.get('nationality', 'N/A')}</p>
        </div>
        <div style="padding:20px; border:1px solid #ddd; border-top:none;">
            <h3>MAS Criteria Evaluation Results</h3>
            <table style="width:100%; border-collapse:collapse;">
                <tr style="background:#1a3a5c; color:white;">
                    <th style="padding:8px; text-align:left;">Criterion</th>
                    <th style="padding:8px; text-align:left;">Extracted Value</th>
                    <th style="padding:8px; text-align:left;">Threshold</th>
                    <th style="padding:8px; text-align:left;">Status</th>
                </tr>
                {criteria_html}
            </table>
        </div>
        <div style="padding:20px; background:#e8f4f8; border:1px solid #ddd; border-top:none;">
            <h3>{status_text}</h3>
            <p>Please log in to the AI Validator system to review the uploaded documents and make your final decision.</p>
            <p style="color:#666; font-size:12px;">This is an automated notification from the AI Validator System. Please do not reply to this email.</p>
        </div>
        </body></html>
        """
        
        # Use a simple SMTP approach (for demo, we log the email)
        # In production, configure with actual SMTP server
        email_log = {
            "to": approver_email,
            "subject": f"[AI Validator] Approval Required: {client_name} (Case {client_id})",
            "body": html_body,
            "sent_at": datetime.datetime.now().isoformat(),
            "status": "logged"
        }
        
        # Save email log
        email_logs = load_data("data/email_logs.json", [])
        email_logs.append(email_log)
        save_data("data/email_logs.json", email_logs)
        
        return True, "Email notification logged successfully (demo mode)"
        
    except Exception as e:
        return False, str(e)

# ─────────────────────────────────────────────
# PAGE FUNCTIONS
# ─────────────────────────────────────────────
def login_page():
    st.markdown("""
    <div style="text-align:center; padding:40px 0 20px 0;">
        <h1 style="color:#1a3a5c; font-size:2.2rem;">🏦 AI Validator</h1>
        <p style="color:#555; font-size:1.1rem;">Singapore MAS Accredited Investor Validation System</p>
        <p style="color:#888; font-size:0.9rem;">Internal Use Only — Powered by Alvin IT</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Sign In")
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="e.g. rm_alice")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)
            
            if submitted:
                users = get_users()
                if username in users and users[username]["password"] == password:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username
                    st.session_state["user"] = users[username]
                    st.session_state["page"] = "dashboard"
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
        
        st.markdown("---")
        st.markdown("""
        **Demo Accounts:**
        | Username | Password | Role |
        |----------|----------|------|
        | rm_alice | password123 | Relationship Manager |
        | rm_bob | password123 | Relationship Manager |
        | compliance_carol | password123 | Compliance |
        | admin_alvin | admin123 | Admin |
        """)

def dashboard_page():
    user = st.session_state["user"]
    clients = get_clients()
    
    st.markdown(f"## 📊 Dashboard — Welcome, {user['name']}")
    st.markdown(f"**Role:** {user['role']} | **Email:** {user['email']}")
    st.divider()
    
    # Stats
    total = len(clients)
    approved = sum(1 for c in clients.values() if c.get("status") == "Approved")
    pending = sum(1 for c in clients.values() if c.get("status") == "Pending Approval")
    rejected = sum(1 for c in clients.values() if c.get("status") == "Rejected")
    draft = sum(1 for c in clients.values() if c.get("status") == "Draft")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Cases", total)
    col2.metric("🟡 Draft", draft)
    col3.metric("🔵 Pending", pending)
    col4.metric("🟢 Approved", approved)
    col5.metric("🔴 Rejected", rejected)
    
    st.divider()
    
    # Recent cases
    st.markdown("### Recent Cases")
    if not clients:
        st.info("No cases yet. Create a new client case to get started.")
    else:
        for cid, c in list(clients.items())[-10:]:
            status_icon = STATUS_COLORS.get(c.get("status", "Draft"), "⚪")
            col_a, col_b, col_c, col_d, col_e = st.columns([3, 2, 2, 2, 1])
            col_a.write(f"**{c.get('client_name', 'N/A')}**")
            col_b.write(c.get("nric", "N/A"))
            col_c.write(f"{status_icon} {c.get('status', 'Draft')}")
            col_d.write(c.get("created_at", "N/A")[:10])
            if col_e.button("View", key=f"view_{cid}"):
                st.session_state["selected_client_id"] = cid
                st.session_state["page"] = "client_detail"
                st.rerun()

def new_client_page():
    st.markdown("## ➕ New Client Case")
    st.divider()
    
    with st.form("new_client_form"):
        col1, col2 = st.columns(2)
        with col1:
            client_name = st.text_input("Full Name *", placeholder="e.g. John Tan Wei Ming")
            nric = st.text_input("NRIC / Passport No. *", placeholder="e.g. S1234567A")
            dob = st.date_input("Date of Birth")
        with col2:
            nationality = st.selectbox("Nationality", ["Singaporean", "Singapore PR", "Foreigner"])
            email = st.text_input("Client Email", placeholder="client@email.com")
            phone = st.text_input("Phone Number", placeholder="+65 9XXX XXXX")
        
        notes = st.text_area("Notes / Remarks", placeholder="Any additional notes...")
        submitted = st.form_submit_button("Create Case", use_container_width=True)
        
        if submitted:
            if not client_name or not nric:
                st.error("Full Name and NRIC are required.")
            else:
                clients = get_clients()
                cid = str(uuid.uuid4())[:8].upper()
                clients[cid] = {
                    "id": cid,
                    "client_name": client_name,
                    "nric": nric,
                    "dob": str(dob),
                    "nationality": nationality,
                    "email": email,
                    "phone": phone,
                    "notes": notes,
                    "status": "Draft",
                    "documents": [],
                    "criteria_results": {},
                    "overall_eligible": False,
                    "created_by": st.session_state["username"],
                    "created_at": datetime.datetime.now().isoformat(),
                    "updated_at": datetime.datetime.now().isoformat(),
                    "approval_history": []
                }
                save_clients(clients)
                st.success(f"✅ Client case created! Case ID: **{cid}**")
                st.session_state["selected_client_id"] = cid
                st.session_state["page"] = "client_detail"
                st.rerun()

def client_detail_page():
    cid = st.session_state.get("selected_client_id")
    clients = get_clients()
    
    if not cid or cid not in clients:
        st.error("Client not found.")
        return
    
    client = clients[cid]
    user = st.session_state["user"]
    
    st.markdown(f"## 👤 {client['client_name']}")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Case ID", client["id"])
    col2.metric("Status", f"{STATUS_COLORS.get(client.get('status','Draft'), '⚪')} {client.get('status','Draft')}")
    col3.metric("Created", client.get("created_at", "N/A")[:10])
    
    st.divider()
    
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Client Info", "📄 Documents & OCR", "📊 Criteria Evaluation", "📧 Approval Workflow"])
    
    # ── TAB 1: Client Info ──
    with tab1:
        st.markdown("### Client Information")
        col_a, col_b = st.columns(2)
        with col_a:
            st.write(f"**NRIC/Passport:** {client.get('nric', 'N/A')}")
            st.write(f"**Date of Birth:** {client.get('dob', 'N/A')}")
            st.write(f"**Nationality:** {client.get('nationality', 'N/A')}")
        with col_b:
            st.write(f"**Email:** {client.get('email', 'N/A')}")
            st.write(f"**Phone:** {client.get('phone', 'N/A')}")
            st.write(f"**Created by:** {client.get('created_by', 'N/A')}")
        
        if client.get("notes"):
            st.markdown(f"**Notes:** {client['notes']}")
    
    # ── TAB 2: Documents & OCR ──
    with tab2:
        st.markdown("### Upload Supporting Documents")
        st.info("Upload financial documents. The system will automatically extract key financial figures using AI-powered OCR.")
        
        col_u1, col_u2 = st.columns(2)
        with col_u1:
            criterion_type = st.selectbox(
                "Document Category",
                options=list(CRITERIA_LABELS.keys()),
                format_func=lambda x: CRITERIA_LABELS[x]
            )
        with col_u2:
            doc_type = st.selectbox(
                "Document Type",
                options=DOCUMENT_TYPES[criterion_type]
            )
        
        uploaded_file = st.file_uploader(
            "Upload Document (PDF, JPG, PNG)",
            type=["pdf", "jpg", "jpeg", "png"],
            key=f"upload_{cid}"
        )
        
        if uploaded_file and st.button("🔍 Extract & Analyze", use_container_width=True):
            with st.spinner("Running AI-powered OCR analysis..."):
                file_bytes = uploaded_file.read()
                
                # Save file
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                save_path = os.path.join(UPLOAD_DIR, f"{cid}_{uploaded_file.name}")
                with open(save_path, "wb") as f:
                    f.write(file_bytes)
                
                # Run OCR
                ocr_result = extract_financial_data_with_ai(file_bytes, uploaded_file.name, criterion_type)
                
                # Store document
                doc_entry = {
                    "doc_id": str(uuid.uuid4())[:8],
                    "filename": uploaded_file.name,
                    "doc_type": doc_type,
                    "criterion_type": criterion_type,
                    "extracted_value": ocr_result.get("extracted_value", 0),
                    "currency": ocr_result.get("currency", "SGD"),
                    "document_date": ocr_result.get("document_date", "Unknown"),
                    "client_name_on_doc": ocr_result.get("client_name", "Unknown"),
                    "description": ocr_result.get("description", ""),
                    "confidence": ocr_result.get("confidence", "low"),
                    "document_type_detected": ocr_result.get("document_type", "Unknown"),
                    "uploaded_at": datetime.datetime.now().isoformat(),
                    "uploaded_by": st.session_state["username"]
                }
                
                clients[cid]["documents"].append(doc_entry)
                clients[cid]["updated_at"] = datetime.datetime.now().isoformat()
                
                # Re-evaluate criteria
                criteria_results, overall_eligible = evaluate_criteria(clients[cid])
                clients[cid]["criteria_results"] = criteria_results
                clients[cid]["overall_eligible"] = overall_eligible
                
                save_clients(clients)
                
                # Show result
                st.success("✅ Document analyzed successfully!")
                
                conf_color = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(ocr_result.get("confidence", "low"), "⚪")
                st.markdown(f"""
                **OCR Extraction Results:**
                - **Document Type Detected:** {ocr_result.get('document_type', 'N/A')}
                - **Name on Document:** {ocr_result.get('client_name', 'N/A')}
                - **Document Date:** {ocr_result.get('document_date', 'N/A')}
                - **Extracted Value:** {ocr_result.get('currency', 'SGD')} {ocr_result.get('extracted_value', 0):,.0f}
                - **Description:** {ocr_result.get('description', 'N/A')}
                - **Confidence:** {conf_color} {ocr_result.get('confidence', 'N/A').upper()}
                """)
                
                st.rerun()
        
        # Show uploaded documents
        st.divider()
        st.markdown("### Uploaded Documents")
        
        # Reload client data
        clients = get_clients()
        client = clients[cid]
        
        if not client.get("documents"):
            st.info("No documents uploaded yet.")
        else:
            for doc in client["documents"]:
                conf_color = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(doc.get("confidence", "low"), "⚪")
                with st.expander(f"📄 {doc['filename']} — {CRITERIA_LABELS[doc['criterion_type']]}"):
                    col_d1, col_d2 = st.columns(2)
                    with col_d1:
                        st.write(f"**Document Type:** {doc.get('document_type_detected', 'N/A')}")
                        st.write(f"**Doc Category:** {doc.get('doc_type', 'N/A')}")
                        st.write(f"**Date on Document:** {doc.get('document_date', 'N/A')}")
                    with col_d2:
                        st.write(f"**Extracted Value:** {doc.get('currency', 'SGD')} {doc.get('extracted_value', 0):,.0f}")
                        st.write(f"**Confidence:** {conf_color} {doc.get('confidence', 'N/A').upper()}")
                        st.write(f"**Uploaded:** {doc.get('uploaded_at', 'N/A')[:10]}")
                    st.write(f"**Description:** {doc.get('description', 'N/A')}")
    
    # ── TAB 3: Criteria Evaluation ──
    with tab3:
        st.markdown("### MAS AI Criteria Evaluation")
        
        # Reload
        clients = get_clients()
        client = clients[cid]
        
        criteria_results, overall_eligible = evaluate_criteria(client)
        
        if not client.get("documents"):
            st.warning("Please upload documents first to run the evaluation.")
        else:
            # Overall result
            if overall_eligible:
                st.success("## ✅ ELIGIBLE — Accredited Investor Status Recommended")
                st.write("The client meets at least one of the MAS AI criteria based on the uploaded documents.")
            else:
                st.error("## ❌ NOT ELIGIBLE — Manual Review Required")
                st.write("The client does not meet any of the MAS AI criteria based on the current documents. Please review and upload additional supporting documents.")
            
            st.divider()
            
            for crit_key, crit_data in criteria_results.items():
                label = CRITERIA_LABELS[crit_key]
                value = crit_data["value"]
                threshold = crit_data["threshold"]
                met = crit_data["met"]
                docs = crit_data["documents"]
                
                progress = min(value / threshold, 1.0) if threshold > 0 else 0
                
                if met:
                    st.markdown(f"### ✅ {label}")
                    st.success(f"**SGD {value:,.0f}** ≥ threshold SGD {threshold:,.0f}")
                else:
                    st.markdown(f"### ❌ {label}")
                    st.error(f"**SGD {value:,.0f}** < threshold SGD {threshold:,.0f}")
                
                st.progress(progress, text=f"{progress*100:.0f}% of threshold")
                
                if docs:
                    st.write(f"*Supporting documents: {', '.join(docs)}*")
                else:
                    st.write("*No documents uploaded for this criterion.*")
                
                st.divider()
    
    # ── TAB 4: Approval Workflow ──
    with tab4:
        st.markdown("### Approval Workflow")
        
        # Reload
        clients = get_clients()
        client = clients[cid]
        
        current_status = client.get("status", "Draft")
        
        st.markdown(f"**Current Status:** {STATUS_COLORS.get(current_status, '⚪')} **{current_status}**")
        st.divider()
        
        # RM Actions
        if user["role"] == "RM":
            if current_status == "Draft":
                if not client.get("documents"):
                    st.warning("Please upload at least one document before submitting for approval.")
                else:
                    st.markdown("#### Submit for Approval")
                    st.write("Once submitted, a notification email will be sent to the Compliance team for review.")
                    
                    approver_email = st.text_input("Approver Email", value="compliance_carol@insurer.sg")
                    
                    if st.button("📧 Submit for Approval", use_container_width=True, type="primary"):
                        criteria_results, overall_eligible = evaluate_criteria(client)
                        
                        # Send email
                        success, msg = send_approval_email(
                            client, approver_email, 
                            user["name"], criteria_results, overall_eligible
                        )
                        
                        if success:
                            clients[cid]["status"] = "Pending Approval"
                            clients[cid]["submitted_at"] = datetime.datetime.now().isoformat()
                            clients[cid]["submitted_by"] = st.session_state["username"]
                            clients[cid]["approval_history"].append({
                                "action": "Submitted for Approval",
                                "by": user["name"],
                                "at": datetime.datetime.now().isoformat(),
                                "note": f"Submitted to {approver_email}"
                            })
                            save_clients(clients)
                            st.success(f"✅ Submitted! Email notification sent to {approver_email}")
                            st.rerun()
                        else:
                            st.error(f"Submission failed: {msg}")
            
            elif current_status == "Pending Approval":
                st.info("🔵 This case is pending approval from the Compliance team.")
            
            elif current_status == "Approved":
                st.success("🟢 This case has been approved.")
            
            elif current_status == "Rejected":
                st.error("🔴 This case has been rejected. Please review and resubmit.")
                if st.button("🔄 Reset to Draft", use_container_width=True):
                    clients[cid]["status"] = "Draft"
                    clients[cid]["approval_history"].append({
                        "action": "Reset to Draft",
                        "by": user["name"],
                        "at": datetime.datetime.now().isoformat()
                    })
                    save_clients(clients)
                    st.rerun()
        
        # Compliance Actions
        elif user["role"] == "Compliance":
            if current_status == "Pending Approval":
                st.markdown("#### Review & Decision")
                
                criteria_results, overall_eligible = evaluate_criteria(client)
                
                if overall_eligible:
                    st.success("System Recommendation: ✅ ELIGIBLE")
                else:
                    st.warning("System Recommendation: ⚠️ PENDING MANUAL REVIEW")
                
                col_approve, col_reject = st.columns(2)
                
                with col_approve:
                    approval_note = st.text_area("Approval Note", placeholder="e.g. All documents verified. Income criterion met.")
                    if st.button("✅ Approve", use_container_width=True, type="primary"):
                        clients[cid]["status"] = "Approved"
                        clients[cid]["approved_at"] = datetime.datetime.now().isoformat()
                        clients[cid]["approved_by"] = user["name"]
                        clients[cid]["approval_history"].append({
                            "action": "Approved",
                            "by": user["name"],
                            "at": datetime.datetime.now().isoformat(),
                            "note": approval_note
                        })
                        save_clients(clients)
                        st.success("✅ Case approved!")
                        st.rerun()
                
                with col_reject:
                    rejection_note = st.text_area("Rejection Reason", placeholder="e.g. Documents insufficient. Please provide latest NOA.")
                    if st.button("❌ Reject", use_container_width=True):
                        clients[cid]["status"] = "Rejected"
                        clients[cid]["rejected_at"] = datetime.datetime.now().isoformat()
                        clients[cid]["rejected_by"] = user["name"]
                        clients[cid]["approval_history"].append({
                            "action": "Rejected",
                            "by": user["name"],
                            "at": datetime.datetime.now().isoformat(),
                            "note": rejection_note
                        })
                        save_clients(clients)
                        st.error("❌ Case rejected.")
                        st.rerun()
            else:
                st.info(f"No action required. Current status: {current_status}")
        
        # Approval History
        st.divider()
        st.markdown("#### Approval History")
        history = client.get("approval_history", [])
        if not history:
            st.info("No history yet.")
        else:
            for h in reversed(history):
                icon = {"Approved": "✅", "Rejected": "❌", "Submitted for Approval": "📧", "Reset to Draft": "🔄"}.get(h["action"], "📝")
                st.write(f"{icon} **{h['action']}** — by {h['by']} on {h['at'][:10]}")
                if h.get("note"):
                    st.write(f"   *Note: {h['note']}*")

def all_clients_page():
    clients = get_clients()
    user = st.session_state["user"]
    
    st.markdown("## 📁 All Client Cases")
    st.divider()
    
    # Filters
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        status_filter = st.selectbox("Filter by Status", ["All", "Draft", "Pending Approval", "Approved", "Rejected"])
    with col_f2:
        search_name = st.text_input("Search by Name", placeholder="Client name...")
    with col_f3:
        st.write("")
    
    st.divider()
    
    if not clients:
        st.info("No cases found.")
        return
    
    filtered = {
        cid: c for cid, c in clients.items()
        if (status_filter == "All" or c.get("status") == status_filter)
        and (not search_name or search_name.lower() in c.get("client_name", "").lower())
    }
    
    if not filtered:
        st.info("No cases match the filter.")
        return
    
    # Table header
    cols = st.columns([3, 2, 2, 2, 2, 1])
    cols[0].markdown("**Client Name**")
    cols[1].markdown("**NRIC**")
    cols[2].markdown("**Status**")
    cols[3].markdown("**Docs**")
    cols[4].markdown("**Created**")
    cols[5].markdown("**Action**")
    st.divider()
    
    for cid, c in filtered.items():
        cols = st.columns([3, 2, 2, 2, 2, 1])
        cols[0].write(c.get("client_name", "N/A"))
        cols[1].write(c.get("nric", "N/A"))
        status_icon = STATUS_COLORS.get(c.get("status", "Draft"), "⚪")
        cols[2].write(f"{status_icon} {c.get('status', 'Draft')}")
        cols[3].write(str(len(c.get("documents", []))))
        cols[4].write(c.get("created_at", "N/A")[:10])
        if cols[5].button("Open", key=f"open_{cid}"):
            st.session_state["selected_client_id"] = cid
            st.session_state["page"] = "client_detail"
            st.rerun()

def email_log_page():
    st.markdown("## 📧 Email Notification Log")
    st.divider()
    
    email_logs = load_data("data/email_logs.json", [])
    
    if not email_logs:
        st.info("No email notifications sent yet.")
        return
    
    for log in reversed(email_logs):
        with st.expander(f"📧 {log.get('subject', 'N/A')} — {log.get('sent_at', 'N/A')[:10]}"):
            st.write(f"**To:** {log.get('to', 'N/A')}")
            st.write(f"**Sent At:** {log.get('sent_at', 'N/A')}")
            st.write(f"**Status:** {log.get('status', 'N/A')}")
            st.markdown("**Email Preview:**")
            st.components.v1.html(log.get("body", ""), height=400, scrolling=True)

def admin_page():
    st.markdown("## ⚙️ Admin Panel")
    st.divider()
    
    users = get_users()
    
    st.markdown("### User Management")
    for username, u in users.items():
        col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
        col1.write(f"**{u['name']}**")
        col2.write(f"@{username}")
        col3.write(f"Role: {u['role']}")
        col4.write(f"Email: {u['email']}")
    
    st.divider()
    st.markdown("### System Statistics")
    clients = get_clients()
    st.write(f"Total client cases: **{len(clients)}**")
    
    email_logs = load_data("data/email_logs.json", [])
    st.write(f"Total email notifications: **{len(email_logs)}**")
    
    st.divider()
    st.markdown("### MAS AI Thresholds (Current Configuration)")
    st.table({
        "Criterion": ["Income", "Net Financial Assets", "Net Personal Assets"],
        "Threshold (SGD)": [f"{MAS_INCOME_THRESHOLD:,}", f"{MAS_FINANCIAL_ASSETS_THRESHOLD:,}", f"{MAS_PERSONAL_ASSETS_THRESHOLD:,}"],
        "Primary Residence Cap": ["N/A", "N/A", f"{MAS_RESIDENCE_CAP:,}"]
    })

# ─────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="AI Validator — MAS Accredited Investor System",
        page_icon="🏦",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS
    st.markdown("""
    <style>
    .stApp { background-color: #f0f4f8; }
    .stSidebar { background-color: #1a3a5c !important; }
    .stSidebar .stMarkdown { color: white !important; }
    .stSidebar .stSelectbox label { color: white !important; }
    div[data-testid="metric-container"] {
        background-color: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 15px;
    }
    .stButton > button {
        border-radius: 6px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Initialize session state
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "page" not in st.session_state:
        st.session_state["page"] = "dashboard"
    
    # Login gate
    if not st.session_state["logged_in"]:
        login_page()
        return
    
    # Sidebar navigation
    user = st.session_state["user"]
    
    with st.sidebar:
        st.markdown(f"### 🏦 AI Validator")
        st.markdown(f"**{user['name']}**")
        st.markdown(f"*{user['role']}*")
        st.divider()
        
        nav_options = {
            "📊 Dashboard": "dashboard",
            "➕ New Client": "new_client",
            "📁 All Cases": "all_clients",
            "📧 Email Log": "email_log",
        }
        
        if user["role"] == "Admin":
            nav_options["⚙️ Admin Panel"] = "admin"
        
        for label, page_key in nav_options.items():
            if st.button(label, use_container_width=True, key=f"nav_{page_key}"):
                st.session_state["page"] = page_key
                st.rerun()
        
        st.divider()
        if st.button("🚪 Sign Out", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        
        st.divider()
        st.markdown("""
        <div style="font-size:0.75rem; color:#aaa;">
        <strong>MAS AI Thresholds</strong><br>
        Income: SGD 300,000<br>
        Fin. Assets: SGD 1,000,000<br>
        Personal Assets: SGD 2,000,000
        </div>
        """, unsafe_allow_html=True)
    
    # Route pages
    page = st.session_state.get("page", "dashboard")
    
    if page == "dashboard":
        dashboard_page()
    elif page == "new_client":
        new_client_page()
    elif page == "all_clients":
        all_clients_page()
    elif page == "client_detail":
        client_detail_page()
    elif page == "email_log":
        email_log_page()
    elif page == "admin":
        if user["role"] == "Admin":
            admin_page()
        else:
            st.error("Access denied.")

if __name__ == "__main__":
    main()
