"""
SHYRA PRODUCTION — Main API Server
=====================================
Single Flask app exposing all API endpoints.
Runs on Railway behind gunicorn.

Routes:
  POST /chat                — Claude proxy (website chatbot)
  POST /api/diagnosis       — Website booking form submission
  POST /api/book-call       — Slot booking + WhatsApp confirmations
  GET/POST /webhook/inbound — WhatsApp inbound (prospects)
  GET/POST /webhook/support — WhatsApp inbound (clients)
  GET  /health              — Health check
"""
import os
import logging
import sentry_sdk
from flask import Flask, request, jsonify
from flask_cors import CORS
from sentry_sdk.integrations.flask import FlaskIntegration

from core.config import cfg, validate
from core.utils import ask_claude, ask_claude_json, send_whatsapp_safe, notify_founder, notify_sales, sheet_append, ts, today

# ── Sentry error tracking
if cfg.SENTRY_DSN:
    sentry_sdk.init(dsn=cfg.SENTRY_DSN, integrations=[FlaskIntegration()], traces_sample_rate=0.1)

# ── Logging
logging.basicConfig(
    level=logging.DEBUG if cfg.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("shyra.api")

# ── App
app = Flask(__name__)
CORS(app, origins=["https://shyra.pro", "https://www.shyra.pro", "http://localhost:*", "https://*.vercel.app"])

# Register admin blueprint
from api.admin import admin_bp
app.register_blueprint(admin_bp)

validate()

# Register ElevenLabs voice agent routes
from api.elevenlabs_routes import register_elevenlabs_routes
register_elevenlabs_routes(app)



def search_business_website(business_name: str, city: str = "") -> str:
    """Search Google for a business website when client doesn't share it."""
    try:
        query = f"{business_name} {city} website official".strip()
        url = f"https://www.googleapis.com/customsearch/v1"
        params = {
            "key": cfg.MAPS_API_KEY,  # reuse Google key
            "cx": os.getenv("GOOGLE_CSE_ID", ""),
            "q": query,
            "num": 3
        }
        resp = requests.get(url, params=params, timeout=5)
        if resp.ok:
            items = resp.json().get("items", [])
            if items:
                return items[0].get("link", "")
    except Exception:
        pass
    return ""


def enrich_business_from_name(business_name: str, city: str = "") -> dict:
    """
    When client mentions their business name but not website,
    use Claude to reason about their likely business type and pain points.
    """
    if not business_name:
        return {}
    prompt = f"""Business name: "{business_name}" in {city or "India"}

Based on the name alone, infer:
1. Most likely business type
2. Top 2 pain points typical for this type
3. Most relevant Shyra AI agent for them
4. A specific, intelligent follow-up question that shows we understand their business

Return JSON: {{"type":"...","pain":"...","agent":"...","followup":"..."}}"""
    try:
        return ask_claude_json(prompt, model=cfg.CLAUDE_MODEL_FAST)
    except Exception:
        return {}

# ══════════════════════════════════════════════
# ROUTE 1 — Claude Chat Proxy
# ══════════════════════════════════════════════
@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    """
    Proxy Claude API calls from website chatbot.
    Keeps Anthropic API key hidden server-side.
    """
    if request.method == "OPTIONS":
        return _cors_preflight()

    data = request.json or {}
    message = data.get("message", "")
    system_override = data.get("system", "")
    conversation = data.get("conversation_history", [])
    json_mode = data.get("json_mode", False)

    if not message:
        return jsonify({"reply": ""}), 400

    # Load KB learnings from past conversations (Agent 16 updates this weekly)
    kb_injection = ""
    try:
        from agents.agent16 import load_knowledge_base
        kb_injection = load_knowledge_base()
    except Exception:
        pass

    SHYRA_CHAT_SYSTEM = system_override or f"""You are Shyra — an AI built by Shyra AI (shyra.pro) to have a real conversation with business owners.

YOUR ONLY JOB: Have a natural, intelligent conversation. Understand their business. Recommend the right AI agent. Get them to book a call.

{cfg.SHYRA_CONTEXT}

HOW TO CONVERSE:
- Talk like a smart, warm friend who happens to know AI — not a salesperson running a script
- Never ask a fixed list of questions. React to exactly what they say.
- If they say "I run a pharmacy" — respond specifically to pharmacy problems, not generic ones
- If they say "my staff waste time on WhatsApp" — dig into that specifically
- If they say "we do ₹50L a month" — acknowledge the scale and calibrate your recommendation
- One question at a time. Never interrogate.
- Read their tone — if they're casual, be casual. If they're formal, match it.
- If they write in Hindi or Telugu, respond in the same language naturally

WHAT YOU'RE TRYING TO LEARN (extract naturally through conversation, never as a form):
1. Business name (pick it up from how they describe themselves)
2. Business type and size (understand from context — don't ask directly)
3. Their actual problem (let them tell the story — don't suggest problems)
4. Website or WhatsApp number (ask only when the conversation is warm)
5. Urgency / timeline (understand from their language — "we're struggling" = urgent)
6. Decision maker (understand from "I" vs "we need to discuss")

WHAT YOU KNOW (use this to give specific, credible answers):
- Shyra builds AI agents for Indian/UAE SMEs
- Setup: ₹20,000 one-time. Monthly: ₹2,000/agent. Live in 7 days.
- Agents available: WhatsApp order assistant, lead qualifier, appointment booking, invoice OCR to Tally, customer follow-up, payment reminder, stock query bot, chit fund tracker, RERA compliance, HR onboarding, delivery tracking, and 40+ more
- Most clients recover cost in 30-45 days
- We serve Hyderabad, Mumbai, Bangalore, Dubai, US

WHEN TO RECOMMEND:
- Only after you genuinely understand their business — not in the first 2 exchanges
- Make the recommendation specific: "For a pharmacy getting 80+ WhatsApp orders daily, the WhatsApp Order Assistant would..." — not generic
- Give a real ROI number based on what they told you

WHEN TO ASK FOR PHONE/BOOKING:
- Only after they've shown clear interest (asked about pricing, asked how it works, said yes to a question)
- Never ask for phone before building trust — this is the #1 drop-off cause
- When you do ask: "What's the best number to reach you on WhatsApp? I'll send you the booking link directly."

CONVERSATION ENDINGS:
- If they want to book → collect WhatsApp number → confirm slot
- If they're browsing → give them something valuable, leave door open
- If they're skeptical → don't push, address the concern directly

WHAT YOU NEVER DO:
- Never ask the same question twice
- Never use bullet point lists in your replies — write like a human texts
- Never say "Great question!" or "Absolutely!" — these sound robotic
- Never give a canned pitch — every reply should feel written specifically for this person
- Never mention competitors
- Never make up specific numbers you don't know

{kb_injection}"""

    try:
        if json_mode:
            reply = ask_claude_json(message, system=SHYRA_CHAT_SYSTEM)
            return jsonify({"reply": json.dumps(reply)}), 200
        else:
            # Build messages list if conversation history provided
            if conversation and isinstance(conversation, list):
                try:
                    import anthropic as ac
                    client = ac.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
                    resp = client.messages.create(
                        model=cfg.CLAUDE_MODEL_FAST,  # Haiku — fast, cheap, long convos
                        max_tokens=600,
                        system=SHYRA_CHAT_SYSTEM,
                        messages=conversation
                    )
                    reply = resp.content[0].text.strip()
                except Exception as e:
                    log.error(f"Conversation history call failed: {e}")
                    reply = ask_claude(message, system=SHYRA_CHAT_SYSTEM, max_tokens=600, model=cfg.CLAUDE_MODEL_FAST)
            else:
                reply = ask_claude(message, system=SHYRA_CHAT_SYSTEM, max_tokens=600, model=cfg.CLAUDE_MODEL_FAST)

        # Save conversation turn for learning
        try:
            from agents.agent16 import save_conversation
            phone_shared = bool(data.get("phone_collected"))
            outcome = data.get("outcome", "browsing")
            if len(conversation) > 8 or phone_shared:
                save_conversation(
                    session_id=data.get("session_id", "unknown"),
                    summary=f"Q: {message[:100]} A: {reply[:100]}",
                    industry=data.get("industry", ""),
                    city=data.get("city", ""),
                    turns=len(conversation),
                    phone_shared=phone_shared,
                    outcome=outcome
                )
        except Exception:
            pass

        return jsonify({"reply": reply}), 200

    except Exception as e:
        log.error(f"Chat error: {e}")
        return jsonify({"reply": "I'd love to help — book a free diagnosis call and our founder will speak with you directly."}), 200


import json


# ══════════════════════════════════════════════
# ROUTE 2 — Website Diagnosis Form
# ══════════════════════════════════════════════
@app.route("/api/diagnosis", methods=["POST", "OPTIONS"])
def diagnosis():
    """
    Handles website booking form / chatbot submission.
    1. Generates AI diagnosis
    2. Sends WhatsApp to client with recommendation
    3. Notifies sales team
    4. Logs to Google Sheets
    """
    if request.method == "OPTIONS":
        return _cors_preflight()

    data = request.json or {}
    phone = data.get("phone", "").replace("+", "").replace(" ", "")
    name = data.get("name", "")
    business = data.get("business", "")
    biz_type = data.get("type", "")
    location = data.get("location", "Hyderabad")
    pain = data.get("pain", "")
    volume = data.get("volume", "")
    conversation = data.get("conversation", [])

    log.info(f"Diagnosis: {name} / {business} / {phone[:6]}****")

    # Generate recommendation
    rec = {"agent": "AI Automation Suite", "why": "Automates your daily operations end-to-end.", "roi": "₹10,000–18,000/month", "payback": "42"}
    try:
        prompt = f"""Business: {business} ({biz_type}) in {location}.
Pain: {pain}. Volume: {volume}/day WhatsApp messages.
Conversation context: {str(conversation)[:500]}

Return JSON — no markdown:
{{"agent":"<best Shyra agent>","why":"<one sentence specific to their business>","roi":"<₹X,000/month>","payback":"<days as integer>"}}"""
        rec = ask_claude_json(prompt, system=cfg.SHYRA_CONTEXT)
    except Exception as e:
        log.warning(f"Rec generation failed: {e}")

    # WhatsApp to client
    client_msg = f"""*Your Free Shyra AI Diagnosis* 🤖

Hi {name.split()[0] if name else 'there'}!

Based on your {biz_type or 'business'}:

🤖 *Best agent for you:* {rec.get('agent')}
💡 {rec.get('why')}
💰 *Monthly saving:* {rec.get('roi')}
⚡ *Payback:* {rec.get('payback')} days
📅 *Live in:* 7 days
💸 Setup: ₹20,000 · Monthly: ₹2,000

Our founder will call you within 2 hours.
No prep needed — just pick up. 🙏

— Shyra AI Team"""

    if phone:
        send_whatsapp_safe(phone, client_msg)

    # Notify sales
    sales_msg = f"""*New Diagnosis* 🎯

👤 {name} — {business}
🏢 {biz_type} · {location}
📱 +{phone}
💬 {pain[:80]}

🤖 Rec: {rec.get('agent')}
💰 ROI: {rec.get('roi')}

*Call within 2 hours ⚡*"""
    notify_sales(sales_msg)

    # Log to Sheets
    if cfg.LEADS_SHEET_ID:
        sheet_append(cfg.LEADS_SHEET_ID, [
            name, business, biz_type, location, phone,
            data.get("email", ""), pain[:120], volume,
            rec.get("agent"), rec.get("roi"), ts(), "website", "new"
        ])

    return jsonify({"status": "ok", "diagnosis_sent": bool(phone)}), 200


# ══════════════════════════════════════════════
# ROUTE 3 — Book Call
# ══════════════════════════════════════════════
@app.route("/api/book-call", methods=["POST", "OPTIONS"])
def book_call():
    """
    Called when client picks a time slot.
    Sends WhatsApp confirmations + logs call.
    """
    if request.method == "OPTIONS":
        return _cors_preflight()

    data = request.json or {}
    phone = data.get("phone", "")
    slot = data.get("slot", "")
    meet_url = data.get("meetUrl", "")
    rescheduled = data.get("rescheduled", False)

    log.info(f"Call booked: {phone[:6]}**** → {slot}")

    # Client confirmation
    action = "rescheduled to" if rescheduled else "confirmed for"
    client_msg = f"""*Call {"Rescheduled 🔄" if rescheduled else "Confirmed! ✅"}*

Your free Shyra AI diagnosis call is {action}:

📅 *{slot}*
🎥 Join: {meet_url}

*What to expect:*
• 30 minutes, no prep needed
• We map your business operations
• You get exact agent recommendation + ROI numbers
• No pitch — just specific data

⏰ Reminder coming 30 mins before.
Reply RESCHEDULE if you need a different time.

— Shyra AI Team"""

    send_whatsapp_safe(phone, client_msg)

    # Founder alert
    action_word = "Rescheduled" if rescheduled else "New Call"
    notify_founder(f"*{action_word}: {slot}* {'🔄' if rescheduled else '🎯'}\n📱 +{phone}\n🎥 {meet_url}")

    # Log
    if cfg.CALLS_SHEET_ID:
        sheet_append(cfg.CALLS_SHEET_ID, [
            phone, slot, meet_url,
            "rescheduled" if rescheduled else "booked",
            ts(), "no"  # reminded=no
        ])

    return jsonify({"status": "ok"}), 200


# ══════════════════════════════════════════════
# ROUTE 4 — WhatsApp Inbound Webhook (Prospects)
# ══════════════════════════════════════════════
@app.route("/webhook/inbound", methods=["GET", "POST"])
def webhook_inbound():
    """
    Handles inbound WhatsApp messages via authkey.io webhook.

    Register in authkey.io console:
      Settings → Webhook → Inbound URL: https://api.shyra.pro/webhook/inbound

    authkey.io sends POST with JSON body:
    {
      "mobile": "919XXXXXXXX",
      "message": "Hi",
      "type": "text",
      "name": "Ravi Kumar"
    }
    """
    if request.method == "GET":
        # authkey.io may send a GET to verify — return 200
        return "OK", 200

    data = request.json or {}

    # ── authkey.io inbound format
    number = str(data.get("mobile", data.get("from", ""))).strip()
    msg_type = data.get("type", "text")
    text = ""

    if msg_type == "text":
        text = data.get("message", data.get("text", {}).get("body", ""))
    elif msg_type == "audio":
        text = "[voice message — please type your question]"
    elif msg_type in ("image", "document", "video"):
        text = f"[{msg_type} received — please describe what you need]"
    elif msg_type == "button":
        # Quick reply button response
        text = data.get("button", {}).get("text", data.get("message", ""))
    elif msg_type == "interactive":
        # List reply or button reply
        interactive = data.get("interactive", {})
        if interactive.get("type") == "button_reply":
            text = interactive.get("button_reply", {}).get("title", "")
        elif interactive.get("type") == "list_reply":
            text = interactive.get("list_reply", {}).get("title", "")

    # Normalize number
    if number and not number.startswith("91"):
        number = f"91{number}" if len(number) == 10 else number

    if number and text:
        log.info(f"Inbound prospect {number[:6]}****: {text[:60]}")
        try:
            reply = _handle_prospect(number, text)
            send_whatsapp_safe(number, reply)
        except Exception as e:
            log.error(f"Inbound handler error: {e}")

    return jsonify({"status": "ok"}), 200


def _handle_prospect(number: str, message: str) -> str:
    """Claude-powered prospect qualification via WhatsApp."""
    system = f"""You are Shyra AI's WhatsApp sales assistant. Someone messaged the main number.
{cfg.SHYRA_CONTEXT}
Your job: Understand what they need, qualify them (what business? what problem?), and push toward a free 30-minute diagnosis call.
Keep replies under 4 sentences. Be warm and specific. Speak like a founder, not a bot.
If they ask pricing: ₹20,000 setup + ₹2,000/month. Payback typically 30-45 days.
To book a call: direct them to shyra.pro"""

    try:
        reply = ask_claude(
            f"WhatsApp message from prospect: {message}\nRespond helpfully.",
            system=system, max_tokens=300
        )
        # Log new prospect
        if cfg.LEADS_SHEET_ID:
            sheet_append(cfg.LEADS_SHEET_ID, [
                "", "", "WhatsApp inbound", "", number,
                "", message[:120], "", "", "", ts(), "whatsapp", "new"
            ])
        return reply
    except Exception as e:
        log.error(f"Prospect handler: {e}")
        return "Hi! I'm Shyra AI. Tell me about your business and I'll show you which agent saves you the most time and money. 🙏"


# ══════════════════════════════════════════════
# ROUTE 5 — WhatsApp Support Webhook (Clients)
# ══════════════════════════════════════════════
@app.route("/webhook/support", methods=["GET", "POST"])
def webhook_support():
    """Handles messages to Shyra's support number (existing clients)."""
    if request.method == "GET":
        return _verify_webhook(request, cfg.WA_VERIFY_TOKEN + "_support")

    data = request.json or {}
    for msg in data.get("messages", []):
        number = msg.get("from", "")
        text = msg.get("text", {}).get("body", "") if msg.get("type") == "text" else ""
        if number and text:
            log.info(f"Support from {number[:6]}****: {text[:60]}")
            try:
                reply = _handle_support(number, text)
                send_whatsapp_safe(number, reply)
            except Exception as e:
                log.error(f"Support handler error: {e}")

    return jsonify({"status": "ok"}), 200


CLIENT_SUPPORT_SYSTEM = """You are Shyra AI's client support assistant via WhatsApp.
Existing paying clients message here with questions about their AI agents.

Common answers:
- Update product list: "Send the updated list here and we'll update within 24 hours"
- Agent gave wrong answer: "Screenshot and send — we'll fix within 4 hours"
- Add new product: "Reply with details and it's done within 24 hours"
- Change escalation number: "Reply with new number — done in 2 hours"
- Check conversations: "Log in to WhatsApp Business dashboard or ask for a weekly summary"
- Pause agent: Reply PAUSE
- Resume agent: Reply RESUME
- Second agent: Reply UPGRADE

Commands handled: PAUSE, RESUME, UPGRADE
Escalation to build team for: complaints, agent errors, billing issues
Keep replies under 3 sentences. Sound like a helpful teammate."""


def _handle_support(number: str, message: str) -> str:
    msg_lower = message.lower().strip()

    # Hard commands
    if msg_lower == "pause":
        notify_build(f"⚠️ PAUSE REQUEST from {number}")
        return "Your agent will be paused within 1 hour. Reply RESUME when you want it back online. ✅"

    if msg_lower == "resume":
        notify_build(f"▶️ RESUME REQUEST from {number}")
        return "Your agent will be back online within 1 hour. ✅"

    if "upgrade" in msg_lower or "second agent" in msg_lower:
        notify_sales(f"🔥 UPGRADE INTEREST from {number}")
        return "Our team will call you within 24 hours to discuss your second agent. Exciting times ahead! 🚀"

    try:
        reply = ask_claude(
            f"Client WhatsApp support message: {message}",
            system=CLIENT_SUPPORT_SYSTEM, max_tokens=200
        )
        # Escalate if AI says it can't handle
        if any(w in reply.lower() for w in ["build team", "flag", "escalat"]):
            notify_build(f"Support escalation\n+{number}\n{message[:100]}")
        return reply
    except Exception:
        return "Thanks for reaching out! I'm forwarding this to our build team — you'll hear back within 4 hours. 🙏"


# ══════════════════════════════════════════════

# ══════════════════════════════════════════════
# ROUTE 7 — Meta Lead Ads Webhook
# ══════════════════════════════════════════════
# Setup in Meta Business Manager:
# Webhooks → leads → URL: https://api.shyra.pro/webhook/meta-lead
# Verify token: set META_VERIFY_TOKEN in env (default: shyra_meta_2026)
#
# Also set in Meta Lead Ads form:
# Fields to collect: full_name, phone_number, email, custom question "Business type"

META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "shyra_meta_2026")

