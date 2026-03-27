# Insurance Review Assistant

Interactive Streamlit demo for two internal insurance operations workflows:

- Accredited Investor review
- USD premium payment review

This solution is designed as a **Copilot-style workflow assistant**.
It helps teams read documents, extract key fields, recommend the next action, draft handoff messages, and keep an audit-style case history.

It is a **demo / prototype**, not a production system yet.

## Project structure

The project is now flattened at the repository root for easier local running and Streamlit deployment.

Key files and folders:

- `app.py`
  - Main Streamlit application
- `requirements.txt`
  - Python dependencies for local run and Streamlit deployment
- `README.md`
  - Demo guide, workflow explanation, deployment notes, and IT discussion guide
- `utils/`
  - OCR, validation, and workflow helper modules
- `data/`
  - Seeded demo users, clients, cases, and message threads
- `sample_docs/`
  - Fake PDF files for the two demo workflows

## 1. What this demo is for

This app demonstrates how AI can support manual insurance operations without removing human control.

The goal is not:

- full automation
- auto-approval without human review
- direct replacement of the New Business Administration, HNW, Finance, or Cashier teams

The goal is:

- reduce manual reading
- reduce copy-paste work
- guide the next action
- make workflow handoff easier
- provide a clearer audit trail

## 2. Who uses it

### Workflow 1: Accredited Investor review

Business users involved:

- Customer uploads supporting documents
- Business Administration team checks intake
- HNW Team reviews evidence
- HNW Team Lead approves
- Policy admin team logs the final result in the policy admin system

### Workflow 2: USD premium payment review

Business users involved:

- Customer submits proof of payment with policy number and amount
- Finance checks whether funds reached the insurer USD account
- Finance confirms premium amount is received
- Finance informs Cashier
- Cashier manually inputs the premium into the policy admin system to force the policy

## 3. What the Copilot does

This demo is built around an interactive Copilot model.

For each case, the UI can show:

- Copilot summary
- Recommended next action
- Why this recommendation
- One-click handoff
- Message draft / follow-up note
- Workflow history

### Copilot support for Accredited Investor review

The app can:

- read uploaded PDFs
- extract applicant name and financial evidence
- check whether documents appear to support accredited investor criteria
- highlight missing evidence or review flags
- recommend the next step
- create a workflow case
- suggest handoff actions for the New Business Administration team, HNW reviewer, HNW lead, and policy admin
- draft email / follow-up messages

Human decisions still required:

- HNW validation
- HNW Team Lead approval
- final policy admin logging

### Copilot support for USD payment review

The app can:

- read MT103 / remittance / payment proof PDFs
- extract amount, policy number, payer, payee, and reference values when present
- compare extracted values against expected amount and policy number
- flag mismatches or low-confidence results
- guide Finance on the next action
- create a payment workflow case
- draft the handoff message to Cashier
- log follow-up history

Human decisions still required:

- checking the actual insurer bank / USD account
- confirming the funds are truly received
- cashier posting the premium into the policy admin system

## 4. Workflow overview

### Accredited Investor review flow

1. Customer uploads supporting documents
2. Business Administration team checks completeness
3. HNW Team reviews evidence
4. HNW Team Lead approves or rejects
5. Policy admin team completes final system update

### USD payment review flow

1. Customer submits proof of payment
2. Finance checks policy number and amount against the payment proof
3. Finance checks the insurer USD account
4. Finance confirms payment is received and informs Cashier
5. Cashier manually posts the premium in the policy admin system

## 5. What this demo currently does

### Investor Review

- Upload one or more investor documents in PDF format
- Extract key financial fields
- Highlight supporting evidence and review flags
- Create a workflow case
- Route the case through New Business Administration, HNW reviewer, HNW lead, and policy admin roles
- Add messages and follow-up notes

### USD Payment Review

- Upload MT103 / payment proof in PDF format
- Enter expected amount and policy number
- Compare document evidence against expected values
- Create a workflow case
- Route the case through Finance and Cashier roles
- Add messages and follow-up notes

### Current case UI

For each case, the app now shows:

- current owner
- current step
- priority
- workflow stepper
- Copilot recommendation
- next actions
- advanced case settings
- messages and follow-up

## 6. What this demo does not do yet

This is still a demo. It does not yet provide:

- enterprise authentication
- role-based access control tied to real user identity
- production database
- secure production document storage
- integration with bank systems
- integration with policy admin system
- real approval governance
- production monitoring and audit controls

## 7. Local data model

The demo stores data locally in the `data/` folder:

- `users.json`
- `clients.json`
- `workflow_cases.json`
- `email_logs.json`

This is useful for demos only.

For production, these should move to enterprise-grade services.

