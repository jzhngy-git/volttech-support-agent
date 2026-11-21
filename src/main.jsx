import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowDown, ArrowUpRight, BadgeCheck, BookOpen, Check, ChevronDown, ChevronRight,
  CircleHelp, Clock3, Cpu, Database, FileText, Headphones, LifeBuoy, LoaderCircle,
  MessageCircle, PackageCheck, Plus, RotateCcw, Send, Shield, ShieldAlert,
  ShoppingBag, Terminal, X,
} from "lucide-react";
import "./styles.css";

const API = "/api";
const orderSuggestions = [
  { id: "VT-1042", title: "VoltBook Pro 14-inch", note: "Delivered 20 days ago · $1,299" },
  { id: "VT-1043", title: "VoltBuds Wireless", note: "Delivered 8 days ago · $179" },
  { id: "VT-1044", title: "VoltCharge 65W", note: "Delivered 88 days ago · $49" },
];

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || "Something went wrong.");
  return body;
}

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [orderId, setOrderId] = useState("VT-1042");
  const [order, setOrder] = useState(null);
  const [stats, setStats] = useState({ pending_approvals: 0, open_tickets: 0 });
  const [tickets, setTickets] = useState([]);
  const [pendingAction, setPendingAction] = useState(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("order");
  const [showQueue, setShowQueue] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    refresh();
    lookupOrder("VT-1042");
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pendingAction]);

  async function refresh() {
    try {
      const [nextStats, nextTickets] = await Promise.all([
        request("/stats"), request("/tickets"),
      ]);
      setStats(nextStats);
      setTickets(nextTickets);
    } catch (reason) {
      setError(reason.message);
    }
  }

  async function lookupOrder(id) {
    const normalized = id.trim().replace(/^#/, "").toUpperCase();
    setOrderId(normalized);
    if (!normalized) return;
    try {
      setOrder(await request(`/orders/${encodeURIComponent(normalized)}`));
      setError("");
    } catch (reason) {
      setOrder(null);
      setError(reason.message);
    }
  }

  function addUserMessage(text) {
    setMessages((current) => [...current, {
      id: crypto.randomUUID(), role: "user", text, time: new Date(),
    }]);
  }

  async function sendMessage(text = input) {
    const clean = text.trim();
    if (!clean || loading) return;
    setInput("");
    setError("");
    addUserMessage(clean);
    setLoading(true);
    try {
      const result = await request("/chat", {
        method: "POST",
        body: JSON.stringify({ message: clean, order_id: orderId || null }),
      });
      setMessages((current) => [...current, {
        id: crypto.randomUUID(), role: "assistant", ...result, time: new Date(),
      }]);
      if (result.order) {
        setOrder(result.order);
        setOrderId(result.order.id);
      }
      if (result.escalation) setShowQueue(true);
      await refresh();
    } catch (reason) {
      setError(reason.message);
    } finally {
      setLoading(false);
    }
  }

  async function prepareAction(actionType) {
    if (!order) return;
    setActionLoading(true);
    setError("");
    try {
      const payload = await request("/actions/prepare", {
        method: "POST",
        body: JSON.stringify({
          order_id: order.id,
          action_type: actionType,
          reason: messages.filter((message) => message.role === "user").at(-1)?.text || "Defective product",
        }),
      });
      setPendingAction(payload);
      await refresh();
    } catch (reason) {
      setError(reason.message);
    } finally {
      setActionLoading(false);
    }
  }

  async function decideAction(approved) {
    if (!pendingAction) return;
    setActionLoading(true);
    setError("");
    try {
      const result = await request(`/actions/${pendingAction.action_id}/approval`, {
        method: "POST",
        body: JSON.stringify({ approved, approved_by: "customer" }),
      });
      setPendingAction(null);
      setMessages((current) => [...current, {
        id: crypto.randomUUID(),
        role: "system",
        text: result.status === "approved"
          ? `${result.action_type === "refund" ? "Refund" : "Replacement"} approved for #${result.order_id}. The demo order record has been updated.`
          : `The request for #${result.order_id} was declined. No order changes were made.`,
        time: new Date(),
      }]);
      await lookupOrder(result.order_id);
      await refresh();
    } catch (reason) {
      setError(reason.message);
    } finally {
      setActionLoading(false);
    }
  }

  function startFlow(prompt) {
    setMessages([]);
    setPendingAction(null);
    setShowQueue(false);
    sendMessage(prompt);
  }

  const latestAssistant = [...messages].reverse().find((message) => message.role === "assistant");
  const eligible = Boolean(latestAssistant?.eligible && latestAssistant.order?.id === order?.id && order?.status === "delivered");

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="VoltTech Support home">
          <span className="brand-mark"><Cpu size={18} strokeWidth={2.6} /></span>
          <span>volt<span className="brand-light">tech</span><small>SUPPORT</small></span>
        </a>
        <div className="topbar-center"><span className="online-dot" /> VoltTech Support</div>
        <div className="topbar-right">
          <button className="icon-button" title="Help"><CircleHelp size={18} /></button>
          <button className="queue-button" onClick={() => setShowQueue(true)}>
            <LifeBuoy size={16} /> Human queue <span className="queue-count">{stats.open_tickets}</span>
          </button>
          <div className="avatar">AM</div>
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <div className="sidebar-label">WORKSPACE</div>
          <button className="nav-item active"><MessageCircle size={17} /> Support desk <span className="nav-dot" /></button>
          <button className="nav-item" onClick={() => setShowQueue(true)}><Headphones size={17} /> Human handoffs <span className="nav-counter">{stats.open_tickets}</span></button>
          <div className="sidebar-label section-gap">QUICK CASES</div>
          <button className="flow-item" onClick={() => startFlow("Can I return my laptop? The screen flickers after 20 days. #VT-1042")}>
            <span className="flow-icon lilac"><BookOpen size={15} /></span>
            <span><b>Laptop return</b><small>Check policy and order details</small></span>
          </button>
          <button className="flow-item" onClick={() => {
            lookupOrder("VT-1043");
            startFlow("My VoltBuds are defective and won't turn on. #VT-1043");
          }}>
            <span className="flow-icon mint"><Shield size={15} /></span>
            <span><b>Defective earbuds</b><small>Try the approval process</small></span>
          </button>
          <button className="flow-item" onClick={() => {
            lookupOrder("VT-1044");
            startFlow("My charger stopped working. Can you replace it? #VT-1044");
          }}>
            <span className="flow-icon amber"><ArrowUpRight size={15} /></span>
            <span><b>Older order</b><small>Check warranty and handoff</small></span>
          </button>
          <div className="sidebar-bottom">
            <div className="profile"><div className="avatar profile-avatar">AM</div><span><b>Alex Morgan</b><small>Support admin</small></span><ChevronDown size={14} /></div>
          </div>
        </aside>

        <main className="main-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow"><span className="live-dot" /> CUSTOMER SUPPORT</div>
              <h1>Support desk</h1>
              <p>Look up orders, check store policies, and send tricky cases to a person.</p>
            </div>
            <div className="heading-actions"><button className="new-chat" onClick={() => { setMessages([]); setPendingAction(null); setError(""); }}><Plus size={16} /> New conversation</button></div>
          </div>

          <div className="workspace-grid">
            <section className="chat-card">
              <div className="chat-header">
                <div className="bot-avatar"><Headphones size={18} /></div>
                <div className="chat-heading"><b>VoltTech Support</b><span><span className="online-dot" /> Available</span></div>
                <button className="more-button" title="Reset conversation" onClick={() => setMessages([])}><RotateCcw size={16} /></button>
              </div>

              <div className="conversation">
                {messages.length === 0 && (
                  <div className="welcome">
                    <div className="welcome-icon"><MessageCircle size={21} /></div>
                    <div className="welcome-kicker">VOLTTECH CUSTOMER SUPPORT</div>
                    <h2>How can we help?</h2>
                    <p>Ask about an order, return, or warranty. You can also ask for a specialist anytime; requests are added to the handoff queue.</p>
                    <div className="suggestion-grid">
                      <button onClick={() => sendMessage("Can I return my laptop? The screen flickers after 20 days. #VT-1042")}><span className="suggestion-symbol lavender"><BookOpen size={16} /></span><span><b>Return a defective laptop</b><small>Check the policy and order</small></span><ChevronRight size={15} /></button>
                      <button onClick={() => { lookupOrder("VT-1043"); sendMessage("My VoltBuds are defective and won't turn on. #VT-1043"); }}><span className="suggestion-symbol green"><PackageCheck size={16} /></span><span><b>Replace defective earbuds</b><small>Try the approval process · VT-1043</small></span><ChevronRight size={15} /></button>
                      <button onClick={() => sendMessage("Can I cancel my order before it ships?")}><span className="suggestion-symbol lavender"><RotateCcw size={16} /></span><span><b>Change or cancel an order</b><small>Check before-dispatch rules</small></span><ChevronRight size={15} /></button>
                      <button onClick={() => sendMessage("How do I get another copy of my payment receipt?")}><span className="suggestion-symbol green"><FileText size={16} /></span><span><b>Find a receipt</b><small>Ask about payment and billing</small></span><ChevronRight size={15} /></button>
                      <button onClick={() => sendMessage("I'd like to speak to a support specialist.")}><span className="suggestion-symbol lavender"><Headphones size={16} /></span><span><b>Talk to a specialist</b><small>Request a human handoff</small></span><ChevronRight size={15} /></button>
                    </div>
                    <div className="demo-hint"><Shield size={14} /> Uses sample customer and order data</div>
                  </div>
                )}
                {messages.map((message) => (
                  <Message key={message.id} message={message} onLookup={lookupOrder} />
                ))}
                {loading && <div className="typing"><span /><span /><span /> <small>Checking policy and order…</small></div>}
                {pendingAction && <ApprovalCard action={pendingAction} busy={actionLoading} onApprove={() => decideAction(true)} onDecline={() => decideAction(false)} />}
                {eligible && !pendingAction && <div className="resolution-card">
                  <div className="resolution-header"><span className="resolution-icon"><BadgeCheck size={17} /></span><span><b>Eligible for resolution</b><small>Choose an action. Nothing is written yet.</small></span></div>
                  <div className="resolution-actions">
                    <button disabled={actionLoading} onClick={() => prepareAction("refund")}><RotateCcw size={15} /> Prepare refund</button>
                    <button disabled={actionLoading} onClick={() => prepareAction("replacement")}><PackageCheck size={15} /> Prepare replacement</button>
                  </div>
                </div>}
                <div ref={bottomRef} />
              </div>

              {error && <div className="error-banner"><ShieldAlert size={15} /> {error}<button onClick={() => setError("")}><X size={14} /></button></div>}
              <form className="composer" onSubmit={(event) => { event.preventDefault(); sendMessage(); }}>
                <div className="composer-input-wrap">
                  <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask about a return, warranty, or delivery…" aria-label="Message" />
                  <span className="enter-hint">↵</span>
                </div>
                <button className="send-button" type="submit" disabled={!input.trim() || loading} aria-label="Send message">{loading ? <LoaderCircle className="spin" size={17} /> : <Send size={17} />}</button>
                <div className="composer-caption"><span><Shield size={12} /> Checks VoltTech policy</span><span>Enter to send</span></div>
              </form>
            </section>

            <aside className="inspector">
              <div className="inspector-title"><div><span className="inspector-icon"><Terminal size={15} /></span><b>Under the hood</b></div><span className="live-label"><i /> LOCAL</span></div>
              <div className="inspector-tabs">
                <button className={activeTab === "order" ? "selected" : ""} onClick={() => setActiveTab("order")}><Database size={14} /> Order data</button>
                <button className={activeTab === "trace" ? "selected" : ""} onClick={() => setActiveTab("trace")}><Cpu size={14} /> Activity</button>
              </div>
              {activeTab === "order" ? <OrderPanel order={order} orderId={orderId} onOrderId={setOrderId} onLookup={lookupOrder} /> : <TracePanel messages={messages} />}
              <div className="inspector-divider" />
              <div className="inspector-subtitle"><span><FileText size={14} /> Policy references</span><small>{latestAssistant?.sources?.length || 0}</small></div>
              {latestAssistant?.sources?.length ? <div className="source-list">
                {latestAssistant.sources.map((source, index) => <div className="source-card" key={`${source.citation}-${index}`}>
                  <div className="source-top"><span className="source-type"><BookOpen size={12} /> POLICY PDF</span><span className="source-score">Used</span></div>
                  <b>{source.title}</b><small>{source.citation}</small><p>“{source.excerpt}”</p>
                </div>)}
              </div> : <div className="empty-sources"><FileText size={17} /><span>Policy passages appear here after a question.</span></div>}
              <div className="policy-footnote"><Shield size={13} /><span>Answers cite the source. When evidence is missing, the agent won’t guess.</span></div>
            </aside>
          </div>
          <footer className="app-footer"><span>VOLTTECH SUPPORT</span><span>Policy lookup <i /> Order records <i /> Approval step</span><span>Demo</span></footer>
        </main>
      </div>
      {showQueue && <QueueDrawer tickets={tickets} onClose={() => setShowQueue(false)} />}
    </div>
  );
}