# 5-day nurture messages
NURTURE_SEQUENCE = [
    # Day 1 — immediate
    lambda name, biz: f"""Hi {name}! 👋

Saw your interest in Shyra AI. Running a {biz}?

Most {biz}s we work with spend 3-4 hours daily on WhatsApp orders, follow-ups, and customer queries — all manual.

We automate all of that. Live in 7 days.

Tell me — what's the biggest time drain in your business right now?

— Rohan, Shyra AI""",

    # Day 2
    lambda name, biz: f"""Hi {name}, quick follow-up from yesterday.

A {biz} in Hyderabad just automated their WhatsApp orders — their team went from 4 hours/day to zero. Setup was done in 6 days.

We have a free 30-min call to show you exactly how it'd work for your business. No commitment.

Interested? Reply with a time that works. 🙏""",

    # Day 4
    lambda name, biz: f"""Hi {name} — one more from Shyra AI.

Quick question: how many customer WhatsApp messages does your team handle daily?

If it's more than 20, you're losing money on manual work. We can show you the rupee number in 10 minutes.

Free call, zero pressure: https://shyra.pro""",

    # Day 7 — final
    lambda name, biz: f"""Hi {name}, last message from me.

If AI automation for your {biz} ever becomes a priority — we're at shyra.pro.

₹20,000 setup. ₹2,000/month. Live in 7 days. Pays for itself in 43 days.

Wishing you and your business the best. 🙏

— Rohan, Shyra AI"""
]

