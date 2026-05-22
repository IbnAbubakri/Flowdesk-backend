"""FlowDesk AI Backend — bridges the dashboard to Gemini LLM."""
import os, logging, sqlite3, json, uvicorn
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("flowdesk")
app = FastAPI(title="FlowDesk AI API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GEMINI_KEY = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not GEMINI_KEY:
    raise RuntimeError("GOOGLE_API_KEY or GEMINI_API_KEY environment variable is required")
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

DB_PATH = os.path.join(os.path.dirname(__file__), "flowdesk.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE,
            email TEXT,
            status TEXT DEFAULT 'active',
            tags TEXT DEFAULT '[]',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            platform TEXT DEFAULT 'whatsapp',
            status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            sender TEXT NOT NULL CHECK(sender IN ('customer','ai','staff')),
            text TEXT NOT NULL,
            confidence REAL,
            escalated INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        );
        CREATE TABLE IF NOT EXISTS business_data (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()
    conn.close()

init_db()

SYSTEM_PROMPT = """You are FlowDesk AI, an intelligent business assistant for Nigerian SMEs.
You help business owners manage customers, track payments, analyze sales, and automate replies.

Your personality:
- Professional but warm, like a trusted business advisor
- Responses should be clear, concise, and actionable
- Use Nigerian Naira (₦) for all monetary values
- Reference Nigerian business context (SMEs, local payment methods, etc.)

Current business: Graceville International School, Lagos
Plan: Business tier (₦45,000/month)

Key business data:
- Total customers: 1,248
- Active leads: 342
- Daily messages: ~1,580
- Monthly revenue: ₦2,755,000
- Pending payments: ₦425,000
- Conversion rate: 23.5%
- Avg response time: 1.2s

Sample customers:
- Chidi Okonkwo — parent, interested in JSS1 admission, ₦350,000 unpaid
- Amina Bello — lead, asked about UK student visas, needs follow-up
- Emeka Okafor — converted, paid ₦2,500,000 deposit on Lekki apartment
- Funke Adeyemi — inactive 20 days, retail/wholesale inquiry
- Ngozi Eze — inactive 2 days, freelancer

Automation rules active:
- Price inquiry auto-reply (auto-sends pricing template)
- 3-day inactive follow-up (re-engages cold leads)
- Complaint escalation (flags to human staff)

When asked about data you don't have, offer to help with what you know rather than making up numbers. Keep responses under 3 paragraphs unless asked for details."""

# ─── Chat ───────────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(req: Request):
    try:
        body = await req.json()
        log.info(f"Chat request: {body.get('message', '')[:50]}")
    except Exception as e:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    message = body.get("message", "")
    history = body.get("history", [])
    if not message:
        return JSONResponse({"error": "Message is required"}, status_code=400)

    contents = []
    for h in history:
        role = "user" if h.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": h.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{GEMINI_URL}?key={GEMINI_KEY}",
            json={
                "contents": contents,
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            },
        )
    if r.status_code != 200:
        log.error(f"Gemini API error: {r.status_code} {r.text[:200]}")
        return JSONResponse({"error": f"AI service error: {r.status_code}"}, status_code=502)

    data = r.json()
    try:
        reply = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        reply = "No response generated."
    return JSONResponse({"reply": reply})

# ─── Inbox / Conversations ──────────────────────────────────────────────────

@app.get("/api/conversations")
async def list_conversations():
    conn = get_db()
    rows = conn.execute("""
        SELECT c.id, c.customer_id, c.platform, c.status, c.updated_at,
               cu.name AS customer_name, cu.phone AS customer_phone,
               (SELECT text FROM messages WHERE conversation_id = c.id ORDER BY id DESC LIMIT 1) AS last_message,
               (SELECT sender FROM messages WHERE conversation_id = c.id ORDER BY id DESC LIMIT 1) AS last_sender
        FROM conversations c
        JOIN customers cu ON cu.id = c.customer_id
        ORDER BY c.updated_at DESC
    """).fetchall()
    conn.close()
    return JSONResponse([dict(r) for r in rows])

@app.get("/api/conversations/{conv_id}/messages")
async def get_messages(conv_id: int):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC", (conv_id,)
    ).fetchall()
    conn.close()
    return JSONResponse([dict(r) for r in rows])

