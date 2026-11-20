from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pypdf import PdfReader

from policy_search import PolicyRetriever


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "volttech.sqlite3"
DATA_DIR.mkdir(exist_ok=True)

POLICY_TERMS = {
    "30-Day Returns": {"return", "refund", "open", "day", "defect", "flicker", "screen", "display", "exchange", "laptop", "send", "back", "accessory", "proof", "delivery", "window"},
    "Return Shipping & Refunds": {"return", "shipping", "refund", "label", "postage", "mail", "cost", "inspection", "days"},
    "Limited Warranty Coverage": {"warranty", "laptop", "computer", "screen", "flicker", "display", "defect", "repair", "replacement", "coverage", "year", "protection", "period"},
    "Warranty Exclusions": {"warranty", "damage", "liquid", "water", "repair", "exclusion", "inspection", "accidental", "dropped", "modified", "scratch"},
    "Warranty Claim Process": {"warranty", "claim", "serial", "inspection", "repair", "replacement", "photos", "service", "apart", "open", "modify", "review"},
    "Shipping & Delivery": {"shipping", "delivery", "tracking", "delivered", "parcel", "carrier", "package", "arrival", "arrive", "late", "missing", "lost", "movement", "scan"},
    "Delivery Delays & Missing Parcels": {"shipping", "delivery", "tracking", "delivered", "parcel", "carrier", "package", "late", "missing", "lost", "update", "business", "dispatch", "delay", "additional", "report"},
    "Payment & Receipts": {"payment", "pay", "charge", "receipt", "invoice", "card", "paypal", "charged", "billing", "email", "confirmation", "inbox"},
    "Order Changes & Cancellations": {"order", "cancel", "change", "address", "dispatch", "fulfillment", "packed", "ship", "parcel", "delivery", "sent", "update", "where"},
    "Safe Device Checks": {"device", "power", "charge", "cable", "restart", "screen", "flicker", "troubleshoot", "outlet", "battery", "charger"},
}
def load_policy_corpus() -> list[dict]:
    policies = []
    title_pattern = "|".join(re.escape(title) for title in sorted(POLICY_TERMS, key=len, reverse=True))
    heading_pattern = re.compile(
        rf"^(?P<section>.+?)\s+Section\s+(?P<number>[\d.]+)\s*-\s*(?P<title>{title_pattern})$"
    )
    for pdf_path in sorted((ROOT / "policies").glob("*.pdf")):
        reader = PdfReader(str(pdf_path))
        for page_number, page in enumerate(reader.pages, start=1):
            page_lines = (page.extract_text() or "").splitlines()
            heading_line = None
            for start in range(len(page_lines)):
                if " Section " not in f" {page_lines[start]} ":
                    continue
                for end in range(start + 1, min(start + 3, len(page_lines)) + 1):
                    combined = " ".join(line.strip() for line in page_lines[start:end]).strip()
                    heading = heading_pattern.fullmatch(combined)
                    if heading:
                        heading_line = (end - 1, heading)
                        break
                if heading_line is not None:
                    break
            if heading_line is None:
                continue
            heading_index, heading = heading_line
            title = heading.group("title").strip()
            terms = POLICY_TERMS.get(title)
            if terms is None:
                raise RuntimeError(f"Unknown policy section '{title}' in {pdf_path.name}, page {page_number}.")
            page_text = re.sub(r"\s+", " ", " ".join(page_lines[heading_index + 1:])).strip()
            policies.append(
                {
                    "id": f"{pdf_path.stem}-{page_number}",
                    "title": title,
                    "section": f"{heading.group('section')} Section {heading.group('number')}",
                    "page": page_number,
                    "text": page_text,
                    "terms": terms,
                }
            )
    indexed_titles = {policy["title"] for policy in policies}
    missing_titles = set(POLICY_TERMS) - indexed_titles
    if missing_titles:
        raise RuntimeError(f"Policy PDFs are missing indexed sections: {', '.join(sorted(missing_titles))}.")
    return policies


POLICIES = load_policy_corpus()
POLICY_RETRIEVER = PolicyRetriever(POLICIES)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    order_id: str | None = None


