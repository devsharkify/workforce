"""
AGENT 02 — Outreach Agent
===========================
Daily 9 AM: Picks top 20 uncontacted leads from Sheets.
Sends personalised WhatsApp + email. Updates status.
"""
import logging
import time
from core.config import cfg
from core.utils import ask_claude, send_whatsapp_safe, send_email, sheet_read, get_sheet, ts, today

log = logging.getLogger("shyra.agent02")

DAILY_LIMIT = 20


def build_whatsapp_message(lead: dict) -> str:
    """Claude writes a hyper-personalised opening message."""
    name = lead.get("Business Name", "")
    biz_type = lead.get("Type", "")
    city = lead.get("City", "")
    pain = lead.get("Pain", "")
    agent = lead.get("Suggested Agent", "WhatsApp AI Agent")
    opening = lead.get("Opening Line", "")

    # If we already have a Claude-generated opening, use it
    if opening and len(opening) > 20:
        return f"""{opening}

*What Shyra AI does:*
✅ {agent} — answers customer queries 24/7
✅ Setup in 7 days · ₹20,000 one-time · ₹2,000/month
✅ Most clients recover the cost in 30-45 days

*Free 30-minute consultation — no commitment.*
Reply YES for a quick call 👇"""

    # Otherwise generate fresh
    prompt = f"""Write a 3-sentence WhatsApp opening message for:
Business: {name} ({biz_type}) in {city}
Pain: {pain}
Suggest: {agent}

Rules:
- Mention their business name naturally
- One specific pain point
- End with "Reply YES for a free 30-min call"
- No spam language. Sound human."""

    try:
        msg = ask_claude(prompt, max_tokens=150)
        return msg + "\n\n✅ Setup in 7 days · ₹20,000 one-time · ₹2,000/month\n\nReply YES for a free 30-min call 👇"
    except Exception:
        return f"Hi! I noticed {name} — would an AI agent that handles customer WhatsApp queries 24/7 be useful? Setup in 7 days, costs ₹2,000/month. Reply YES for a free call 👇"


def build_email(lead: dict) -> tuple[str, str]:
    """Returns (subject, html)."""
    name = lead.get("Business Name", "")
    biz_type = lead.get("Type", "")
    agent = lead.get("Suggested Agent", "AI Agent")
    pain = lead.get("Pain", "")

    subject = f"AI agent for {name} — live in 7 days"
    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;color:#333;">
<h2 style="color:#0f0f0e">Hi {name.split()[0]},</h2>
<p>I'm Rohan from <strong>Shyra AI</strong> — we build AI agents for {biz_type} businesses in India and UAE.</p>
<p>Based on {name}, I think a <strong>{agent}</strong> could save your team 3+ hours daily on:</p>
<blockquote style="border-left:3px solid #a855f7;padding-left:12px;color:#555">{pain}</blockquote>
<p><strong>How it works:</strong></p>
<ul>
<li>Connects to your WhatsApp Business number</li>
<li>Trained on your products, prices, FAQs</li>
<li>Live in 7 days. ₹20,000 setup · ₹2,000/month</li>
<li>Most clients recover cost in 30–45 days</li>
</ul>
<p><a href="https://shyra.pro" style="background:linear-gradient(135deg,#f97316,#a855f7);color:white;padding:12px 24px;border-radius:100px;text-decoration:none;font-weight:600">Book free 30-min call →</a></p>
<p style="font-size:12px;color:#999;margin-top:32px">Shyra AI · Sharkify Technology Pvt Ltd · Hyderabad<br>Unsubscribe by replying STOP</p>
</div>"""
    return subject, html


def run():
    log.info("Agent 02 — Outreach starting")

    # Load leads from Sheets — filter new/uncontacted, sort by score desc
    try:
        all_leads = sheet_read(cfg.LEADS_SHEET_ID)
    except Exception as e:
        log.error(f"Failed to read leads: {e}")
        return

    targets = [
        l for l in all_leads
        if l.get("Status", "").lower() in ("new", "")
        and l.get("Phone", "")
    ]
    targets.sort(key=lambda x: int(x.get("AI Score", 0) or 0), reverse=True)
    targets = targets[:DAILY_LIMIT]

    if not targets:
        log.info("No new leads to contact today")
        return

    log.info(f"Contacting {len(targets)} leads")
    sent = 0

    for lead in targets:
        phone = lead.get("Phone", "").replace(" ", "").replace("+", "").replace("-", "")
        name = lead.get("Business Name", "")

        try:
            # WhatsApp
            if phone and len(phone) >= 10:
                msg = build_whatsapp_message(lead)
                ok = send_whatsapp_safe(phone, msg)
                if ok:
                    log.info(f"WhatsApp sent: {name} ({phone[:6]}****)")

            # Email (if available)
            email = lead.get("Email", "")
            if email and "@" in email:
                subj, html = build_email(lead)
                send_email(email, name, subj, html)
                log.info(f"Email sent: {name} ({email})")

            # Update status in sheet
            try:
                ws = get_sheet(cfg.LEADS_SHEET_ID)
                all_vals = ws.get_all_values()
                for i, row in enumerate(all_vals):
                    if row and row[0] == name:
                        ws.update_cell(i+1, 15, "contacted")  # Status col
                        ws.update_cell(i+1, 16, ts())         # Last Contacted col
                        break
            except Exception as e:
                log.warning(f"Sheet update failed for {name}: {e}")

            sent += 1
            time.sleep(1.5)  # WhatsApp rate limit — 1 msg/sec max

        except Exception as e:
            log.error(f"Outreach failed for {name}: {e}")
            continue

    log.info(f"Agent 02 done — {sent}/{len(targets)} contacted")


if __name__ == "__main__":
    run()