def schedule_nurture(phone: str, name: str, biz_type: str):
    """Schedule 5-day WhatsApp nurture sequence via APScheduler."""
    from orchestrator import scheduler
    from datetime import datetime, timedelta
    now = datetime.now()
    delays = [0, 1, 3, 6]  # days after lead capture
    for i, day in enumerate(delays):
        run_at = now + timedelta(days=day, hours=2) if day > 0 else now + timedelta(minutes=2)
        msg = NURTURE_SEQUENCE[i](name, biz_type)
        try:
            scheduler.add_job(
                lambda p=phone, m=msg: send_whatsapp_safe(p, m),
                "date", run_date=run_at,
                id=f"nurture_{phone}_{i}",
                replace_existing=True
            )
        except Exception:
            pass  # scheduler may not be available in this process


@app.route("/webhook/meta-lead", methods=["GET", "POST"])
def meta_lead_webhook():
    # ── Verification (Meta sends GET to verify)
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == META_VERIFY_TOKEN:
            log.info("Meta webhook verified")
            return challenge, 200
        return "Forbidden", 403

    # ── Incoming lead
    try:
        data = request.json or {}
        log.info(f"Meta lead received: {str(data)[:200]}")

        # Extract lead data from Meta payload
        entry = data.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        lead_id = value.get("leadgen_id", "")
        page_id = value.get("page_id", "")

        # Fetch full lead data from Meta Graph API
        name, phone, email, biz_type = "", "", "", "business"
        if lead_id and cfg.META_TOKEN:
            try:
                resp = requests.get(
                    f"https://graph.facebook.com/v19.0/{lead_id}",
                    params={"access_token": cfg.META_TOKEN,
                            "fields": "field_data,created_time,ad_name,form_id"},
                    timeout=8
                )
                if resp.ok:
                    lead_data = resp.json()
                    for field in lead_data.get("field_data", []):
                        fname = field.get("name", "").lower()
                        fval = field.get("values", [""])[0]
                        if "name" in fname: name = fval
                        elif "phone" in fname: phone = fval.replace("+", "").replace(" ", "").replace("-", "")
                        elif "email" in fname: email = fval
                        elif "business" in fname or "type" in fname: biz_type = fval
            except Exception as e:
                log.warning(f"Meta lead fetch error: {e}")

        # Normalize phone
        if phone and not phone.startswith("91"):
            if len(phone) == 10: phone = "91" + phone

        first_name = name.split()[0] if name else "there"
        log.info(f"Meta lead: {name} | {phone} | {biz_type}")

        # 1. Score lead with Claude
        score_prompt = f"""Business type: {biz_type}. Score 1-10 for AI agent potential.
Return JSON: {{"score":7,"priority":"hot","recommended_agent":"...","opening_roi":"..."}}"""
        try:
            score = ask_claude_json(score_prompt, model=cfg.CLAUDE_MODEL_FAST)
        except Exception:
            score = {"score": 7, "priority": "warm", "recommended_agent": "WhatsApp Support Agent", "opening_roi": "saves 2-3 hrs/day"}

        # 2. Instant WhatsApp to lead (within 60 seconds)
        if phone:
            opening = NURTURE_SEQUENCE[0](first_name, biz_type)
            send_whatsapp_safe(phone, opening)

        # 3. Alert sales team
        priority = score.get("priority", "warm")
        alert = f"""*New Meta Lead* {"🔥" if priority=="hot" else "⚡"}

Name: {name}
Phone: {phone}
Email: {email}
Business: {biz_type}
AI Score: {score.get("score")}/10 ({priority})
Agent: {score.get("recommended_agent")}
ROI: {score.get("opening_roi")}
Ad: {value.get("ad_name","unknown")}

WhatsApp sent ✓"""
        notify_sales(alert)
        if priority == "hot":
            notify_founder(alert)

        # 4. Save to Leads Sheet
        if cfg.LEADS_SHEET_ID:
            sheet_append(cfg.LEADS_SHEET_ID, [
                name, biz_type, "", "", phone, email,
                f"Meta Ads lead — {biz_type}", "",
                score.get("score"), priority,
                score.get("recommended_agent"), "", ts(), "meta_ads", "new"
            ])

        # 5. Schedule nurture sequence (Days 2, 4, 7)
        if phone:
            schedule_nurture(phone, first_name, biz_type)

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        log.error(f"Meta webhook error: {e}")
        return jsonify({"status": "error"}), 200  # always 200 to Meta

