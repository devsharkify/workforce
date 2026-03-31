# SHYRA AI — Production System
## Complete Context for Claude Code

---

## WHAT THIS IS

Shyra AI is an AI agent agency built by Rohan (Sharkify Technology Pvt Ltd, Hyderabad).
It sells custom AI agents to Indian and UAE SMEs — pharmacies, restaurants, clinics, real estate agents, chit fund operators, CA firms, logistics companies.

**Business model:**
- ₹20,000 one-time setup fee per agent
- ₹2,000/month retainer per agent
- Live in 7 days
- Payback in 30–45 days for most clients

**Tech stack:**
- Backend: Python 3.11, Flask, APScheduler, Railway (hosting)
- AI: Anthropic Claude (Opus 4.6 for heavy tasks, Haiku 4.5 for fast/cheap tasks)
- WhatsApp: authkey.io API
- Email: SendGrid
- Payments: Razorpay
- Database: Google Sheets (no SQL DB — intentional, keeps it simple)
- Frontend: shyra.pro — single HTML file on Vercel
- DNS: Cloudflare → api.shyra.pro → Railway

---

## DIRECTORY STRUCTURE

```
shyra_production/
├── agents/                        # 16 internal agents
│   ├── 01_lead_scraper.py
│   ├── 02_outreach_agent.py
│   ├── 03_proposal_generator.py
│   ├── 04_onboarding_agent.py
│   ├── 05_06_roi_upsell.py
│   ├── 07_churn_predictor.py
│   ├── 08_billing_agent.py
│   ├── 09_contract_generator.py
│   ├── 10_11_testimonial_social.py
│   ├── 12_13_intel_referral.py
│   ├── 14_15_quality_briefing.py
│   └── 16_knowledge_distiller.py
├── api/
│   ├── server.py                  # Main Flask app — all routes
│   ├── admin_routes.py            # Admin panel auth + key management
│   └── admin_panel.html           # Dark UI for managing API keys
├── core/
│   ├── config.py                  # All env vars — single source of truth
│   └── utils.py                   # Shared utilities: Claude, WhatsApp, Sheets, Email, PDF
├── orchestrator.py                # APScheduler — runs all agents on schedule
├── Procfile                       # Railway: web + worker
├── requirements.txt
└── .env.example                   # All required environment variables
```

---

## CORE UTILITIES (core/utils.py)

All external calls go through here. Never call APIs directly from agents.

### Claude
```python
ask_claude(prompt, system="", max_tokens=1024, model=None)
ask_claude_fast(prompt, system="", max_tokens=512)   # Uses Haiku
ask_claude_json(prompt, system="", model=None)        # Returns dict
```
- Default model: `claude-opus-4-6` (cfg.CLAUDE_MODEL)
- Fast model: `claude-haiku-4-5-20251001` (cfg.CLAUDE_MODEL_FAST)
- All calls have retry(3) with exponential backoff

### WhatsApp
```python
send_whatsapp(to, message)          # Raises on failure
send_whatsapp_safe(to, message)     # Returns True/False, never raises
notify_founder(message)             # Sends to cfg.FOUNDER_NUMBER
notify_sales(message)               # Sends to cfg.SALES_NUMBER
notify_build(message)               # Sends to cfg.BUILD_NUMBER
```
- `to` format: `919XXXXXXXXX` (with country code, no +)

### Google Sheets
```python
sheet_read(sheet_id, worksheet=None)         # Returns list[dict]
sheet_append(sheet_id, row_list, worksheet)  # Appends one row
get_sheet(sheet_id, worksheet=None)          # Returns gspread worksheet
```

### Email
```python
send_email(to, to_name, subject, html, attachment=None)  # Returns bool
```

### PDF
```python
generate_pdf(path, title, sections)
# sections = [{"heading": "...", "body": "..." or [["col1","col2"],["val1","val2"]]}]
```

### Helpers
```python
today()    # "2025-03-21"
now_str()  # "2025-03-21 14:30"
ts()       # ISO timestamp
```

---

## CONFIGURATION (core/config.py)

All settings from environment variables. Access via `cfg.KEY_NAME`.