function Message({ message, onLookup }) {
  if (message.role === "user") {
    return <div className="message-row user-row"><div className="user-bubble">{message.text}<small>{formatTime(message.time)}</small></div><div className="user-avatar">AM</div></div>;
  }
  if (message.role === "system") {
    return <div className="system-message"><Check size={15} /> {message.text}<small>{formatTime(message.time)}</small></div>;
  }
  return <div className="message-row assistant-row">
    <div className="message-bot"><MessageCircle size={14} /></div>
    <div className="assistant-content">
      <div className="message-meta"><b>VoltTech Support</b><time>{formatTime(message.time)}</time></div>
      <div className="assistant-bubble">{message.answer.split("\n\n").map((paragraph, index) => <p key={index}>{renderAnswer(paragraph)}</p>)}</div>
      {message.order && <button className="inline-order" onClick={() => onLookup(message.order.id)}><ShoppingBag size={13} /> Order #{message.order.id}<ArrowDown size={12} /></button>}
      {message.escalation && <div className="escalation-notice"><span><LifeBuoy size={15} /></span><div><b>Added to the handoff queue</b><small>Ticket {message.escalation.ticket_id} · {message.escalation.reason.replaceAll("_", " ")} · {message.escalation.priority} priority</small></div><ArrowUpRight size={14} /></div>}
    </div>
  </div>;
}

function renderAnswer(text) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => part.startsWith("**") && part.endsWith("**")
    ? <strong key={index}>{part.slice(2, -2)}</strong>
    : part);
}

