"""
AGENT 03 — Proposal Generator
================================
On-demand: generates a custom PDF proposal + emails + WhatsApps it.
Called by: sales team after a qualified call.

Usage:
  python agents/03_proposal_generator.py \
    --client "Kumar Pharma" \
    --type "pharmacy" \
    --phone "919876543210" \
    --email "kumar@gmail.com" \
    --pain "100+ WhatsApp orders daily, manual entry" \
    --agents "WhatsApp Order Assistant, Invoice OCR to Tally" \
    --notes "300 chemist clients, Secunderabad"
"""
import argparse
import logging
from pathlib import Path
from core.config import cfg
from core.utils import ask_claude, ask_claude_json, generate_pdf, send_email, send_whatsapp_safe, notify_founder, ts

log = logging.getLogger("shyra.agent03")


def generate_proposal(
    client_name: str,
    biz_type: str,
    phone: str,
    email: str,
    pain: str,
    agents: str,
    notes: str = ""
) -> str:
    """Generate full proposal and return PDF path."""

    log.info(f"Generating proposal for {client_name}")

    # Claude builds the detailed proposal content
    prompt = f"""Generate a professional AI agent proposal for:

Client: {client_name}
Business type: {biz_type}
Pain points: {pain}
Proposed agents: {agents}
Notes: {notes}
Pricing: ₹20,000 setup + ₹2,000/month per agent

Return JSON:
{{
  "executive_summary": "2 paragraphs",
  "problem_statement": "specific to their business (2 paragraphs)",
  "proposed_solution": {{
    "agents": [
      {{"name": "agent name", "what_it_does": "2 sentences", "time_saved": "X hours/day", "monthly_value": "₹X,000"}}
    ]
  }},
  "implementation_timeline": [
    {{"day": "Day 1–2", "activity": "..."}}
  ],
  "roi_calculation": {{
    "monthly_cost": "₹X,000",
    "monthly_saving": "₹X,000",
    "payback_days": "XX",
    "year_1_roi": "XXX%"
  }},
  "why_shyra": "3 bullet points"
}}"""

    try:
        content = ask_claude_json(prompt)
    except Exception as e:
        log.error(f"Content generation failed: {e}")
        content = {
            "executive_summary": f"Shyra AI proposes a custom AI agent solution for {client_name}.",
            "problem_statement": f"Manual operations are costing {client_name} significant time and revenue daily.",
            "proposed_solution": {"agents": [{"name": agents, "what_it_does": "Automates daily operations.", "time_saved": "3+ hours/day", "monthly_value": "₹15,000"}]},
            "implementation_timeline": [{"day": "Day 1–2", "activity": "Discovery and setup"}, {"day": "Day 3–5", "activity": "Training and testing"}, {"day": "Day 6–7", "activity": "Go live"}],
            "roi_calculation": {"monthly_cost": "₹2,000", "monthly_saving": "₹15,000", "payback_days": "4", "year_1_roi": "650%"},
            "why_shyra": "7-day delivery · No technical knowledge needed · Indian-built for Indian businesses"
        }

    # Build PDF sections
    roi = content.get("roi_calculation", {})
    agents_list = content.get("proposed_solution", {}).get("agents", [])
    timeline = content.get("implementation_timeline", [])

    agent_rows = [["Agent", "What It Does", "Time Saved", "Monthly Value"]]
    for a in agents_list:
        agent_rows.append([a.get("name",""), a.get("what_it_does",""), a.get("time_saved",""), a.get("monthly_value","")])

    timeline_rows = [["Timeline", "Activity"]]
    for t in timeline:
        timeline_rows.append([t.get("day",""), t.get("activity","")])

    sections = [
        {"heading": "Executive Summary",
         "body": content.get("executive_summary", "")},
        {"heading": "The Problem We're Solving",
         "body": content.get("problem_statement", "")},
        {"heading": "Proposed Solution",
         "body": agent_rows},
        {"heading": "Implementation — Live in 7 Days",
         "body": timeline_rows},
        {"heading": "ROI Calculation",
         "body": f"Monthly investment: {roi.get('monthly_cost')}\nMonthly time saving value: {roi.get('monthly_saving')}\nPayback period: {roi.get('payback_days')} days\nYear 1 ROI: {roi.get('year_1_roi')}"},
        {"heading": "Investment",
         "body": [
             ["Item", "Amount"],
             ["One-time setup fee", "₹20,000"],
             ["Monthly retainer (per agent)", "₹2,000"],
             ["WhatsApp API credits (at cost + 40%)", "Usage-based"],
             ["Support & updates", "Included"],
         ]},
        {"heading": "Why Shyra",
         "body": str(content.get("why_shyra", ""))},
    ]

    client_safe = client_name.replace(" ", "_").replace("/", "-")
    path = f"data/proposals/{client_safe}_{ts().replace(':','-')}.pdf"
    Path("data/proposals").mkdir(parents=True, exist_ok=True)
    generate_pdf(path, f"AI Agent Proposal — {client_name}", sections)
    log.info(f"Proposal PDF: {path}")
    return path


def run(client_name, biz_type, phone, email, pain, agents, notes=""):
    path = generate_proposal(client_name, biz_type, phone, email, pain, agents, notes)

    # Email with PDF
    if email:
        subj = f"Your Shyra AI Proposal — {client_name}"
        html = f"""<div style="font-family:Arial;max-width:600px">
<h2>Hi {client_name.split()[0]},</h2>
<p>Thank you for the call. Your custom Shyra AI proposal is attached.</p>
<p><strong>Summary:</strong> {agents} — live in 7 days, ₹20,000 setup + ₹2,000/month.</p>
<p>Any questions? Reply directly to this email or WhatsApp me: {cfg.FOUNDER_NUMBER}</p>
<p>Looking forward to building this for you 🙏</p>
<p>— Rohan<br>Shyra AI · Sharkify Technology Pvt Ltd</p>
</div>"""
        send_email(email, client_name, subj, html, attachment=path)
        log.info(f"Proposal emailed to {email}")

    # WhatsApp with link (can't send PDF directly — send summary)
    if phone:
        wa_msg = f"""*Your Shyra AI Proposal is Ready* 📄

Hi {client_name.split()[0]}!

Your custom AI agent proposal has been sent to {email or 'your email'}.

*Quick summary:*
🤖 Agents: {agents}
⚡ Live in: 7 days
💸 ₹20,000 setup · ₹2,000/month

*Next step:* Confirm and we start Day 1.

Any questions? Reply here or call Rohan directly. 🙏"""
        send_whatsapp_safe(phone, wa_msg)

    # Notify founder
    notify_founder(f"📄 Proposal sent\n{client_name} · {phone}\n{agents}")

    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    parser.add_argument("--type", default="SME")
    parser.add_argument("--phone", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--pain", default="Manual customer operations")
    parser.add_argument("--agents", default="WhatsApp Support Agent")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    run(args.client, args.type, args.phone, args.email, args.pain, args.agents, args.notes)