```python
from core.config import cfg

cfg.ANTHROPIC_API_KEY
cfg.CLAUDE_MODEL            # "claude-opus-4-6"
cfg.CLAUDE_MODEL_FAST       # "claude-haiku-4-5-20251001"
cfg.WA_API_URL              # "https://waba.authkey.io.io/v1"
cfg.AUTHKEY_IO
cfg.WA_MAIN_NUMBER          # Prospects inbox
cfg.WA_SUPPORT_NUMBER       # Existing clients inbox
cfg.FOUNDER_NUMBER          # Rohan's WhatsApp
cfg.SALES_NUMBER
cfg.BUILD_NUMBER
cfg.SENDGRID_KEY
cfg.FROM_EMAIL              # "rohan@sharkify.ai"
cfg.MAPS_API_KEY
cfg.GOOGLE_CREDS_JSON       # Full service account JSON as string
cfg.GOOGLE_CREDS_FILE       # Or file path
cfg.LEADS_SHEET_ID          # Google Sheet for leads
cfg.CLIENTS_SHEET_ID        # Google Sheet for active clients
cfg.CALLS_SHEET_ID          # Google Sheet for booked calls
cfg.RAZORPAY_KEY
cfg.RAZORPAY_SECRET
cfg.META_TOKEN
cfg.LINKEDIN_TOKEN
cfg.LINKEDIN_ORG
cfg.SENTRY_DSN
cfg.REDIS_URL
cfg.SHYRA_CONTEXT           # Business context string injected into AI prompts
```

---

## API SERVER (api/server.py)

Flask app running on Railway. Deployed via gunicorn.

### Routes

```
POST /chat
  Body: { message, system?, conversation_history?, json_mode?, business_name?, city?, phone_collected?, outcome?, session_id? }
  Returns: { reply }
  — Claude proxy for website chatbot
  — Uses Haiku model
  — Injects knowledge base from Agent 16
  — Saves conversation for learning

POST /api/diagnosis
  Body: { phone, name, business, type, location, pain, volume, conversation, email }
  Returns: { status, diagnosis_sent }
  — Generates AI recommendation
  — Sends WhatsApp to client with agent recommendation + ROI
  — Alerts sales team
  — Logs to LEADS_SHEET_ID

POST /api/book-call
  Body: { phone, slot, meetUrl, rescheduled? }
  Returns: { status }
  — Sends WhatsApp confirmation to client
  — Alerts founder
  — Logs to CALLS_SHEET_ID

POST /webhook/inbound  (+ GET for verification)
  — WhatsApp webhook for prospects messaging main number
  — Claude qualifies and auto-replies
  — Verify token: cfg.WA_VERIFY_TOKEN

POST /webhook/support  (+ GET for verification)
  — WhatsApp webhook for existing clients on support number
  — Handles PAUSE / RESUME / UPGRADE commands
  — Claude handles support queries
  — Escalates to build team when needed

POST /webhook/meta-lead
  — Meta Ads lead form webhook
  — Instant WhatsApp to new lead
  — Schedules 5-day nurture sequence

GET /health
  Returns: { status, env, anthropic, whatsapp, email, sheets, ts }

GET /admin
  — Admin panel for API key management (password protected)

GET/POST /admin/keys
  — Read/write all API keys

POST /admin/test
  — Test a specific API key against its service

GET /admin/health
  — Run health check on all connected services
```

---

## THE 16 INTERNAL AGENTS

### Agent 01 — Lead Scraper
**File:** `agents/01_lead_scraper.py`
**Schedule:** Daily 7:00 AM IST
**What it does:**
- Scrapes Google Places API for 12 target business types in Hyderabad, Mumbai, Bangalore, Dubai
- Scores each lead 1-10 with Claude (size, AI readiness, affordability)
- Generates a personalised WhatsApp opening line for each lead
- Saves to LEADS_SHEET_ID with columns: Name, Type, City, Address, Phone, Website, Rating, Reviews, AI Score, Priority, Pain, Suggested Agent, Opening Line, Date, Status
- Skips duplicates
- 30 leads/day limit

**Run manually:**
```bash
python agents/01_lead_scraper.py
```

---

### Agent 02 — Outreach Agent
**File:** `agents/02_outreach_agent.py`
**Schedule:** Daily 9:00 AM IST
**What it does:**
- Reads LEADS_SHEET_ID, filters Status="new" with phone number
- Sorts by AI Score descending, takes top 20
- Sends personalised WhatsApp using Claude-generated opening line
- Sends email if available
- Updates Status="contacted" + Last Contacted timestamp in sheet
- 1.5 second delay between messages (WhatsApp rate limit)

**Run manually:**
```bash
python agents/02_outreach_agent.py
```

---

### Agent 03 — Proposal Generator
**File:** `agents/03_proposal_generator.py`
**Schedule:** On-demand (called by sales team after qualified call)
**What it does:**
- Claude generates full proposal content as JSON (executive summary, problem, solution, timeline, ROI)
- Generates PDF with ReportLab
- Emails PDF to client
- Sends WhatsApp summary to client
- Notifies founder
- Saves to `data/proposals/`

