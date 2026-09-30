# 4. System Architecture

> Items marked **[verify]** should be checked against `main.py` before submission. Remove this note and the markers once confirmed.

## 4.1 Business Workflow

The Checking Agent is positioned within the policy issuance process between policy generation and issuance to the insured (Figure 1). Following the insured's submission, the underwriter assesses the risk, issues a quote and a binder, and generates the policy. The underwriter then submits the binder and the generated policy to the Checking Agent, which compares them field by field and returns any discrepancies for correction. After a final comparison, the result is referred to Compliance, which accepts or rejects it. An accepted policy is issued to the insured; a rejected policy returns to the policy generation step. The Auditor, acting as an independent third party, inspects issued documents and stored run records on a read-only basis and does not take part in the approval flow.

*Figure 1. Business workflow and actor responsibilities (`01_business_workflow`).*

## 4.2 Technology Stack

| Layer | Technology |
|---|---|
| Front end | React components (JSX) with `index.html`, served as static files by the backend |
| Backend | Python 3.11, Flask 3.0.3 |
| Application server | Gunicorn 22.0.0 (one worker, 300-second timeout) |
| Document parsing | pdfplumber 0.11.4 |
| Language model | Gemini 3.1 Flash-Lite on Vertex AI via the `google-genai` SDK, set through the `GEMINI_MODEL` environment variable on Cloud Run; temperature 0 |
| Database | Cloud Firestore (run records, review status, usage and cost) |
| Authentication | Google ID token verification (`google-auth`); username and password demo login for evaluation only |
| Hosting | Cloud Run service `checking-agent`, region `us-central1` |
| Build and delivery | Cloud Shell, Cloud Build, Artifact Registry, Docker (`python:3.11-slim`) |
| Observability | Cloud Logging (structured JSON logs written to standard output) |
| Source control | Git, GitHub (`ssreemukhi/CheckingAgent`) |

## 4.3 End-to-End Architecture

All runtime components reside in the Google Cloud project `checking-agent-507207` (Figure 2). Users interact with a React front end, which calls the Flask application over HTTPS. The application authenticates the user, extracts text from the uploaded PDFs, sends the extracted content to Gemini, compares field values and flags discrepancies, presents the results to the reviewer, and saves each run with its token usage and cost to Firestore. **[verify: whether extraction and comparison are performed in a single Gemini call; if so, steps 3 and 4 should be merged.]** Code is deployed from Cloud Shell through Cloud Build and Artifact Registry to Cloud Run. The benchmark and test-case generation scripts are run offline and are not part of the deployed container.

*Figure 2. End-to-end architecture on Google Cloud (`02_end_to_end_architecture`).*

## 4.4 Network Path and Availability

A user request resolves the service's `run.app` hostname through DNS and reaches Google Front End at Google's global edge, where TLS is terminated (Figure 3). The request is then routed over Google's network to the Cloud Run service in `us-central1`. Ingress is set to *all*, and no separate load balancer, web application firewall or custom domain sits in front of the service.

The service is configured with a minimum and maximum of one instance. A single instance therefore remains warm at all times, which avoids cold starts, and runs in a zone selected by Google; Cloud Run relocates it to another zone within the region if that zone fails. Although Cloud Run permits up to 80 concurrent requests per instance, the single synchronous Gunicorn worker processes one request at a time, so a long-running comparison delays other requests on the same instance.

*Figure 3. Network path, regional placement and availability (`03_network_path_and_availability`).*

## 4.5 API Sequence

Figure 4 traces a complete session through the application's endpoints. The browser loads the application from `/`, authenticates through `POST /api/login` and retrieves the user profile and checklist configuration (`/api/me`, `/api/checklists`, `/api/checklist-fields`). A check is submitted through `POST /api/compare`, which extracts the PDF text, calls Gemini, stores the run and returns the discrepancy report. Reviewers retrieve past runs through `/api/history`, add remarks, and approve or reject a run through `/api/history/<run_id>/approve` and `/reject`. Administrators view aggregate usage and cost through `/api/admin/stats`. A `/health` endpoint supports service health checks. **[verify: which roles are permitted to approve or reject runs.]**

*Figure 4. API sequence from login to logout (`04_api_sequence`).*

## 4.6 Code Components

The codebase is organised into three layers (Figure 5). The front end consists of `index.html` and three JSX modules. The backend, contained in `main.py` and `id_validation.py`, handles authentication, PDF extraction, the Gemini client with retry logic, usage and cost tracking, and run history, including review status. Offline tooling, which is not deployed, comprises the test-case generator, the benchmark script, a self-test and a history clean-up utility. **[verify: the purpose of `id_validation.py`, `clear_history.py` and `tests/selftest.py`.]**

*Figure 5. Code components by layer (`05_code_components`).*

## 4.7 Data Location, Security and Scalability

**Data location.** The application is hosted on Cloud Run in `us-central1`, and run records are stored in Cloud Firestore in the `nam5` (United States) multi-region location. Model inference uses the Vertex AI global endpoint, which allows Google to serve requests from any available region; the processing location for individual requests is therefore not fixed. The current deployment does not meet the data residency expectation raised by survey respondents and focus-group participants, namely that customer policy data be processed within India. Pinning inference, hosting and storage to an Indian region is identified as a prerequisite for any pilot with live policy documents.

**Identity and access.** The service runs as the project's default compute service account. A dedicated service account granted only the roles required for Vertex AI and Firestore access is recommended under the principle of least privilege. The demo login lacks multi-factor authentication, password rotation and lockout controls, and is suitable for evaluation only.

**Scalability.** The single-instance, single-worker configuration is adequate for demonstration but serialises requests. Enabling threaded Gunicorn workers or permitting additional instances would be required for concurrent use by a checking team.
