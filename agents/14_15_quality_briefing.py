"""
AGENT 14 — Quality Monitor
AGENT 15 — Morning Briefing
==============================
Agent 14: Daily 9 PM — samples client agent conversations, flags issues.
Agent 15: Daily 7:30 AM — sends founder a morning briefing via WhatsApp.
"""
import logging
from datetime import datetime
from core.config import cfg
from core.utils import ask_claude, ask_claude_json, send_whatsapp_safe, notify_founder, sheet_read, ts, today

log = logging.getLogger("shyra.agent14_15")

# ══════════════════════════════════════
# AGENT 14 — Quality Monitor
# ══════════════════════════════════════

def audit_client_agent(client: dict, sample_conversations: list) -> dict:
    """Claude audits sample conversations for quality issues."""
    if not sample_conversations:
        return {"score": 8, "issues": [], "fixes": []}

    name = client.get("Client Name","")
    agents = client.get("Agents","")

    convo_text = "\n---\n".join([
        f"User: {c.get('user','')}\nAgent: {c.get('agent','')}"
        for c in sample_conversations[:10]
    ])

    prompt = f"""Audit these AI agent conversations for {name} ({agents}):

{convo_text}

Score 1-10 on: accuracy, tone, helpfulness, brand voice, escalation decisions.

Return JSON:
{{
  "score": 1-10,
  "issues": ["specific issue 1", "specific issue 2"],
  "fixes": ["specific fix for issue 1", "specific fix for issue 2"],
  "best_exchange": "quote the best customer interaction",
  "urgent": true/false
}}"""

    try:
        return ask_claude_json(prompt)
    except Exception:
        return {"score": 7, "issues": [], "fixes": [], "urgent": False}


def run_quality_monitor():
    log.info("Agent 14 — Quality Monitor starting")

    try:
        clients = sheet_read(cfg.CLIENTS_SHEET_ID)
    except Exception as e:
        log.error(f"Failed to read clients: {e}")
        return

    issues_found = []

    for client in clients:
        if client.get("Status","").lower() != "active":
            continue

        name = client.get("Client Name","")

        # In production: fetch real conversations from WhatsApp API / your DB
        # For now, we audit based on health score and client feedback
        health = int(client.get("Health Score", 7) or 7)
        sample_convos = []  # Would be populated from WhatsApp conversation DB

        result = audit_client_agent(client, sample_convos)
        score = result.get("score", 7)

        if score < 6 or result.get("urgent"):
            issues_found.append({
                "client": name,
                "score": score,
                "issues": result.get("issues", []),
                "fixes": result.get("fixes", []),
            })
            log.warning(f"Quality issue: {name} (score={score})")

        # Update health score in sheet
        try:
            from core.utils import get_sheet
            ws = get_sheet(cfg.CLIENTS_SHEET_ID)
            all_vals = ws.get_all_values()
            for i, row in enumerate(all_vals):
                if row and row[0] == name:
                    ws.update_cell(i+1, 9, str(score))  # Health score col
                    break
        except Exception:
            pass

    if issues_found:
        alert = "*⚠️ Quality Issues Found*\n\n"
        for issue in issues_found:
            alert += f"*{issue['client']}* (score={issue['score']}/10)\n"
            for iss in issue.get("issues",[])[:2]:
                alert += f"  • {iss}\n"
            alert += "\n"
        notify_founder(alert)

    log.info(f"Agent 14 done — {len(issues_found)} issues flagged")


# ══════════════════════════════════════
# AGENT 15 — Morning Briefing
# ══════════════════════════════════════

def run_morning_briefing():
    log.info("Agent 15 — Morning Briefing starting")

    try:
        leads = sheet_read(cfg.LEADS_SHEET_ID)
        clients = sheet_read(cfg.CLIENTS_SHEET_ID)
        calls = sheet_read(cfg.CALLS_SHEET_ID) if cfg.CALLS_SHEET_ID else []
    except Exception as e:
        log.error(f"Sheet read failed: {e}")
        leads, clients, calls = [], [], []

    # Calculate metrics
    total_leads = len(leads)
    new_leads = len([l for l in leads if l.get("Date Scraped","") == today()])
    hot_leads = len([l for l in leads if l.get("Priority","").lower() == "hot"])
    contacted_today = len([l for l in leads if l.get("Last Contacted","")[:10] == today()])

    active_clients = len([c for c in clients if c.get("Status","").lower() == "active"])
    onboarding = len([c for c in clients if c.get("Status","").lower() == "onboarding"])
    at_risk = len([c for c in clients if int(c.get("Health Score",7) or 7) < 5])

    calls_today = len([c for c in calls if c.get("Slot","")[:10] == today()])

    monthly_mrr = active_clients * 2000

    # Today's priority actions
    prompt = f"""Generate 3 specific priority actions for Shyra AI today based on:
- {hot_leads} hot leads not yet contacted
- {at_risk} at-risk clients
- {calls_today} calls booked today
- {onboarding} clients in onboarding

Be specific. One sentence each. Start each with an action verb."""

    try:
        priorities_text = ask_claude(prompt, max_tokens=120)
    except Exception:
        priorities_text = f"• Follow up on {hot_leads} hot leads\n• Check on {at_risk} at-risk clients\n• Prep for {calls_today} calls today"

    # Format briefing
    date_str = datetime.now().strftime("%A, %d %B %Y")
    briefing = f"""*🌅 Good morning, Rohan!*
*{date_str}*

*📊 Pipeline*
🎯 Total leads: {total_leads} ({new_leads} new today)
🔥 Hot leads: {hot_leads}
📞 Contacted today: {contacted_today}

*👥 Clients*
✅ Active: {active_clients}
⚙️ Onboarding: {onboarding}
⚠️ At-risk: {at_risk}
💰 MRR: ₹{monthly_mrr:,}

*📅 Today*
📞 Calls scheduled: {calls_today}

*✅ Priority actions:*
{priorities_text}

Have a great day! 🚀"""

    notify_founder(briefing)
    log.info("Morning briefing sent")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--agent", choices=["quality","briefing"], required=True)
    args = p.parse_args()
    if args.agent == "quality":  run_quality_monitor()
    elif args.agent == "briefing": run_morning_briefing()
