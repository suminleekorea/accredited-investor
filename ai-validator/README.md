# Insurance Review Assistant

Streamlit MVP for internal operations reviewers handling two manual workflows:

- Accredited Investor onboarding review
- USD policy payment verification

The app extracts structured fields from uploaded PDFs, highlights evidence snippets, and flags cases that still need manual review. It is an assistive review tool, not an automated approval engine.

## What the app does

### Accredited Investor Check
- Extracts applicant name, annual income, and net worth when present
- Compares extracted values against configured review thresholds
- Shows evidence snippets and manual-review reasons

### USD Payment Check
- Extracts amount, policy/reference, payer, and payee when present
- Compares extracted amount and reference against expected inputs
- Flags incomplete or low-confidence payment proofs for manual review

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
