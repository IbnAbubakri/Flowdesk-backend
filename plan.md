# FlowDesk AI — Project Status

## What's Working Now

### Frontend (flowdesk-demo) — Next.js 14 + Tailwind
- Login / Signup pages
- Dashboard with stats cards + charts (Recharts)
- **Inbox** — now live with real conversations + messages from SQLite DB
- Customers (CRM table — connected to real API)
- Automation rules list with toggle
- Payments ledger
- Analytics page with metrics + charts
- **AI Assistant** — connected to real Gemini LLM with business context
- Settings page (business info, team, dark mode, subscription tiers)

### Backend (Python FastAPI — port 3001)
- **`flowdesk_api.py`** — live AI backend powered by **Gemini 2.5 Flash**
- System prompt tuned for Nigerian SME business assistant
- **SQLite database** (`flowdesk.db`) — stores customers, conversations, messages
- **WhatsApp webhook** — receives incoming messages, auto-replies with AI
- API endpoints:
  - `GET  /api/health` — health check
  - `POST /api/chat` — AI Assistant chat
  - `GET  /api/conversations` — list conversations for inbox
  - `GET  /api/conversations/:id/messages` — get messages
  - `POST /api/conversations/:id/reply` — staff reply
  - `POST /api/webhook/whatsapp` — WhatsApp message ingest
  - `GET  /api/customers` — customer list

### WhatsApp Bridge (Node.js + Baileys)
- **`whatsapp-bridge/bridge.js`** — connects to WhatsApp Web via QR code
- Forwards incoming messages to the API webhook
- AI auto-replies directly on WhatsApp
- All conversations stored in SQLite, visible in dashboard Inbox

### AI Engine
- **Hermes Agent** (NousResearch) cloned to `wjeff/hermes-agent/`
- Python 3.11 venv with dependencies installed
- Configured with Gemini + Groq API keys
- WhatsApp bridge uses Baileys library directly (lighter than full Hermes gateway)

## Architecture
```
Phone                           Windows (port 3001)                    Browser (port 3000)
┌─────────┐   WhatsApp msg     ┌──────────────────────┐   HTTP        ┌─────────────────┐
│ WhatsApp │ ──────────────→   │  flowdesk_api.py     │ ←─────────→  │  flowdesk-demo  │
│  App     │                   │  FastAPI + Gemini     │              │  Next.js 14     │
│          │ ←── AI reply ─── │  SQLite DB            │              │  Dashboard       │
└─────────┘                   └──────────────────────┘              └─────────────────┘
       ↑                              ↑
       │    QR code pair              │ POST /api/webhook/whatsapp
       │                              │
  ┌────┴──────────────────┐           │
  │  whatsapp-bridge/     │───────────┘
  │  bridge.js (Node.js)  │
  │  @baileys             │
  └───────────────────────┘
```

## API Keys Status
| Provider | Key | Status |
|----------|-----|--------|
| Gemini 2.5 Flash | Set via `GOOGLE_API_KEY` env var | ✅ Working |
| Groq (llama-3.3-70b) | Set via `GROQ_API_KEY` env var | ✅ Working |

## File Structure
```
wjeff/
├── flowdesk-demo/              # Next.js frontend dashboard
│   └── src/
│       ├── app/
│       │   ├── page.tsx                     # Login
│       │   ├── signup/page.tsx
│       │   ├── dashboard/page.tsx           # Main dashboard
│       │   ├── dashboard/inbox/page.tsx     # REAL conversations from DB
│       │   ├── dashboard/customers/page.tsx
│       │   ├── dashboard/automation/page.tsx
│       │   ├── dashboard/payments/page.tsx
│       │   ├── dashboard/analytics/page.tsx
│       │   ├── dashboard/ai-assistant/page.tsx  # Live Gemini chat
│       │   └── dashboard/settings/page.tsx
│       ├── components/
│       ├── hooks/
│       └── lib/mock-data.ts
├── hermes-agent/               # Cloned Hermes Agent repo
│   ├── flowdesk_api.py              # FastAPI backend (Gemini + DB)
│   ├── flowdesk.db                  # SQLite database (auto-created)
│   ├── .env                         # API keys
│   ├── cli-config.yaml              # Gemini provider config
│   ├── venv/                        # Python 3.11 virtual env
│   └── whatsapp-bridge/             # WhatsApp connector
│       ├── bridge.js                # Baileys WhatsApp bridge
│       ├── package.json
│       └── auth_info/               # WhatsApp session (auto-created)
├── api.txt
├── plan.md
├── PRD Document.md
├── Proposal Paper.md
└── App Architecture.md
```

## How to Run (Windows — 3 terminals)

### Terminal 1 — Backend API
```cmd
cd C:\Users\USER\Desktop\wjeff\hermes-agent
python flowdesk_api.py
```

### Terminal 2 — WhatsApp Bridge
```cmd
cd C:\Users\USER\Desktop\wjeff\hermes-agent\whatsapp-bridge
node bridge.js
```
Scan QR code with WhatsApp phone app.

### Terminal 3 — Frontend Dashboard
```cmd
cd C:\Users\USER\Desktop\wjeff\flowdesk-demo
npm run dev
```
Open `http://localhost:3000/dashboard/inbox`

## Data Flow
1. Customer sends WhatsApp message
2. Bridge receives it → forwards to `/api/webhook/whatsapp`
3. API stores message in SQLite, calls Gemini for auto-reply
4. API returns reply → Bridge sends it back on WhatsApp
5. Staff sees conversation in real-time at `/dashboard/inbox`
6. Staff can reply from dashboard → stored in DB

## Next Steps
- Deploy backend (Railway/Render) with PostgreSQL upgrade
- Add real automation rules engine (triggers → actions)
- Build analytics on real message data
- Add payment tracking integration
- Create Hermes Agent skill for advanced FlowDesk tools