function OrderPanel({ order, orderId, onOrderId, onLookup }) {
  return <div className="order-panel">
    <div className="lookup-label">LOOK UP AN ORDER</div>
    <form className="lookup-form" onSubmit={(event) => { event.preventDefault(); onLookup(orderId); }}>
      <span>#</span><input value={orderId} onChange={(event) => onOrderId(event.target.value.toUpperCase())} aria-label="Order ID" /><button type="submit"><ArrowUpRight size={14} /></button>
    </form>
    {order ? <>
      <div className="order-product">
        <div className="product-placeholder"><Cpu size={23} /></div>
        <div><b>{order.item}</b><small>Order #{order.id}</small></div>
        <span className={`status-tag ${order.status === "delivered" ? "delivered" : "resolved"}`}><i /> {order.status.replaceAll("_", " ")}</span>
      </div>
      <div className="data-grid">
        <DataPoint label="TOTAL" value={`$${Number(order.price).toLocaleString("en-US", { minimumFractionDigits: 2 })}`} />
        <DataPoint label="DELIVERED" value={new Date(`${order.delivered_at}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })} />
        <DataPoint label="RETURN WINDOW" value={order.return_eligible ? `${order.days_since_delivery} / 30 days` : "Window closed"} state={order.return_eligible ? "good" : "warn"} />
        <DataPoint label="WARRANTY" value={order.warranty_active ? "Active · 1 year" : "Expired"} state={order.warranty_active ? "good" : "warn"} />
      </div>
      <div className="customer-detail"><div className="customer-avatar">{order.customer_name.split(" ").map((word) => word[0]).join("")}</div><span><b>{order.customer_name}</b><small>Verified customer</small></span><BadgeCheck size={15} /></div>
    </> : <div className="no-order"><PackageCheck size={20} /><b>No order selected</b><small>Enter an order ID to query the demo database.</small></div>}
    <div className="tool-call"><span className="tool-call-icon"><Database size={13} /></span><span><b>get_order()</b><small>SQLite · read-only lookup</small></span><span className="tool-success"><Check size={12} /> OK</span></div>
  </div>;
}

function DataPoint({ label, value, state }) {
  return <div className="data-point"><small>{label}</small><b className={state ? `state-${state}` : ""}>{value}</b></div>;
}

function TracePanel({ messages }) {
  const latest = [...messages].reverse().find((message) => message.role === "assistant");
  const steps = latest?.agent_steps || ["Waiting for a customer message", "Policy retrieval will run here", "Order lookup uses the selected order ID", "Write tools pause for approval"];
  return <div className="trace-panel">
    <div className="trace-intro"><span className="trace-pulse" /><div><b>Request steps</b><small>Request → policy → order → outcome</small></div></div>
    <div className="trace-steps">{steps.map((step, index) => <div className="trace-step" key={`${step}-${index}`}><span className={`trace-number ${index < steps.length - 1 ? "done" : ""}`}>{index < steps.length - 1 ? <Check size={11} /> : index + 1}</span><div><b>{step}</b><small>{traceDescription(step)}</small></div></div>)}</div>
    <div className="trace-separator" />
    <div className="trace-info"><Shield size={14} /><span>This view shows the checks and database actions used for the request.</span></div>
    <div className="tool-call"><span className="tool-call-icon"><Cpu size={13} /></span><span><b>support_case()</b><small>Policy lookup · order check</small></span><span className="tool-success"><Check size={12} /> READY</span></div>
  </div>;
}

function traceDescription(step) {
  if (step.includes("Retrieved")) return "Ranked policy passages by keyword relevance";
  if (step.includes("Read order")) return "Called the SQLite order read tool";
  if (step.includes("Escalated")) return "Created structured ticket; no order write";
  if (step.includes("approval")) return "Resolution tool awaits customer confirmation";
  if (step.includes("Classified")) return "Detected intent and safety signals";
  return "Source match unavailable; no unsupported claim";
}

function ApprovalCard({ action, busy, onApprove, onDecline }) {
  return <div className="approval-card">
    <div className="approval-title"><span><Shield size={16} /></span><div><b>Approval required</b><small>Review the structured action before it writes to SQLite.</small></div></div>
    <div className="payload-box"><div className="payload-label"><Terminal size={12} /> PYDANTIC PAYLOAD <span>VALID</span></div>
      <pre>{JSON.stringify({
        order_id: action.order_id,
        action_type: action.action_type,
        reason: action.reason,
        amount: `$${Number(action.amount).toFixed(2)}`,
        policy_references: action.policy_references,
      }, null, 2)}</pre>
    </div>
    <div className="approval-buttons"><button className="decline-button" disabled={busy} onClick={onDecline}>Decline</button><button className="approve-button" disabled={busy} onClick={onApprove}>{busy ? <LoaderCircle size={14} className="spin" /> : <Check size={14} />} Confirm &amp; process</button></div>
    <div className="approval-note"><Shield size={12} /> No database change happens until you confirm.</div>
  </div>;
}

function QueueDrawer({ tickets, onClose }) {
  return <div className="drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <aside className="queue-drawer">
      <div className="drawer-header"><div><span className="drawer-icon"><LifeBuoy size={16} /></span><div><b>Human handoff queue</b><small>Escalations that need a person</small></div></div><button onClick={onClose} aria-label="Close queue"><X size={18} /></button></div>
      <div className="drawer-summary"><div><b>{tickets.length}</b><small>OPEN TICKETS</small></div><div><b>{tickets.filter((ticket) => ticket.priority === "high").length}</b><small>HIGH PRIORITY</small></div></div>
      <div className="ticket-list">{tickets.length ? tickets.map((ticket) => <div className="ticket-card" key={ticket.id}>
        <div className="ticket-top"><span className={`priority-tag ${ticket.priority}`}>{ticket.priority === "high" ? <ShieldAlert size={12} /> : <Clock3 size={12} />}{ticket.priority} priority</span><small>{ticket.id}</small></div>
        <b>{ticket.order_id ? `Order #${ticket.order_id}` : "Policy question"}</b><p>{ticket.summary}</p>
        <div className="ticket-meta"><span>{ticket.reason.replaceAll("_", " ")}</span><span className="ticket-open"><i /> {ticket.status}</span></div>
      </div>) : <div className="queue-empty"><LifeBuoy size={25} /><b>All clear</b><small>Escalations will show up here.</small></div>}</div>
      <div className="queue-footer"><Shield size={14} /> Escalations are stored in the local support database.</div>
    </aside>
  </div>;
}

function formatTime(value) {
  return new Date(value).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

createRoot(document.getElementById("root")).render(<App />);
