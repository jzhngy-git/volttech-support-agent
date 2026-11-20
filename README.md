# VoltTech Support

A local customer-support demo with a React frontend, FastAPI + Pydantic API, SQLite mock customer/order/ticket store, and policy-grounded retrieval from searchable PDF files. No hosted model or API key is required; the local agent uses deterministic intent and keyword matching so its decisions are repeatable.

## Run locally

In one terminal:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload
```

In a second terminal:

```powershell
npm install
npm run dev
```

Open the Vite URL (usually `http://localhost:5173`). The SQLite database is created and seeded at `data/volttech.sqlite3`.

## Deploy publicly

This app needs both the React interface and the FastAPI backend, so GitHub Pages alone cannot run it. The included `render.yaml` and `Dockerfile` deploy both in one Render web service:

1. In Render, choose **New → Blueprint** and connect this GitHub repository.
2. Select `volttech-support-agent` and deploy the blueprint.
3. Open the public `onrender.com` URL shown for the service.

The free service may sleep when idle. Its filesystem is temporary, so SQLite demo changes can reset after a restart or redeploy. Do not use real customer data.

## Demo records

- `VT-1042`: VoltBook Pro, delivered 20 days ago, $1,299. Eligible for an initial defect/return review, but high-value cases are escalated.
- `VT-1043`: VoltBuds, delivered 8 days ago, $179. Use this for the approval and database-write flow.
- `VT-1044`: VoltCharge, delivered 88 days ago, $49. Outside the return window; ask about a defect to see the warranty path.

Policies and cited sections are in `policies/`; the API indexes the PDF text and returns its real section and page. Coverage includes returns, refunds, warranty claims and exclusions, shipping and missing parcels, payment receipts, order changes/cancellations, and basic device checks. The matching Markdown files are the editable source for those PDFs. Run `python tools/build_policy_pdfs.py` after editing the source policies to regenerate the PDFs.

## Safety and scope

Refunds and replacements are first stored as Pydantic-validated pending actions. The order record changes only after the explicit confirmation step. Out-of-policy, uncertain, high-value, and frustrated cases create structured tickets instead of automated writes. This is a portfolio/demo app, not a production support system: it does not authenticate real customers, connect to payment or shipping providers, or use a hosted LLM.
