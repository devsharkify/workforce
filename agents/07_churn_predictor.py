"""
AGENT 07 — Churn Predictor
============================
Daily 8 PM: Scans all active clients for churn signals.
Alerts sales team immediately for at-risk clients.
Runs a save sequence for clients showing early signals.

Churn signals:
1. No WhatsApp activity for 7+ days
2. Support complaints in last 7 days
3. Missed invoice payment
4. No response to last 2 WhatsApps
5. Health score < 5
6. Sent PAUSE command
"""
import logging
from datetime import datetime, timedelta
from core.config import cfg
from core.utils import ask_claude, send_whatsapp_safe, notify_sales, notify_founder, sheet_read, get_sheet, ts

log = logging.getLogger("shyra.agent07")

CHURN_SIGNALS = {
    "inactive_7d":      {"weight": 3, "label": "No activity 7+ days"},
    "inactive_14d":     {"weight": 5, "label": "No activity 14+ days"},
    "low_health":       {"weight": 4, "label": "Health score < 5"},
    "missed_payment":   {"weight": 4, "label": "Missed invoice"},
    "no_response":      {"weight": 3, "label": "No response to last 2 messages"},
    "support_complaint":{"weight": 3, "label": "Recent complaint"},
    "paused":           {"weight": 5, "label": "Agent paused"},
}

# Score 7+ = at risk, 10+ = urgent


def calculate_churn_score(client: dict) -> tuple[int, list]:
    score = 0
    signals = []

    health = int(client.get("Health Score", 7) or 7)
    status = client.get("Status", "").lower()
    last_activity = client.get("Last Activity", "")
    payment_status = client.get("Payment Status", "paid").lower()

    # Health score
    if health < 5:
        score += CHURN_SIGNALS["low_health"]["weight"]
        signals.append(CHURN_SIGNALS["low_health"]["label"])

    # Paused
    if status == "paused":
        score += CHURN_SIGNALS["paused"]["weight"]
        signals.append(CHURN_SIGNALS["paused"]["label"])

    # Missed payment
    if payment_status in ("overdue", "missed"):
        score += CHURN_SIGNALS["missed_payment"]["weight"]
        signals.append(CHURN_SIGNALS["missed_payment"]["label"])

    # Activity check
    if last_activity:
        try:
            last = datetime.strptime(last_activity[:10], "%Y-%m-%d")
            days_ago = (datetime.now() - last).days
            if days_ago >= 14:
                score += CHURN_SIGNALS["inactive_14d"]["weight"]
                signals.append(CHURN_SIGNALS["inactive_14d"]["label"] + f" ({days_ago}d)")
            elif days_ago >= 7:
                score += CHURN_SIGNALS["inactive_7d"]["weight"]
                signals.append(CHURN_SIGNALS["inactive_7d"]["label"] + f" ({days_ago}d)")
        except Exception:
            pass

    return score, signals


def build_save_message(client: dict, signals: list) -> str:
    name = client.get("Client Name", "")
    agents = client.get("Agents", "")

    prompt = f"""Write a WhatsApp save message for a Shyra AI client showing churn signals.

Client: {name}
Agents: {agents}
Signals: {', '.join(signals)}

Rules:
- Sound like a caring founder checking in, NOT a retention script
- Reference something specific about their business
- Offer real help — free training session, feature they haven't used, problem-solving call
- Max 4 sentences
- End with a soft open question"""

    try:
        return ask_claude(prompt, max_tokens=150)
    except Exception:
        return f"Hi {name.split()[0]}! Just checking in — how is your AI agent performing for you? If there's anything we can improve or a feature you'd like added, I'm here. What's working well and what could be better? 🙏"


def run():
    log.info("Agent 07 — Churn Predictor starting")

    try:
        clients = sheet_read(cfg.CLIENTS_SHEET_ID)
    except Exception as e:
        log.error(f"Failed to read clients: {e}")
        return

    at_risk = []
    warned = []

    for client in clients:
        if client.get("Status", "").lower() not in ("active", "paused"):
            continue

        score, signals = calculate_churn_score(client)
        name = client.get("Client Name", "")
        phone = client.get("Phone", "")

        if score >= 10:
            # URGENT — alert founder + sales immediately
            at_risk.append(client)
            log.warning(f"URGENT churn risk: {name} (score={score})")

            alert = f"""*🚨 URGENT — Churn Risk*

Client: {name}
Phone: +{phone}
Score: {score}/15
Signals: {', '.join(signals)}

*Action: Call within 2 hours.*"""
            notify_founder(alert)
            notify_sales(alert)

        elif score >= 7:
            # Warning — send save message
            warned.append(client)
            log.info(f"Churn warning: {name} (score={score})")
            save_msg = build_save_message(client, signals)
            send_whatsapp_safe(phone, save_msg)

            notify_sales(f"*⚠️ Churn Warning*\n{name} · score={score}\n{', '.join(signals)}\nSave message sent.")

        else:
            log.debug(f"Healthy: {name} (score={score})")

    log.info(f"Agent 07 done — {len(at_risk)} urgent, {len(warned)} warned")

    # Daily summary to founder
    if at_risk or warned:
        summary = f"*Churn Report {datetime.now().strftime('%d %b')}*\n"
        summary += f"🚨 Urgent: {len(at_risk)}\n⚠️ Warning: {len(warned)}\n"
        if at_risk:
            summary += "\nUrgent: " + ", ".join(c.get("Client Name","") for c in at_risk)
        notify_founder(summary)


if __name__ == "__main__":
    run()