# ROUTE 6 — Health Check
# ══════════════════════════════════════════════
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "env": cfg.ENV,
        "anthropic": bool(cfg.ANTHROPIC_API_KEY),
        "whatsapp": bool(cfg.AUTHKEY_IO),
        "email": bool(cfg.SENDGRID_KEY),
        "sheets": bool(cfg.LEADS_SHEET_ID),
        "ts": ts()
    }), 200


@app.route("/", methods=["GET"])
def root():
    return jsonify({"service": "Shyra AI API", "status": "running"}), 200


# ── CORS helpers
def _cors_preflight():
    resp = jsonify({})
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    return resp, 200


def _verify_webhook(req, token: str):
    if req.args.get("hub.verify_token") == token:
        return req.args.get("hub.challenge", ""), 200
    return "Forbidden", 403


# ══════════════════════════════════════════════
# ADMIN — API Key Management
# ══════════════════════════════════════════════
from api.admin_routes import (
    ADMIN_TOKEN, MANAGED_KEYS, admin_required,
    mask_value, save_to_env_file, save_to_railway,
    test_key, login_html
)

@app.route("/admin", methods=["GET"])
def admin_panel():
    token = request.cookies.get("admin_token","")
    if token != ADMIN_TOKEN:
        return make_response(login_html(), 200)
    with open(os.path.join(os.path.dirname(__file__), "admin_panel.html")) as f:
        return f.read(), 200

