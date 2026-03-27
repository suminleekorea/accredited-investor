
# Insurance Review Assistant

Streamlit MVP for internal operations reviewers handling two manual workflows:

- Accredited Investor onboarding review
- USD policy payment verification

The app extracts structured fields from uploaded PDFs, highlights evidence snippets, and flags cases that still need manual review. It is an assistive review tool, not an automated approval engine.

## What the app does

### Accredited Investor Check
- Extracts applicant name plus DBS-style AI evidence when present
- Checks these DBS criteria:
  - annual income >= SGD 300,000 in the last 12 months
  - net personal assets > SGD 2,000,000, with primary residence contribution capped at SGD 1,000,000
  - net financial assets > SGD 1,000,000
  - joint account with an accredited investor
- Shows evidence snippets and manual-review reasons

### USD Payment Check
- Extracts amount, policy/reference, payer, and payee when present
- Requires a policy/reference number for a clean pass
- Compares extracted amount and reference against expected inputs
- Flags incomplete or low-confidence payment proofs for manual review
- Supports the manual TT workflow:
  - customer provides MT103
  - finance sights incoming funds
  - finance notifies cashier
  - cashier posts premium in the policy admin system

## Accredited Investor workflow automation

The Accredited Investor tab now goes beyond a simple document check:

- Creates a case after review for each investor onboarding workflow
- Uses simplified business statuses: `New`, `Pending docs`, `HNW review`, `Approved`, `Rejected`
- Routes the case through the manual process described in the business email:
  - customer provides documentary proof
  - New Business admin forwards documents to HNW team
  - HNW team validates against the accredited investor criteria
  - HNW forwards the case to the team lead for email approval
  - approved case is tagged in the policy admin system
- Stores users, clients, cases, and message threads in the local `data/` folder
- Lets reviewers reassign work, change queue/status, and log email-style follow-ups
- Includes dedicated actions for NB admin, HNW reviewer, team lead, and policy admin
- Includes canned email templates such as `request more documents` and `AI criteria met, pending approval`

Seeded local users are added automatically if `data/users.json` is empty.

## USD payment workflow automation

The USD tab now supports the manual TT payment process for USD policies:

- Creates a case after MT103 review
- Starts the case with `MT103 received`
- Lets Finance confirm `Funds sighted`
- Lets Finance notify Cashier that premium is received
- Lets Cashier mark `Premium posted`
- Stores message threads in the local `data/` folder
- Includes canned templates such as `notify cashier to post premium` and `request payment clarification`

## How to use the platform

### Accredited Investor onboarding
1. Open the `Accredited Investor Check` tab.
2. Select the client from the system list.
3. Upload one or more supporting PDFs.
4. Review the extracted customer, document, and decision summary.
5. Create an investor workflow case.
6. Use the role-based actions to move the case through:
   - `New`
   - `Pending docs`
   - `HNW review`
   - `Approved`
   - `Rejected`
7. Use the email templates or manual notes to record follow-up communication.

### USD TT payment workflow
1. Open the `USD Payment Check` tab.
2. Select the client from the system list.
3. Enter the expected USD amount and policy/reference number.
4. Upload the MT103 or payment proof PDF.
5. Review the extracted amount and reference match.
6. Create a USD workflow case.
7. Use the role-based actions to move the case through:
   - `MT103 received`
   - `Funds sighted`
   - `Cashier notified`
   - `Premium posted`
   - `Rejected`
8. Use the email templates or manual notes to record finance-to-cashier or customer follow-up.

## OCR and extraction behavior

- The app first tries native PDF text extraction
- If the text is weak or empty, it falls back to OCR
- OCR can still miss values on blurry or poorly scanned files, so reviewers should always confirm key numbers

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Community Cloud

1. Push this folder to a GitHub repository.
2. In Streamlit Community Cloud, create a new app from that repository.
3. Set the main file path to `app.py`.
4. Deploy with the default settings.

This version is designed to avoid secrets and external paid APIs so deployment stays simple.

## Current limitations

- PDF-first workflow; image uploads are not included in v1
- OCR quality depends on scan quality
- Field extraction uses document patterns and may miss unusual layouts
- Results should be reviewed by an operations or compliance user before action is taken

## Sample test files

The folder `sample_docs/` contains fake PDFs you can upload for testing:

- `investor_income_pass.pdf`
- `investor_financial_assets_pass.pdf`
- `investor_net_assets_with_residence_cap.pdf`
- `investor_joint_account_pass.pdf`
- `investor_conflict_manual_review.pdf`
- `payment_pass_policy_match.pdf`
- `payment_wrong_reference.pdf`
- `payment_missing_policy_manual_review.pdf`
- `payment_wrong_amount.pdf`

## Included sample platform data

The app also includes sample in-app data under `data/` so users can try the platform immediately:

- `users.json`
  - includes demo roles for NB admin, HNW reviewer, team lead, policy admin, finance, and cashier
- `clients.json`
  - includes demo customers such as John Tan, Sarah Lim, Alice Tan, and Michael Ong
- `workflow_cases.json`
  - includes one demo Accredited Investor case and one demo USD payment case
- `email_logs.json`
  - includes example message threads for both workflows

### Quick demo path

1. Open the app.
2. Go to `Accredited Investor Check` and open the preloaded case `AI-DEMO-001`.
3. Go to `USD Payment Check` and open the preloaded case `USD-DEMO-001`.
4. Upload sample PDFs from `sample_docs/` to create new demo cases of your own.
