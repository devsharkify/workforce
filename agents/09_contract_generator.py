"""
AGENT 09 — Contract Generator
================================
On-demand: generates service agreement PDF.
Sends to client for digital confirmation (reply CONFIRM).
"""
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from core.config import cfg
from core.utils import generate_pdf, send_email, send_whatsapp_safe, notify_founder, ts

log = logging.getLogger("shyra.agent09")


def generate_contract(
    client_name: str,
    client_phone: str,
    client_email: str,
    client_address: str,
    agents: str,
    start_date: str = None,
    notes: str = ""
) -> str:
    if not start_date:
        start_date = datetime.now().strftime("%d %B %Y")

    end_date = (datetime.now() + timedelta(days=365)).strftime("%d %B %Y")
    agent_count = len(agents.split(","))
    monthly = 2000 * agent_count
    contract_id = f"SHY-{datetime.now().strftime('%Y%m%d')}-{client_name[:3].upper()}"

    sections = [
        {"heading": "Service Agreement",
         "body": f"Contract ID: {contract_id}\nDate: {start_date}\nValid until: {end_date}"},

        {"heading": "Parties",
         "body": [
             ["Party", "Details"],
             ["Service Provider", "Sharkify Technology Pvt Ltd\nShyra AI\nHyderabad, Telangana\nCIN: [YOUR_CIN]\nGST: [YOUR_GST]\nContact: rohan@sharkify.ai"],
             ["Client", f"{client_name}\n{client_address}\nPhone: {client_phone}\nEmail: {client_email}"],
         ]},

        {"heading": "Scope of Services",
         "body": f"Shyra AI agrees to build, deploy and maintain the following AI agents:\n\n{agents}\n\nServices include:\n• Custom AI agent development\n• WhatsApp Business API integration\n• Initial training on client's products/services/FAQs\n• Go-live support within 7 business days\n• Monthly performance reporting\n• Ongoing maintenance and updates\n• Support via WhatsApp during business hours (9 AM–9 PM IST)"},

        {"heading": "Investment",
         "body": [
             ["Item", "Amount", "Frequency"],
             ["One-time setup fee", "₹20,000", "At contract signing"],
             ["Monthly retainer", f"₹{monthly:,}", "25th of each month"],
             ["WhatsApp API credits", "At cost + 40%", "Monthly, usage-based"],
             ["Additional agents", "₹20,000 setup + ₹2,000/month", "Per agent"],
         ]},

        {"heading": "Payment Terms",
         "body": "• Setup fee payable within 3 days of agreement signing\n• Monthly retainer due on the 25th of each month\n• 7-day grace period before service suspension\n• All payments via bank transfer or Razorpay\n• GST applicable as per government regulations"},

        {"heading": "Deliverables & Timeline",
         "body": [
             ["Day", "Milestone"],
             ["Day 1–2", "Kickoff call + client sends product data/FAQs"],
             ["Day 3–4", "Agent build and training"],
             ["Day 5–6", "Client testing and feedback"],
             ["Day 7", "Go-live on client's WhatsApp Business number"],
         ]},

        {"heading": "Intellectual Property",
         "body": "The AI agent's infrastructure, prompts and technology remain the property of Sharkify Technology Pvt Ltd. The client's data (products, FAQs, conversation logs) remains the property of the client. Shyra AI will not use client data to train models for other clients."},

        {"heading": "Confidentiality",
         "body": "Both parties agree to maintain confidentiality of all proprietary information shared during the engagement. This obligation survives termination of the agreement."},

        {"heading": "Termination",
         "body": "Either party may terminate this agreement with 30 days' written notice. Shyra AI reserves the right to terminate immediately in case of non-payment exceeding 30 days or breach of terms. No refunds on setup fees after agent go-live."},

        {"heading": "Limitation of Liability",
         "body": "Shyra AI's liability is limited to the monthly retainer amount. We are not liable for indirect losses, missed business opportunities or third-party platform downtimes (WhatsApp, cloud services)."},

        {"heading": "Governing Law",
         "body": "This agreement is governed by the laws of India. All disputes shall be subject to the jurisdiction of courts in Hyderabad, Telangana."},

        {"heading": "Acceptance",
         "body": f"By replying CONFIRM to our WhatsApp or signing below, {client_name} agrees to all terms above.\n\nSigned for Sharkify Technology Pvt Ltd:\nRohan _______________\nDirector, Shyra AI\nDate: {start_date}\n\nSigned for {client_name}:\n_______________________________\nDate: _______________"},
    ]

    client_safe = client_name.replace(" ", "_")
    path = f"data/contracts/contract_{client_safe}_{contract_id}.pdf"
    Path("data/contracts").mkdir(parents=True, exist_ok=True)
    generate_pdf(path, f"Service Agreement — {client_name}", sections)
    log.info(f"Contract generated: {path}")
    return path, contract_id


def run(client_name, phone, email, address, agents):
    path, contract_id = generate_contract(client_name, phone, email, address, agents)

    # Send via WhatsApp
    wa = f"""*Service Agreement Ready — {client_name}* 📄

Contract ID: {contract_id}

Your Shyra AI service agreement has been sent to {email or 'your email'}.

*To confirm:*
Reply *CONFIRM* to this message to digitally accept the agreement.

Or call Rohan to discuss any clauses: {cfg.FOUNDER_NUMBER}

*Once confirmed:*
• Setup invoice raised immediately
• Onboarding starts Day 1
• Agent live in 7 days 🚀"""

    send_whatsapp_safe(phone, wa)

    # Email with PDF
    if email:
        send_email(email, client_name,
            f"Service Agreement — Shyra AI ({contract_id})",
            f"""<div style="font-family:Arial;max-width:600px">
<h2>Service Agreement Enclosed</h2>
<p>Hi {client_name.split()[0]},</p>
<p>Your Shyra AI service agreement (Contract ID: <strong>{contract_id}</strong>) is attached.</p>
<p><strong>To confirm:</strong> Reply CONFIRM on WhatsApp or email, or sign and scan the attached PDF.</p>
<p>Any questions? Reply to this email or WhatsApp us directly.</p>
<p>— Rohan, Shyra AI</p>
</div>""", attachment=path)

    notify_founder(f"📄 Contract sent\n{client_name} · {contract_id}")
    return path, contract_id


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--client", required=True)
    p.add_argument("--phone", required=True)
    p.add_argument("--email", default="")
    p.add_argument("--address", default="Hyderabad")
    p.add_argument("--agents", default="WhatsApp Support Agent")
    args = p.parse_args()
    run(args.client, args.phone, args.email, args.address, args.agents)