**Run manually:**
```bash
python agents/03_proposal_generator.py \
  --client "Kumar Pharma" \
  --type "pharmacy" \
  --phone "919876543210" \
  --email "kumar@gmail.com" \
  --pain "100+ WhatsApp orders daily, manual entry" \
  --agents "WhatsApp Order Assistant, Invoice OCR to Tally" \
  --notes "300 chemist clients, Secunderabad"
```

---

### Agent 04 — Onboarding Agent
**File:** `agents/04_onboarding_agent.py`
**Schedule:** On-demand (called on contract sign)
**What it does:**
- Day 0 (kickoff): Welcome WhatsApp + email, requests product data, alerts build team, logs to CLIENTS_SHEET_ID
- Day 1: Follow-up if no data received
- Day 3: Halfway update
- Day 5: Test session instructions
- Day 7: Go-live confirmation

**Run manually:**
```bash
python agents/04_onboarding_agent.py --step kickoff --client "Kumar Pharma" --phone "919876543210" --agents "WhatsApp Order Assistant" --type "pharmacy"
python agents/04_onboarding_agent.py --step golive --client "Kumar Pharma" --phone "919876543210"
```

---

### Agent 05 — ROI Report Generator
**File:** `agents/05_06_roi_upsell.py` — function `run_roi_reports()`
**Schedule:** 1st of every month, 9:00 AM IST
**What it does:**
- Reads all active clients from CLIENTS_SHEET_ID
- Claude estimates monthly impact numbers (queries handled, hours saved, leads captured, ROI multiple)
- Generates PDF report for each client
- Sends WhatsApp summary + PDF via email
- Saves to `data/reports/`

---

### Agent 06 — Upsell Detector
**File:** `agents/05_06_roi_upsell.py` — function `run_upsell_detector()`
**Schedule:** 5th of every month, 9:00 AM IST
**What it does:**
- Reads active clients 45+ days old with health score ≥ 7
- Claude identifies most natural next agent to upsell
- Generates personalised WhatsApp opening message
- Sends opportunity alert to sales team

---

### Agent 07 — Churn Predictor
**File:** `agents/07_churn_predictor.py`
**Schedule:** Daily 8:00 PM IST
**What it does:**
- Reads all active/paused clients
- Scores each client 0-15 across 5 signals:
  - `inactive_7d` (+3): No activity in 7+ days
  - `inactive_14d` (+5): No activity in 14+ days
  - `low_health` (+4): Health score < 5
  - `missed_payment` (+4): Payment status = overdue/missed
  - `paused` (+5): Agent paused
- Score ≥ 10: URGENT alert to founder + sales team, call within 2 hours
- Score 7-9: Claude writes personalised save message, sends to client
- Sends daily summary to founder if any at-risk

---

### Agent 08 — Billing Agent
**File:** `agents/08_billing_agent.py`
**Schedule:**
- 25th: raise_monthly_invoices()
- 27th: send_payment_reminders(1)
- 30th: send_payment_reminders(2)
- 5th next month: send_payment_reminders(3) — final notice
- Daily 10:15 AM: check_payments()
**What it does:**
- Creates Razorpay payment links (₹2,000 × number of agents)
- Sends WhatsApp + email invoice to each active client
- Three-tier reminder sequence with escalating urgency
- Daily payment status check via Razorpay API
- Updates CLIENTS_SHEET_ID payment status

---

### Agent 09 — Contract Generator
**File:** `agents/09_contract_generator.py`
**Schedule:** On-demand
**What it does:**
- Generates full service agreement PDF with: parties, scope, timeline, pricing, terms, IP, confidentiality, termination, governing law
- Sends PDF via email
- Sends WhatsApp with CONFIRM instruction
- Assigns contract ID: SHY-YYYYMMDD-XXX
- Notifies founder

**Run manually:**
```bash
python agents/09_contract_generator.py --client "Kumar Pharma" --phone "919876543210" --email "kumar@gmail.com" --agents "WhatsApp Order Assistant"
```

---

### Agent 10 — Testimonial Collector
**File:** `agents/10_11_testimonial_social.py` — function `run_testimonial_collector()`
**Schedule:** Daily 10:00 AM IST
**What it does:**
- Checks clients at day 30, 60, 90 of being active
- Only requests from clients with health score ≥ 6
- Sends warm, specific WhatsApp review request
- Marks Testimonial Requested in sheet

---

### Agent 11 — Social Media Content
**File:** `agents/10_11_testimonial_social.py` — function `run_social_content()`
**Schedule:** Mondays 9:15 AM IST
**What it does:**
- Claude generates 7 posts for the week (founder story, client win, agent explainer, industry insight, ROI data, tips, week recap)
- Posts to LinkedIn via API
- Posts to Instagram (saves draft if no image)
- Backs up all posts to Google Sheets