@app.route("/admin/auth", methods=["POST"])
def admin_auth():
    data = request.json or {}
    import hashlib
    pwd = data.get("password","")
    computed = hashlib.sha256(pwd.encode()).hexdigest()[:32]
    if computed == ADMIN_TOKEN:
        resp = jsonify({"token": ADMIN_TOKEN})
        resp.set_cookie("admin_token", ADMIN_TOKEN, max_age=86400, httponly=True, samesite="Strict")
        return resp
    return jsonify({"error": "wrong password"}), 401

@app.route("/admin/keys", methods=["GET"])
@admin_required
def admin_get_keys():
    values = {}
    for _, key, *_ in MANAGED_KEYS:
        val = os.getenv(key, "")
        values[key] = mask_value(key, val) if val else ""
    return jsonify({"values": values}), 200

@app.route("/admin/keys", methods=["POST"])
@admin_required
def admin_save_keys():
    data = request.json or {}
    updates = data.get("keys", {})
    if not updates:
        return jsonify({"success": False, "reason": "No keys provided"}), 400
    # Try Railway first, fallback to .env
    result = save_to_railway(updates)
    save_to_env_file(updates)  # always save locally too
    result["saved_to"] = result.get("saved_to", ".env (Railway token not set)")
    return jsonify(result), 200