class ResolutionRequest(BaseModel):
    order_id: str
    action_type: Literal["refund", "replacement"]
    reason: str = Field(min_length=3, max_length=500)


class ResolutionPayload(BaseModel):
    action_id: str
    order_id: str
    action_type: Literal["refund", "replacement"]
    reason: str
    amount: float = Field(gt=0)
    policy_references: list[str]
    status: Literal["awaiting_approval", "approved", "rejected"]


class ApprovalRequest(BaseModel):
    approved: bool
    approved_by: Literal["customer", "admin"]


class EscalationPayload(BaseModel):
    order_id: str | None
    summary: str
    reason: Literal["out_of_policy", "high_value", "customer_frustration", "uncertain"]
    priority: Literal["normal", "high"]


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize_database() -> None:
    with closing(connect()) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
                item TEXT NOT NULL, order_date TEXT NOT NULL, delivered_at TEXT NOT NULL,
                price REAL NOT NULL, serial TEXT NOT NULL, warranty_months INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'delivered', resolution TEXT
            );
            CREATE TABLE IF NOT EXISTS actions (
                id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id),
                action_type TEXT NOT NULL, reason TEXT NOT NULL, amount REAL NOT NULL,
                policy_references TEXT NOT NULL, status TEXT NOT NULL,
                approved_by TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tickets (
                id TEXT PRIMARY KEY, order_id TEXT, summary TEXT NOT NULL,
                reason TEXT NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        if db.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0:
            today = date.today()
            db.executemany(
                "INSERT INTO customers (id, name, email) VALUES (?, ?, ?)",
                [
                    ("CUS-001", "Alex Morgan", "alex.morgan@example.test"),
                    ("CUS-002", "Jamie Chen", "jamie.chen@example.test"),
                ],
            )
            db.executemany(
                """INSERT INTO orders
                   (id, customer_id, item, order_date, delivered_at, price, serial, warranty_months)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        "VT-1042", "CUS-001", "VoltBook Pro 14-inch", (today - timedelta(days=22)).isoformat(),
                        (today - timedelta(days=20)).isoformat(), 1299.00, "VB14-88A21", 12,
                    ),
                    (
                        "VT-1043", "CUS-001", "VoltBuds Wireless", (today - timedelta(days=10)).isoformat(),
                        (today - timedelta(days=8)).isoformat(), 179.00, "VBW-31C09", 12,
                    ),
                    (
                        "VT-1044", "CUS-002", "VoltCharge 65W", (today - timedelta(days=90)).isoformat(),
                        (today - timedelta(days=88)).isoformat(), 49.00, "VC65-71D04", 12,
                    ),
                ],
            )
        db.commit()


def order_record(order_id: str) -> dict | None:
    with closing(connect()) as db:
        row = db.execute(
            """SELECT o.*, c.name AS customer_name
               FROM orders o JOIN customers c ON c.id = o.customer_id WHERE o.id = ?""",
            (order_id.upper().lstrip("#"),),
        ).fetchone()
    if row is None:
        return None
    order = dict(row)
    delivered = date.fromisoformat(order["delivered_at"])
    days_since_delivery = (date.today() - delivered).days
    order["days_since_delivery"] = days_since_delivery
    order["return_eligible"] = 0 <= days_since_delivery <= 30
    order["warranty_active"] = delivered + timedelta(days=365) >= date.today()
    return order


def extract_order_id(message: str, supplied_id: str | None) -> str | None:
    match = re.search(r"#?(VT-\d{4})", message, re.IGNORECASE)
    candidate = match.group(1) if match else supplied_id
    return candidate.upper().lstrip("#") if candidate else None


def retrieve_policies(message: str) -> list[dict]:
    return POLICY_RETRIEVER.search(message, limit=3)


def create_escalation(
    order_id: str | None,
    summary: str,
    reason: Literal["out_of_policy", "high_value", "customer_frustration", "uncertain"],
) -> dict:
    ticket_id = f"TK-{uuid.uuid4().hex[:6].upper()}"
    priority = "high" if reason in {"high_value", "customer_frustration"} else "normal"
    payload = EscalationPayload(
        order_id=order_id,
        summary=summary[:500],
        reason=reason,
        priority=priority,
    )
    with closing(connect()) as db:
        db.execute(
            """INSERT INTO tickets (id, order_id, summary, reason, priority, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'open', ?)""",
            (ticket_id, payload.order_id, payload.summary, payload.reason, payload.priority, datetime.now(timezone.utc).isoformat()),
        )
        db.commit()
    return {"ticket_id": ticket_id, **payload.model_dump(), "status": "open"}


initialize_database()
app = FastAPI(title="VoltTech Support API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/orders/{order_id}")
def get_order(order_id: str) -> dict:
    order = order_record(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found. Check the ID and try again.")
    return order


@app.get("/api/policies")
def get_policies() -> list[dict]:
    return [
        {"title": p["title"], "citation": f'{p["section"]}, p. {p["page"]}', "excerpt": p["text"]}
        for p in POLICIES
    ]


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict:
    message = request.message.strip()
    order_id = extract_order_id(message, request.order_id)
    sources = retrieve_policies(message)
    order = order_record(order_id) if order_id else None
    frustrated = any(
        phrase in message.lower()
        for phrase in ("furious", "angry", "unacceptable", "awful", "lawyer", "complaint", "fed up", "ridiculous")
    )
    defect_signal = any(
        phrase in message.lower()
        for phrase in ("defect", "flicker", "broken", "fault", "not working", "damaged", "won't turn on", "wont turn on")
    )
    resolution_intent = defect_signal or any(
        phrase in message.lower()
        for phrase in ("return", "refund", "replacement", "replace", "exchange", "warranty", "cancel")
    )
    exclusion_signal = any(
        phrase in message.lower()
        for phrase in ("accidental", "dropped", "liquid", "water", "unauthorized repair", "modified", "improper installation")
    )

    answer_parts = []
    if sources:
        answer_parts.append(f'According to **{sources[0]["citation"]}**, {sources[0]["excerpt"]}')
    else:
        answer_parts.append(
            "I couldn't find a policy clause that answers that confidently, so I won't guess. "
            "I can route this to a support specialist."
        )

    if order_id and order is None:
        answer_parts.append(f"I couldn't find order **#{order_id}**. Please check the order ID.")
    elif order:
        answer_parts.append(
            f'Order **#{order["id"]}** is {order["item"]}, delivered {order["days_since_delivery"]} days ago. '
            f'{"It is within" if order["return_eligible"] else "It is outside"} the 30-day return window; '
            f'{"its" if order["warranty_active"] else "its"} warranty is '
            f'{"active" if order["warranty_active"] else "expired"}.'
        )

    escalation = None
    if frustrated:
        escalation = create_escalation(order_id, f"Customer expressed frustration: {message}", "customer_frustration")
    elif order and order["price"] > 200 and resolution_intent:
        escalation = create_escalation(
            order_id,
            f"High-value {order['item']} ({order['price']:.2f}) requires human review. Customer request: {message}",
            "high_value",
        )
    elif order and exclusion_signal:
        escalation = create_escalation(
            order_id,
            f"Possible warranty exclusion requires inspection. Customer request: {message}",
            "uncertain",
        )
    elif order and not order["return_eligible"] and not order["warranty_active"]:
        escalation = create_escalation(
            order_id,
            f"Order is outside the return window and warranty period. Customer request: {message}",
            "out_of_policy",
        )
    elif not sources:
        escalation = create_escalation(order_id, f"Policy answer not found: {message}", "uncertain")
    elif order and not order["return_eligible"] and resolution_intent:
        escalation_reason = "uncertain" if order["warranty_active"] else "out_of_policy"
        escalation = create_escalation(
            order_id,
            f"Requested resolution is outside the 30-day return window. Human review required: {message}",
            escalation_reason,
        )

    return_policy_retrieved = any(source["title"] == "30-Day Returns" for source in sources)
    eligible = bool(
        order
        and return_policy_retrieved
        and order["return_eligible"]
        and defect_signal
        and not exclusion_signal
        and not frustrated
        and order["price"] <= 200
    )
    if order and return_policy_retrieved and order["return_eligible"] and defect_signal and order["price"] > 200:
        answer_parts.append("This item meets the initial return-window and defect criteria, but its value requires human review before any refund or replacement.")
    elif eligible:
        answer_parts.append("This order appears eligible for a return resolution. Choose a refund or replacement below; nothing is changed until you approve it.")

    return {
        "answer": "\n\n".join(answer_parts),
        "sources": sources,
        "order": order,
        "eligible": eligible,
        "escalation": escalation,
        "agent_steps": [
            "Classified request",
            "Retrieved policy passages" if sources else "No matching policy passage",
            f"Read order {order_id}" if order else "No order lookup",
            "Escalated to human queue" if escalation else ("Prepared for approval" if eligible else "No write performed"),
        ],
    }


@app.post("/api/actions/prepare", response_model=ResolutionPayload)
def prepare_action(request: ResolutionRequest) -> ResolutionPayload:
    order = order_record(request.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found.")
    if order["status"] != "delivered":
        raise HTTPException(status_code=409, detail="This order already has a resolution in progress.")
    if order["price"] > 200:
        raise HTTPException(status_code=409, detail="Orders over $200 require human review instead of automated processing.")
    reason_lower = request.reason.lower()
    defect_signal = any(
        phrase in reason_lower
        for phrase in ("defect", "flicker", "broken", "fault", "not working", "damaged", "won't turn on", "wont turn on")
    )
    if not defect_signal:
        raise HTTPException(status_code=409, detail="A documented defect is required for an automated return resolution.")
    if not order["return_eligible"]:
        raise HTTPException(status_code=409, detail="This order is outside the 30-day automated return window and needs human review.")
    if not order["warranty_active"]:
        raise HTTPException(status_code=409, detail="This order's warranty has expired.")

    action_id = f"AC-{uuid.uuid4().hex[:8].upper()}"
    references = ["Returns & Exchanges §2.1, p. 2", "Limited Warranty §1.2, p. 4"]
    payload = ResolutionPayload(
        action_id=action_id,
        order_id=order["id"],
        action_type=request.action_type,
        reason=request.reason,
        amount=order["price"],
        policy_references=references,
        status="awaiting_approval",
    )
    with closing(connect()) as db:
        db.execute(
            """INSERT INTO actions
               (id, order_id, action_type, reason, amount, policy_references, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'awaiting_approval', ?)""",
            (
                payload.action_id, payload.order_id, payload.action_type, payload.reason,
                payload.amount, json.dumps(payload.policy_references), datetime.now(timezone.utc).isoformat(),
            ),
        )
        db.commit()
    return payload


@app.post("/api/actions/{action_id}/approval", response_model=ResolutionPayload)
def decide_action(action_id: str, request: ApprovalRequest) -> ResolutionPayload:
    with closing(connect()) as db:
        row = db.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Pending action not found.")
        if row["status"] != "awaiting_approval":
            raise HTTPException(status_code=409, detail=f"This action is already {row['status']}.")
        status = "approved" if request.approved else "rejected"
        db.execute(
            "UPDATE actions SET status = ?, approved_by = ? WHERE id = ?",
            (status, request.approved_by, action_id),
        )
        if request.approved:
            order_status = "refund_issued" if row["action_type"] == "refund" else "replacement_requested"
            db.execute("UPDATE orders SET status = ?, resolution = ? WHERE id = ?", (order_status, row["action_type"], row["order_id"]))
        db.commit()
    return ResolutionPayload(
        action_id=row["id"],
        order_id=row["order_id"],
        action_type=row["action_type"],
        reason=row["reason"],
        amount=row["amount"],
        policy_references=json.loads(row["policy_references"]),
        status=status,
    )


@app.get("/api/tickets")
def list_tickets() -> list[dict]:
    with closing(connect()) as db:
        rows = db.execute(
            "SELECT id, order_id, summary, reason, priority, status, created_at FROM tickets ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/stats")
def get_stats() -> dict:
    with closing(connect()) as db:
        counts = {
            "orders": db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "pending_approvals": db.execute("SELECT COUNT(*) FROM actions WHERE status = 'awaiting_approval'").fetchone()[0],
            "open_tickets": db.execute("SELECT COUNT(*) FROM tickets WHERE status = 'open'").fetchone()[0],
        }
    return counts


DIST_DIR = ROOT / "dist"
if DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")