---

### Agent 12 — Competitor Intel
**File:** `agents/12_13_intel_referral.py` — function `run_competitor_intel()`
**Schedule:** Mondays 8:00 AM IST
**What it does:**
- Claude analyses competitive landscape vs Wati, Interakt, Yellow.ai, AiSensy, Gallabox, Haptik, and 6 others
- Extracts: market gaps, competitor weaknesses, pricing position, emerging threats, recommended actions for Shyra this week
- Sends formatted WhatsApp brief to founder

---

### Agent 13 — Referral Agent
**File:** `agents/12_13_intel_referral.py` — function `run_referral_agent()`
**Schedule:** Daily 10:30 AM IST
**What it does:**
- Finds active clients 45+ days with health score ≥ 7 who haven't been asked for referrals
- Claude writes personalised referral ask mentioning their specific success
- Offers ₹3,000 Amazon voucher per successful referral
- Marks Referral Asked in sheet

---

### Agent 14 — Quality Monitor
**File:** `agents/14_15_quality_briefing.py` — function `run_quality_monitor()`
**Schedule:** Daily 9:00 PM IST
**What it does:**
- Samples conversation logs for each active client
- Claude audits quality: accuracy, tone, helpfulness, brand voice, escalation decisions
- Scores 1-10
- Flags issues and specific fixes for scores < 6
- Updates health score in CLIENTS_SHEET_ID
- Sends alert to founder for any urgent issues

---

### Agent 15 — Morning Briefing
**File:** `agents/14_15_quality_briefing.py` — function `run_morning_briefing()`
**Schedule:** Daily 7:30 AM IST
**What it does:**
- Reads leads + clients + calls sheets
- Calculates: total leads, new today, hot leads, contacted today, active clients, onboarding clients, at-risk clients, MRR, calls today
- Claude generates 3 specific priority actions for the day
- Sends formatted WhatsApp briefing to founder

---

### Agent 16 — Knowledge Distiller
**File:** `agents/16_knowledge_distiller.py`
**Schedule:** Sundays 6:00 AM IST
**What it does:**
- Reads all chat conversations from last 7 days from `Conversations` tab in LEADS_SHEET_ID
- Claude extracts: top questions, best converting answers, industries that convert/ghost, common objections + rebuttals, what triggers phone sharing, drop-off points, language patterns, time patterns
- Saves structured knowledge base to `KnowledgeBase` tab
- This KB is injected into the chat agent system prompt on every conversation
- Result: chat agent gets smarter every week automatically

**API integration:**
```python
from agents.agent16 import load_knowledge_base, save_conversation

# In /chat route — inject KB into system prompt
kb = load_knowledge_base()

# After each conversation — save for learning
save_conversation(session_id, summary, industry, city, turns, phone_shared, outcome)
```

---

## ORCHESTRATOR (orchestrator.py)

Runs everything. One process on Railway (`worker` in Procfile).

```
Daily schedule (IST):
07:00 — Agent 01 Lead Scraper
07:30 — Agent 15 Morning Briefing
09:00 — Agent 02 Outreach
09:15 — Agent 11 Social Content (Mondays only)
10:00 — Agent 10 Testimonials
10:15 — Agent 08 Payment Check
10:30 — Agent 13 Referral
20:00 — Agent 07 Churn Predictor
21:00 — Agent 14 Quality Monitor

Weekly (Mondays):
08:00 — Agent 12 Competitor Intel
09:15 — Agent 11 Social Content
06:00 Sunday — Agent 16 Knowledge Distiller

Monthly:
1st  09:00 — Agent 05 ROI Reports
5th  09:00 — Agent 06 Upsell Detector
25th 09:00 — Agent 08 Raise Invoices
27th 10:00 — Agent 08 Reminder 1
30th 10:00 — Agent 08 Reminder 2
5th  10:00 — Agent 08 Final Notice
```

All agents run via `safe_run()` — one agent failing never stops others.

API server runs in a background thread on the same process.

---

## GOOGLE SHEETS STRUCTURE

### LEADS_SHEET_ID (tab: Sheet1)
Columns: Name, Type, City, Address, Phone, Website, Rating, Reviews, AI Score, Priority, Pain, Suggested Agent, Opening Line, Date Scraped, Status, Last Contacted, Email

### LEADS_SHEET_ID (tab: Conversations)
Columns: Session ID, Date, Industry, City, Turns, Phone Shared, Outcome, Summary, Notable Exchanges