@app.post("/api/conversations/{conv_id}/reply")
async def staff_reply(conv_id: int, req: Request):
    body = await req.json()
    text = body.get("text", "")
    if not text:
        return JSONResponse({"error": "Text is required"}, status_code=400)

    conn = get_db()
    conn.execute(
        "INSERT INTO messages (conversation_id, sender, text) VALUES (?, 'staff', ?)",
        (conv_id, text),
    )
    conn.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
        (conv_id,),
    )
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True})

# ─── Ingest WhatsApp message ────────────────────────────────────────────────

@app.post("/api/webhook/whatsapp")
async def whatsapp_webhook(req: Request):
    """Webhook for WhatsApp messages (called by the bridge)."""
    body = await req.json()
    phone = body.get("from", "")
    text = body.get("text", "")
    name = body.get("name", phone)

    conn = get_db()
    cur = conn.execute("SELECT id FROM customers WHERE phone = ?", (phone,))
    customer = cur.fetchone()

    if customer:
        customer_id = customer["id"]
    else:
        cur = conn.execute(
            "INSERT INTO customers (name, phone) VALUES (?, ?)", (name, phone)
        )
        customer_id = cur.lastrowid

    # Find or create a conversation
    cur = conn.execute(
        "SELECT id FROM conversations WHERE customer_id = ? AND status = 'open'",
        (customer_id,),
    )
    conv = cur.fetchone()
    if conv:
        conv_id = conv["id"]
    else:
        cur = conn.execute(
            "INSERT INTO conversations (customer_id, platform) VALUES (?, 'whatsapp')",
            (customer_id,),
        )
        conv_id = cur.lastrowid

    conn.execute(
        "INSERT INTO messages (conversation_id, sender, text) VALUES (?, 'customer', ?)",
        (conv_id, text),
    )
    conn.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
        (conv_id,),
    )
    conn.commit()

    # Auto-reply with AI
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{GEMINI_URL}?key={GEMINI_KEY}",
            json={
                "contents": [{"role": "user", "parts": [{"text": text}]}],
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            },
        )

    if r.status_code == 200:
        try:
            reply = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            reply = "Sorry, I couldn't process that."
    else:
        reply = "Sorry, I'm having trouble connecting. A staff member will respond shortly."

    conn.execute(
        "INSERT INTO messages (conversation_id, sender, text, confidence) VALUES (?, 'ai', ?, 0.85)",
        (conv_id, reply),
    )
    conn.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
        (conv_id,),
    )
    conn.commit()
    conn.close()

    return JSONResponse({"reply": reply})

# ─── Customers ──────────────────────────────────────────────────────────────

@app.get("/api/customers")
async def list_customers():
    conn = get_db()
    rows = conn.execute("""
        SELECT cu.*,
            (SELECT text FROM messages m
             JOIN conversations c ON c.id = m.conversation_id
             WHERE c.customer_id = cu.id
             ORDER BY m.id DESC LIMIT 1) AS last_message,
            (SELECT created_at FROM messages m
             JOIN conversations c ON c.id = m.conversation_id
             WHERE c.customer_id = cu.id
             ORDER BY m.id DESC LIMIT 1) AS last_contacted
        FROM customers cu ORDER BY cu.id DESC
    """).fetchall()
    conn.close()
    return JSONResponse([dict(r) for r in rows])

# ─── Health ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "model": GEMINI_MODEL, "db": DB_PATH}

@app.get("/")
async def root():
    return {
        "status": "FlowDesk AI API is running",
        "endpoints": [
            "GET  /api/health",
            "POST /api/chat",
            "GET  /api/conversations",
            "GET  /api/conversations/:id/messages",
            "POST /api/conversations/:id/reply",
            "POST /api/webhook/whatsapp",
            "GET  /api/customers",
        ],
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3001)
