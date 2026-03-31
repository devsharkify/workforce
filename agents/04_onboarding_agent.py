"""
AGENT 04 — Onboarding Agent
==============================
On-demand: kicks off 7-day onboarding sequence for new clients.
Day 1: Welcome + kickoff form via WhatsApp
Day 2: Build team briefed
Day 5: Test session reminder
Day 7: Go-live confirmation
"""
import logging
from datetime import datetime, timedelta
from core.config import cfg
from core.utils import send_whatsapp_safe, send_email, notify_build, notify_founder, sheet_append, ts

log = logging.getLogger("shyra.agent04")

ONBOARDING_STEPS = [
    {"day": 0, "label": "kickoff"},
    {"day": 1, "label": "day1_followup"},
    {"day": 3, "label": "halfway"},
    {"day": 5, "label": "test_session"},
    {"day": 7, "label": "go_live"},
]


def kickoff(client_name: str, phone: str, email: str, agents: str, biz_type: str):
    """Day 0 — immediate kickoff on contract sign."""
    log.info(f"Onboarding kickoff: {client_name}")

    # Welcome WhatsApp
    wa = f"""*Welcome to Shyra AI, {client_name.split()[0]}! 🎉*

Your AI agent journey starts NOW.

*Your 7-day roadmap:*
📋 Day 1–2: We gather your data (products, FAQs, prices)
🔧 Day 3–4: Build & train your agent
🧪 Day 5–6: You test it — give feedback
🚀 Day 7: Go live!

*To start — please send us:*
1. Your product list / service menu (PDF or photo)
2. Top 20 questions customers ask you
3. Your WhatsApp Business number to connect

You can send all of this here in WhatsApp. No forms. 🙏

Any questions? I'm available 24/7 on this number."""

    send_whatsapp_safe(phone, wa)

    # Email welcome
    if email:
        html = f"""<div style="font-family:Arial;max-width:600px">
<h2>Welcome aboard, {client_name}! 🎉</h2>
<p>Your AI agent — <strong>{agents}</strong> — goes live in 7 days.</p>
<h3>What happens next:</h3>
<ul>
<li><strong>Day 1–2:</strong> Share your product list + FAQs via WhatsApp</li>
<li><strong>Day 3–4:</strong> We build and train your agent</li>
<li><strong>Day 5–6:</strong> Test session — you try it as a customer</li>
<li><strong>Day 7:</strong> Go live on your WhatsApp Business number</li>
</ul>
<p>Questions? Reply to this email or WhatsApp our team directly.</p>
<p>— The Shyra AI Team</p>
</div>"""
        send_email(email, client_name, f"Welcome to Shyra AI — your agent goes live in 7 days", html)

    # Alert build team
    notify_build(f"""*New Client Onboarding* 🚀
Client: {client_name}
Type: {biz_type}
Agent: {agents}
Phone: {phone}
Email: {email}

*Action needed: Request product data via WhatsApp within 2 hours.*""")

    # Log to clients sheet
    if cfg.CLIENTS_SHEET_ID:
        go_live = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        sheet_append(cfg.CLIENTS_SHEET_ID, [
            client_name, biz_type, phone, email, agents,
            ts(),           # Start date
            go_live,        # Expected go-live
            "onboarding",   # Status
            "0",            # Health score
            "",             # Last ROI date
        ])

    notify_founder(f"*Onboarding started* ✅\n{client_name} · {agents}")


def day1_followup(client_name: str, phone: str):
    msg = f"""Hi {client_name.split()[0]}! 👋

Just checking — did you get a chance to send over:
• Product list / menu
• Common customer questions

No pressure — even a WhatsApp photo of a price list works perfectly.
The sooner we get this, the earlier your agent goes live! 🚀"""
    send_whatsapp_safe(phone, msg)


def halfway(client_name: str, phone: str, agents: str):
    msg = f"""*Day 3 Update — {client_name}* ⚙️

Our build team is working on your {agents}.
Training is underway. ✅

*Tomorrow — test session prep:*
We'll send you a test WhatsApp number to try your agent as a customer.
Just reply as you normally would to customer queries.

Anything specific you want your agent to handle well?
Reply here and we'll make sure it's covered. 🙏"""
    send_whatsapp_safe(phone, msg)


def test_session(client_name: str, phone: str):
    msg = f"""*Test Session Ready — {client_name}* 🧪

Your AI agent is built and ready for testing!

*How to test:*
1. Message this test number: [TEST_NUMBER]
2. Ask it anything a customer would ask
3. Check if answers are accurate
4. Reply here with any corrections

You have 24 hours to test. After that we go live. 🚀

Pro tip: try edge cases — wrong spellings, Hindi questions, price haggling."""
    send_whatsapp_safe(phone, msg)


def go_live(client_name: str, phone: str, agents: str):
    msg = f"""🎉 *Your AI Agent Is LIVE, {client_name.split()[0]}!*

*{agents}* is now active on your WhatsApp Business number.

*What happens now:*
✅ Agent handles all customer queries 24/7
✅ Escalates to you when it can't answer
✅ You get a weekly performance report every Monday
✅ First invoice: ₹2,000 on 25th of this month

*Your first week checklist:*
• Let your team know the agent is live
• Don't answer queries the agent handles (let it learn)
• Send any corrections here directly

Welcome to the future of your business! 🚀
— The Shyra AI Team"""
    send_whatsapp_safe(phone, msg)
    notify_founder(f"*CLIENT LIVE* 🚀\n{client_name}\n{agents}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--step", choices=["kickoff","day1","halfway","test","golive"], default="kickoff")
    p.add_argument("--client", required=True)
    p.add_argument("--phone", required=True)
    p.add_argument("--email", default="")
    p.add_argument("--agents", default="WhatsApp Support Agent")
    p.add_argument("--type", default="SME")
    args = p.parse_args()

    if args.step == "kickoff":    kickoff(args.client, args.phone, args.email, args.agents, args.type)
    elif args.step == "day1":     day1_followup(args.client, args.phone)
    elif args.step == "halfway":  halfway(args.client, args.phone, args.agents)
    elif args.step == "test":     test_session(args.client, args.phone)
    elif args.step == "golive":   go_live(args.client, args.phone, args.agents)