### LEADS_SHEET_ID (tab: KnowledgeBase)
Columns: Key, Value, Updated
(Written by Agent 16, read by /chat route)

### CLIENTS_SHEET_ID (tab: Sheet1)
Columns: Client Name, Type, Phone, Email, Agents, Start Date, Expected Go-Live, Status, Health Score, Last ROI Date, Payment Status, Payment Date

### CALLS_SHEET_ID (tab: Sheet1)
Columns: Phone, Slot, Meet URL, Status, Booked At, Reminded

---

## WHATSAPP WEBHOOK SETUP

Register in authkey.io dashboard:
- Prospects: `https://api.shyra.pro/webhook/inbound` — verify token: `shyra_prod_2025`
- Clients: `https://api.shyra.pro/webhook/support` — verify token: `shyra_prod_2025_support`

Client WhatsApp commands (exact text):
- `PAUSE` → pauses their agent, alerts build team
- `RESUME` → resumes their agent, alerts build team
- `UPGRADE` → alerts sales team for upsell call

---

## RAILWAY DEPLOYMENT

**Procfile:**
```
web: gunicorn api.server:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
worker: python orchestrator.py
```

**Two services in Railway:**
1. `shyra-web` — Flask API (web process)
2. `shyra-worker` — Orchestrator (worker process)

**Custom domain:**
- `api.shyra.pro` → Railway shyra-web service
- Set in Railway → Settings → Domains
- Add CNAME in Cloudflare: `api` → Railway URL

**Required env vars (set in Railway Variables UI):**
See `.env.example` for full list. Minimum to start:
- `ANTHROPIC_API_KEY`
- `AUTHKEY_IO`
- `WA_MAIN_NUMBER`
- `FOUNDER_NUMBER`
- `SENDGRID_KEY`
- `MAPS_API_KEY`
- `GOOGLE_CREDS_JSON`
- `LEADS_SHEET_ID`
- `CLIENTS_SHEET_ID`
- `RAZORPAY_KEY` + `RAZORPAY_SECRET`

---

## ADMIN PANEL

URL: `https://api.shyra.pro/admin`
Password: set via `ADMIN_PASSWORD` env var (default: `shyra_admin_2025`)

Features:
- Enter/update all API keys in a dark UI
- Test each key against its service (green/red indicator)
- Health check all services at once
- Download .env file
- Saves to Railway env vars via Railway API (requires `RAILWAY_API_TOKEN`)
- Always saves locally to .env as backup

---

## COMMON TASKS FOR CLAUDE CODE

### Add a new agent
1. Create file in `agents/` following naming convention
2. Add `run()` function with `if __name__ == "__main__"` block
3. Add to `orchestrator.py`: import in `_load()` section + add `scheduler.add_job()`
4. Add to this README

### Add a new API route
1. Add function to `api/server.py` following existing pattern
2. Use `@admin_required` decorator for admin routes
3. Use `send_whatsapp_safe()` not `send_whatsapp()` in routes (never raise)
4. Always return `jsonify()` with status code

### Change the chat agent personality
Edit `SHYRA_CHAT_SYSTEM` in `api/server.py` (lines ~72-130)

### Change which model runs what
- Chat agent: `cfg.CLAUDE_MODEL_FAST` (Haiku — fast, cheap)
- Proposals, contracts, ROI reports: `cfg.CLAUDE_MODEL` (Opus — quality)
- Lead scoring, outreach writing: `cfg.CLAUDE_MODEL_FAST`

### Debug a failed agent
Check Railway logs → filter by agent name. All agents log with `log = logging.getLogger("shyra.agentXX")`.

### Test locally
```bash
pip install -r requirements.txt
cp .env.example .env  # fill in your keys
python api/server.py   # starts API on port 8000
python orchestrator.py # starts scheduler
```

---

## IMPORTANT RULES

1. **Never call Anthropic API directly** — always use `ask_claude()` from `core/utils.py`
2. **Never call WhatsApp API directly** — always use `send_whatsapp_safe()` for routes, `send_whatsapp()` for agents
3. **All agents must be isolated** — wrap in try/except, use `safe_run()` in orchestrator
4. **All API costs go through Shyra** — WhatsApp credits charged at cost + 40% margin to clients
5. **Google Sheets is the database** — no SQL, no MongoDB, no Supabase
6. **Indian phone numbers** — always format as `919XXXXXXXXX` (no + or spaces)
7. **Language** — chat agent responds in Hindi/Telugu if client writes in those languages
8. **Model selection** — Haiku for anything conversational or repetitive, Opus for proposals/contracts/analysis