## 8. OCR and extraction behavior

- The app first tries native PDF text extraction
- If the text is weak or empty, it falls back to OCR
- OCR can miss values on poor scans
- Human review is still required for important names, amounts, and approval decisions

## 9. Run locally

From the project folder:

```bash
pip install -r requirements.txt
python -m streamlit run app.py
```

The app will usually open on:

- `http://localhost:8501`
- or another local port such as `8502` if `8501` is already in use

## 10. Sample files for demo

The folder `sample_docs/` contains fake PDFs for testing:

- `investor_income_pass.pdf`
- `investor_financial_assets_pass.pdf`
- `investor_net_assets_with_residence_cap.pdf`
- `investor_joint_account_pass.pdf`
- `investor_conflict_manual_review.pdf`
- `payment_pass_policy_match.pdf`
- `payment_wrong_reference.pdf`
- `payment_missing_policy_manual_review.pdf`
- `payment_wrong_amount.pdf`

### Which sample file is used for which demo

#### Investor Review demo

Use these files in the `Investor Review` tab:

- `sample_docs/investor_income_pass.pdf`
  - Use this to show a clean income-based pass scenario
- `sample_docs/investor_financial_assets_pass.pdf`
  - Use this to show a financial-assets-based pass scenario
- `sample_docs/investor_net_assets_with_residence_cap.pdf`
  - Use this to show net personal assets with residence cap logic
- `sample_docs/investor_joint_account_pass.pdf`
  - Use this to show a joint-account accredited investor scenario
- `sample_docs/investor_conflict_manual_review.pdf`
  - Use this to show a manual-review / conflicting-evidence scenario

#### USD Payment Review demo

Use these files in the `USD Payment Review` tab:

- `sample_docs/payment_pass_policy_match.pdf`
  - Good case: clean bank-originated payment proof with a printed policy number and amount that matches
- `sample_docs/payment_wrong_reference.pdf`
  - Bad case: payment amount is visible but the policy/reference does not match
- `sample_docs/payment_missing_policy_manual_review.pdf`
  - Bad case: payment amount is visible but the policy/reference is missing, so manual review is needed
- `sample_docs/payment_wrong_amount.pdf`
  - Bad case: policy/reference is present but the amount does not match

## 11. Quick demo script

If you want to show this in a meeting:

1. Open the app
2. Show the two tabs:
   - `Investor Review`
   - `USD Payment Review`
3. Open the seeded demo investor case
4. Show the workflow stepper and Copilot recommendation
5. Open the seeded USD payment case
6. Show the Finance-to-Cashier handoff model

### Good case vs bad case message for payment OCR

- Good case:
  - bank-originated proof with a clear printed policy number
  - amount and reference also available from bank data or Excel
  - expected result: `Review passed`
- Bad case:
  - handwritten, blurry, tilted, or incomplete receipt
  - OCR may find some text but the policy number is weak or missing
  - expected result: `Needs manual review`

### Quick local check for payment cases

Run this from the project root:

```bash
python scripts/payment_demo_check.py
```

This prints the current extraction result for the good case and the bad-case sample PDFs.
7. Upload one sample PDF and create a new case
8. Explain that human approval still stays in place

## 11A. Which files are needed to run or share the demo

If you want to hand this project to another person or deploy it, the important files are:

- `app.py`
- `requirements.txt`
- `utils/`
- `data/`
- `sample_docs/`
- `README.md`

If someone only wants to run the Streamlit demo, these are the minimum files they need.

## 12. How Copilot can automate the business process

This app is best positioned as an **interactive operations Copilot**.

### For Business Administration / HNW workflow

Copilot can automate:

- document reading
- field extraction
- evidence summarization
- missing document detection
- recommendation of the next workflow step
- message drafting
- workflow logging

Copilot should not fully automate:

- final accredited investor approval
- final lead approval
- final policy admin completion without human confirmation

### For Finance / Cashier workflow

Copilot can automate:

- payment proof reading
- amount and policy number matching
- mismatch flagging
- summary generation
- cashier notification draft
- audit-style workflow logging

Copilot should not fully automate:

- actual bank receipt confirmation unless integrated with trusted bank data
- premium posting unless explicitly integrated and approved

## 13. What to discuss with IT before going live

Before production deployment, IT and business teams should align on the following:

### Users and authentication

- Is this internal-only or customer-facing?
- Will users sign in through SSO, Azure AD, Okta, or another internal identity provider?
- How will roles be enforced for New Business Administration, HNW reviewer, HNW lead, Finance, Cashier, and Policy Admin?

### Data and storage

- Where should uploaded documents be stored securely?
- What production database should store cases, messages, and audit logs?
- What data retention rules apply to customer and financial documents?

