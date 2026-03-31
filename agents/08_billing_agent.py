"""
AGENT 08 — Billing Agent
==========================
25th of every month:
  - Raises Razorpay invoices for all active clients
  - Sends WhatsApp payment link
  - Sends email invoice

Monthly reminders:
  - 27th: first reminder if unpaid
  - 30th: second reminder
  - 5th next month: final notice + escalate to founder

Reconciliation:
  - Daily 10 AM: check payment status, update sheet
"""
import logging
import razorpay
from datetime import datetime, timedelta
from core.config import cfg
from core.utils import send_whatsapp_safe, send_email, notify_founder, sheet_read, get_sheet, ts

log = logging.getLogger("shyra.agent08")

MONTHLY_RETAINER = 2000  # ₹ per agent


def get_razorpay_client():
    return razorpay.Client(auth=(cfg.RAZORPAY_KEY, cfg.RAZORPAY_SECRET))


def create_invoice(client_name: str, amount: int, description: str) -> dict:
    """Create Razorpay payment link."""
    rz = get_razorpay_client()
    data = {
        "amount": amount * 100,  # paise
        "currency": "INR",
        "description": description,
        "customer": {"name": client_name},
        "notify": {"sms": False, "email": False},
        "reminder_enable": True,
        "notes": {"client": client_name, "month": datetime.now().strftime("%B %Y")},
        "expire_by": int((datetime.now() + timedelta(days=10)).timestamp()),
    }
    try:
        link = rz.payment_link.create(data)
        return {"url": link.get("short_url",""), "id": link.get("id","")}
    except Exception as e:
        log.error(f"Razorpay link creation failed for {client_name}: {e}")
        return {"url": "", "id": ""}


def raise_monthly_invoices():
    log.info("Agent 08 — Raising monthly invoices")
    month = datetime.now().strftime("%B %Y")

    try:
        clients = sheet_read(cfg.CLIENTS_SHEET_ID)
    except Exception as e:
        log.error(f"Failed to read clients: {e}")
        return

    active = [c for c in clients if c.get("Status","").lower() == "active"]
    log.info(f"Raising invoices for {len(active)} clients")

    for client in active:
        name = client.get("Client Name","")
        phone = client.get("Phone","")
        email = client.get("Email","")
        agent_count = len(client.get("Agents","").split(","))
        amount = MONTHLY_RETAINER * agent_count

        try:
            inv = create_invoice(name, amount, f"Shyra AI — Monthly Retainer {month}")
            url = inv.get("url","")

            # WhatsApp
            wa = f"""*Invoice — {month}* 📄

Hi {name.split()[0]}!

Your Shyra AI monthly retainer is due:
💰 Amount: ₹{amount:,}
📅 Due: {(datetime.now() + timedelta(days=5)).strftime('%d %B %Y')}

Pay securely: {url}

Or transfer to:
Bank: HDFC
Acc: [YOUR_ACCOUNT]
IFSC: [YOUR_IFSC]
Ref: SHYRA-{name.replace(' ','').upper()[:8]}

Receipt sent automatically on payment 🙏"""

            send_whatsapp_safe(phone, wa)

            # Email
            if email:
                html = f"""<div style="font-family:Arial;max-width:600px">
<h2>Invoice — {month}</h2>
<table style="border-collapse:collapse;width:100%">
<tr style="background:#0f0f0e;color:white"><td style="padding:8px">Description</td><td style="padding:8px">Amount</td></tr>
<tr><td style="padding:8px;border:1px solid #eee">Shyra AI — {client.get('Agents','')} — Monthly Retainer</td><td style="padding:8px;border:1px solid #eee">₹{amount:,}</td></tr>
<tr style="font-weight:bold"><td style="padding:8px;border:1px solid #eee">Total</td><td style="padding:8px;border:1px solid #eee">₹{amount:,}</td></tr>
</table>
<br>
<a href="{url}" style="background:linear-gradient(135deg,#f97316,#a855f7);color:white;padding:12px 24px;border-radius:100px;text-decoration:none">Pay Now ₹{amount:,} →</a>
<p style="font-size:12px;color:#999;margin-top:24px">Shyra AI · Sharkify Technology Pvt Ltd · GST: [YOUR_GST]</p>
</div>"""
                send_email(email, name, f"Invoice {month} — Shyra AI ₹{amount:,}", html)

            log.info(f"Invoice raised: {name} ₹{amount:,}")

        except Exception as e:
            log.error(f"Invoice failed for {name}: {e}")
            notify_founder(f"⚠️ Invoice failed: {name}\n{e}")


def send_payment_reminders(reminder_day: int):
    """reminder_day: 1=first, 2=second, 3=final"""
    log.info(f"Agent 08 — Payment reminders (day {reminder_day})")

    try:
        clients = sheet_read(cfg.CLIENTS_SHEET_ID)
    except Exception:
        return

    for client in clients:
        if client.get("Payment Status","").lower() in ("paid",""):
            continue
        if client.get("Status","").lower() != "active":
            continue

        name = client.get("Client Name","")
        phone = client.get("Phone","")
        amount = MONTHLY_RETAINER * len(client.get("Agents","").split(","))

        if reminder_day == 1:
            msg = f"Hi {name.split()[0]}! Just a reminder — your Shyra AI invoice of ₹{amount:,} is due. Pay via the link we sent earlier or reply for any help. 🙏"
        elif reminder_day == 2:
            msg = f"Hi {name.split()[0]}, your Shyra AI payment of ₹{amount:,} is 3 days overdue. Please pay at your earliest — your agent continues running smoothly. Reply if you need any help."
        else:
            # Final — escalate to founder
            msg = f"Hi {name.split()[0]}, this is a final reminder for your Shyra AI invoice of ₹{amount:,}. Please pay today to avoid service interruption. Reply here or call us directly."
            notify_founder(f"*Final payment reminder sent*\n{name} · ₹{amount:,}")

        send_whatsapp_safe(phone, msg)
        log.info(f"Reminder {reminder_day} sent: {name}")


def check_payments():
    """Daily: verify Razorpay payments and update sheet."""
    log.info("Agent 08 — Checking payment status")
    # In production: call Razorpay payment links list API
    # and update the sheet with actual payment status
    try:
        rz = get_razorpay_client()
        # Get all payment links from this month
        month_start = int(datetime.now().replace(day=1, hour=0).timestamp())
        links = rz.payment_link.all({"created_at": month_start})
        for link in links.get("items", []):
            client_name = link.get("notes", {}).get("client","")
            status = link.get("status","")
            if status == "paid" and client_name:
                # Update sheet
                try:
                    ws = get_sheet(cfg.CLIENTS_SHEET_ID)
                    records = ws.get_all_values()
                    for i, row in enumerate(records):
                        if row and row[0] == client_name:
                            ws.update_cell(i+1, 12, "paid")
                            ws.update_cell(i+1, 13, ts())
                            break
                except Exception:
                    pass
    except Exception as e:
        log.error(f"Payment check failed: {e}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--action", choices=["raise","remind1","remind2","final","check"], required=True)
    args = p.parse_args()
    if args.action == "raise":   raise_monthly_invoices()
    elif args.action == "remind1": send_payment_reminders(1)
    elif args.action == "remind2": send_payment_reminders(2)
    elif args.action == "final":   send_payment_reminders(3)
    elif args.action == "check":   check_payments()
