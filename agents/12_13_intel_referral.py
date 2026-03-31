"""
AGENT 12 — Competitor Intel
AGENT 13 — Referral Agent
============================
Agent 12: Monday 8 AM — researches AI competitors in India, sends brief to founder.
Agent 13: Daily — identifies clients eligible for referral program, sends referral ask.
"""
import logging
from datetime import datetime, timedelta
from core.utils import ask_claude, ask_claude_json, send_whatsapp_safe, notify_founder, sheet_read, sheet_append, ts, today

log = logging.getLogger("shyra.agent12_13")

# ══════════════════════════════════════
# AGENT 12 — Competitor Intel
# ══════════════════════════════════════

COMPETITORS = [
    "Wati", "Interakt", "Respond.io", "Yellow.ai", "Botpress",
    "Landbot", "Tidio", "Haptik", "AiSensy", "Gallabox"
]

def run_competitor_intel():
    log.info("Agent 12 — Competitor Intel starting")

    prompt = f"""Analyse the competitive landscape for Shyra AI, an AI agent agency for Indian and UAE SMEs.

Shyra's positioning:
- Custom AI agents (not DIY platforms)
- WhatsApp-first for Indian market
- ₹20,000 setup + ₹2,000/month — affordable for SMEs
- Live in 7 days
- Built for Hyderabad/India market

Key competitors to analyse: {', '.join(COMPETITORS)}

Return JSON:
{{
  "market_gaps": ["3 gaps Shyra can own"],
  "competitor_weaknesses": {{"CompetitorName": "key weakness", ...}},
  "pricing_insight": "where Shyra sits vs market",
  "emerging_threats": ["2 new threats to watch"],
  "recommended_actions": ["3 specific actions for Shyra this week"],
  "headline": "one sentence market summary"
}}"""

    try:
        intel = ask_claude_json(prompt)
    except Exception as e:
        log.error(f"Intel generation failed: {e}")
        return

    # Format for WhatsApp
    gaps = "\n".join(f"• {g}" for g in intel.get("market_gaps",[]))
    actions = "\n".join(f"• {a}" for a in intel.get("recommended_actions",[]))
    threats = "\n".join(f"• {t}" for t in intel.get("emerging_threats",[]))

    report = f"""*📊 Weekly Competitor Intel*

*Market:* {intel.get('headline','')}

*Gaps Shyra can own:*
{gaps}

*Emerging threats:*
{threats}

*Actions this week:*
{actions}

*Pricing:* {intel.get('pricing_insight','')}"""

    notify_founder(report)
    log.info("Competitor intel sent to founder")


# ══════════════════════════════════════
# AGENT 13 — Referral Agent
# ══════════════════════════════════════

REFERRAL_REWARD = "₹3,000 Amazon voucher"  # Per successful referral

def run_referral_agent():
    log.info("Agent 13 — Referral Agent starting")

    try:
        clients = sheet_read(None)  # Would use CLIENTS_SHEET_ID
    except Exception:
        # Demo mode
        log.info("No clients sheet — running in demo mode")
        return

    for client in clients:
        if client.get("Status","").lower() != "active":
            continue
        if client.get("Referral Asked",""):
            continue

        # Only ask clients active 45+ days with good health
        try:
            start = datetime.strptime(client.get("Start Date", today())[:10], "%Y-%m-%d")
            days_active = (datetime.now() - start).days
        except Exception:
            continue

        health = int(client.get("Health Score", 0) or 0)
        if days_active < 45 or health < 7:
            continue

        name = client.get("Client Name","")
        phone = client.get("Phone","")
        agents = client.get("Agents","")

        # Generate personalised referral ask
        prompt = f"""Write a referral ask WhatsApp message for:
Client: {name} (active {days_active} days, health {health}/10)
Using: {agents}

Rules:
- Reference their specific success (assume agent is working well)
- Mention referral reward: {REFERRAL_REWARD}
- Suggest specific people they might know (same industry/area)
- Max 5 sentences. Sound genuine, not salesy."""

        try:
            msg = ask_claude(prompt, max_tokens=150)
            msg += f"\n\n🎁 *Referral reward:* {REFERRAL_REWARD} for every client you introduce who goes live.\n\nJust share their number here and we handle everything else 🙏"
        except Exception:
            msg = f"""Hi {name.split()[0]}! 

Your AI agent has been running brilliantly for {days_active} days 🙏

Do you know any other business owners who struggle with customer WhatsApp management? We'd love to help them too.

🎁 We'll send you {REFERRAL_REWARD} for every referral who goes live.

Just drop their number here and we'll take it from there."""

        send_whatsapp_safe(phone, msg)
        log.info(f"Referral ask sent: {name}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--agent", choices=["intel","referral"], required=True)
    args = p.parse_args()
    if args.agent == "intel":    run_competitor_intel()
    elif args.agent == "referral": run_referral_agent()