### Security and compliance

- Are AI / OCR services allowed to process PII and financial documents?
- What encryption requirements apply?
- What audit trail must be kept?
- What are the rules for deletion, retention, and access review?

### System integration

- Can this integrate with the policy admin system?
- Should policy posting remain manual?
- Can Finance confirm bank receipt inside the tool, or should that remain outside the tool?
- Is there any approved interface for bank / payment confirmation?

### Operations and support

- Who owns production support?
- Who handles incidents and access requests?
- What monitoring and alerting are required?
- What are the backup and disaster recovery expectations?

## 14. Demo vs production

### This Streamlit app is good for

- business demos
- design validation
- workflow walkthroughs
- pilot conversations with business and IT
- proof of concept for AI-assisted operations

### This Streamlit app is not yet enough for full production by itself

Because production will usually need:

- enterprise authentication
- stronger role-based security
- production database
- secure file storage
- audit logging
- integration with internal systems
- deployment and monitoring standards

## 15. Production deployment options

There are two realistic paths.

### Option A: Keep Streamlit as an internal tool

Good for:

- internal users only
- fast rollout
- smaller user base
- pilot or controlled production

Typical architecture:

- Streamlit app
- PostgreSQL or SQL Server
- secure document storage
- SSO / internal authentication
- reverse proxy / internal hosting
- central logging and monitoring

### Option B: Keep the workflow logic but rebuild the UI as an enterprise web app

Good for:

- larger user base
- long-term production ownership
- stronger UI / UX requirements
- deeper enterprise integration

Typical architecture:

- frontend web app
- backend API service
- workflow / queue service
- production database
- secure object storage
- SSO
- audit logging
- integration with internal policy admin systems

## 16. Suggested production path

Recommended sequence:

1. Use this Streamlit app as the business demo
2. Confirm workflow requirements with New Business Administration, HNW, Finance, Cashier, and Policy Admin
3. Review security, storage, identity, and integration requirements with IT
4. Decide whether production should stay on Streamlit or move to a full enterprise app stack
5. Replace local JSON storage with a production database
6. Replace local file handling with secure storage
7. Add authentication and role-based access control
8. Add audit logging and monitoring
9. Run user acceptance testing with real business scenarios
10. Move to pilot deployment before full rollout

## 17. Suggested questions for IT

These are direct questions you can use in a meeting:

- Can this tool be hosted internally behind SSO?
- Which production database should store workflow cases and audit logs?
- Where should customer financial documents be stored securely?
- Do we have an approved OCR / AI platform for PII documents?
- Can the tool integrate with the policy admin system?
- Should payment receipt confirmation remain manual?
- What monitoring and logging are required?
- Who will own application support after go-live?

## 17A. Streamlit Cloud deployment settings

If you deploy this repo to Streamlit Community Cloud, use:

- Repository: your GitHub repository
- Branch: `main`
- Main file path: `app.py`

Because the project is now flattened at the repo root, you do not need to point Streamlit to `ai-validator/app.py` anymore.

## 18. Current limitations

- PDF-first workflow only
- OCR quality depends on scan quality
- field extraction may miss unusual layouts
- no real system integration yet
- no production auth yet
- no production audit controls yet

## 18A. Dependency versions

The dependency ranges in `requirements.txt` were updated to current package releases as of March 27, 2026.

Current target ranges:

- `streamlit>=1.55,<1.56`
- `pdfplumber>=0.11.9,<0.12`
- `PyMuPDF>=1.27.2,<1.28`
- `rapidocr-onnxruntime>=1.4.4,<1.5`

## 19. Included sample data

The app includes sample in-app data under `data/`:

- `users.json`
- `clients.json`
- `workflow_cases.json`
- `email_logs.json`

This makes the demo usable immediately without external dependencies.

### Which data file supports which part of the demo

- `data/users.json`
  - Demo users for:
    - New Business Administration
    - HNW reviewer
    - HNW Team Lead
    - Policy Admin
    - Finance
    - Cashier

- `data/clients.json`
  - Demo customers used in the client selector

- `data/workflow_cases.json`
  - Contains seeded workflow cases such as:
    - `AI-DEMO-001` for the Investor Review demo
    - `USD-DEMO-001` for the USD Payment Review demo

- `data/email_logs.json`
  - Contains sample handoff messages and follow-up history for the demo cases

### Quick file-to-demo mapping

- `sample_docs/investor_*`
  - Upload into `Investor Review`

- `sample_docs/payment_*`
  - Upload into `USD Payment Review`

- `data/workflow_cases.json`
  - Open existing demo cases without uploading files

- `data/email_logs.json`
  - Shows example message threads inside the case view
