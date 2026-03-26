# AI Validator System: IT Integration & Deployment Guide

This document outlines the technical requirements and data layer integrations necessary for the Group IT team to deploy the AI Validator system into the company's production environment.

## 1. System Architecture Overview
The current prototype is built using **Streamlit (Python)**. For production, the architecture should be structured as follows:
- **Frontend:** React.js or Streamlit (if rapid internal deployment is preferred).
- **Backend API:** FastAPI or Django (Python) to handle business logic, OCR processing, and database interactions.
- **Database:** PostgreSQL or MS SQL Server (replacing the prototype's JSON file storage).
- **OCR Engine:** On-premise OCR (e.g., Tesseract + LayoutLM) or a secure enterprise agreement with an LLM provider (e.g., Azure OpenAI) to ensure data privacy.

## 2. Required Data Layer Integrations

To fully automate the workflow, the AI Validator needs to integrate with the following internal systems:

### 2.1. Identity & Access Management (IAM)
- **Requirement:** Single Sign-On (SSO) integration.
- **Protocol:** SAML 2.0 or OAuth 2.0 (e.g., Microsoft Entra ID / Active Directory).
- **Purpose:** Allow RMs and Compliance Officers to log in using their existing corporate credentials. Role-based access control (RBAC) should be mapped from AD groups.

### 2.2. Core CRM System (e.g., Salesforce / MS Dynamics)
- **Requirement:** Two-way API integration.
- **Purpose:** 
  - **Pull:** Fetch client details (Name, NRIC, Contact) directly from the CRM using the Client ID, eliminating manual data entry.
  - **Push:** Once Compliance approves the AI status, the system must push a status update (`AI_Status: Accredited`, `Approval_Date: YYYY-MM-DD`) back to the CRM client profile.

### 2.3. Enterprise Email Server (SMTP / Exchange)
- **Requirement:** SMTP relay or Microsoft Graph API integration.
- **Purpose:** To send automated approval requests and status notifications securely from a recognized corporate email address (e.g., `noreply-aivalidator@company.com`).

### 2.4. Secure Document Storage (DMS)
- **Requirement:** Integration with the company's Document Management System (e.g., SharePoint, AWS S3 with KMS encryption).
- **Purpose:** Uploaded financial documents must be securely stored, encrypted at rest, and linked to the client's CRM record. The temporary `uploads/` folder used in the prototype must be replaced with secure cloud storage.

## 3. Security & Compliance Requirements

1. **Data Privacy (PDPA Compliance):** Financial documents contain highly sensitive PII (Personal Identifiable Information). If using cloud-based OCR (like OpenAI Vision), the IT team must ensure a Zero-Data-Retention agreement is in place with the vendor.
2. **Audit Trail:** Every action (Upload, AI Extraction, Submit, Approve, Reject) must be logged in an immutable audit table containing `Timestamp`, `User_ID`, `Action`, and `IP_Address`.
3. **Data Masking:** The system should automatically mask NRIC numbers (e.g., `S****123A`) on the UI for users who do not have full clearance.

## 4. Infrastructure & Hosting
- **Containerization:** Dockerize the application (Frontend, Backend, OCR worker).
- **Orchestration:** Deploy via Kubernetes (EKS/AKS) for scalability.
- **CI/CD:** Set up GitLab CI or Jenkins pipelines for automated testing and deployment.

---
*Prepared for: Group IT & Infrastructure Team*