@app.route("/admin/test", methods=["POST"])
@admin_required
def admin_test_key():
    data = request.json or {}
    key = data.get("key","")
    value = data.get("value","")
    if not key or not value:
        return jsonify({"ok": False, "msg": "Missing key or value"}), 400
    result = test_key(key, value)
    return jsonify(result), 200

@app.route("/admin/health", methods=["GET"])
@admin_required
def admin_health():
    services = {}
    checks = [
        ("ANTHROPIC",     "ANTHROPIC_API_KEY"),
        ("WHATSAPP",      "AUTHKEY_IO"),
        ("SENDGRID",      "SENDGRID_KEY"),
        ("GOOGLE MAPS",   "MAPS_API_KEY"),
        ("RAZORPAY",      "RAZORPAY_KEY"),
    ]
    for service, key in checks:
        val = os.getenv(key,"")
        if val:
            services[service] = test_key(key, val)
        else:
            services[service] = {"ok": False, "msg": "Key not set"}
    # Sheets check
    try:
        from core.utils import get_sheet
        get_sheet(os.getenv("LEADS_SHEET_ID",""))
        services["GOOGLE SHEETS"] = {"ok": True, "msg": "Connected"}
    except Exception as e:
        services["GOOGLE SHEETS"] = {"ok": False, "msg": str(e)[:40]}
    return jsonify({"services": services}), 200


# ── Run
if __name__ == "__main__":
    log.info("Starting Shyra API server...")
    app.run(host="0.0.0.0", port=cfg.PORT, debug=cfg.DEBUG)
