"""
SHYRA PRODUCTION — Core Utilities
====================================
All external service calls with:
- Retry logic
- Error handling  
- Structured logging
- Rate limiting
"""
import anthropic
import requests
import gspread
import json
import logging
import time
import os
import base64
from datetime import datetime
from functools import wraps
from pathlib import Path
from google.oauth2.service_account import Credentials
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import inch

from core.config import cfg

log = logging.getLogger("shyra")

# ─────────────────────────────────────────
# RETRY DECORATOR
# ─────────────────────────────────────────
def retry(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(Exception,)):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            attempt = 0
            wait = delay
            while attempt < max_attempts:
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    attempt += 1
                    if attempt == max_attempts:
                        log.error(f"{fn.__name__} failed after {max_attempts} attempts: {e}")
                        raise
                    log.warning(f"{fn.__name__} attempt {attempt} failed: {e}. Retrying in {wait}s")
                    time.sleep(wait)
                    wait *= backoff
        return wrapper
    return decorator


# ─────────────────────────────────────────
# CLAUDE API
# ─────────────────────────────────────────
@retry(max_attempts=3, delay=1.0, exceptions=(Exception,))
def ask_claude(
    prompt: str,
    system: str = "",
    max_tokens: int = 1024,
    model: str = None,
    temperature: float = 0.7
) -> str:
    client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
    kwargs = {
        "model": model or cfg.CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return resp.content[0].text.strip()


def ask_claude_fast(prompt: str, system: str = "", max_tokens: int = 512) -> str:
    """Use Haiku for fast, cheap tasks."""
    return ask_claude(prompt, system=system, max_tokens=max_tokens, model=cfg.CLAUDE_MODEL_FAST)


def ask_claude_json(prompt: str, system: str = "", model: str = None) -> dict:
    full_system = (system + "\n\n" if system else "") + "Respond ONLY with valid JSON. No markdown, no explanation."
    raw = ask_claude(prompt, system=full_system, max_tokens=4096, model=model)
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(raw)


# ─────────────────────────────────────────
# WHATSAPP — authkey.io
# ─────────────────────────────────────────
AUTHKEY_BASE = "https://console.authkey.io/restapi"

def _normalize_number(to: str, country_code: str = "91") -> str:
    """Normalize to plain digits without country code prefix."""
    to = to.replace("+", "").replace(" ", "").replace("-", "")
    if to.startswith(country_code) and len(to) > 10:
        to = to[len(country_code):]
    return to[-10:]  # last 10 digits


@retry(max_attempts=3, delay=0.5, exceptions=(requests.HTTPError,))
def send_whatsapp(to: str, message: str, wid: str = None,
                  body_values: dict = None, header_data: str = None,
                  msg_type: str = "text") -> dict:
    """
    Send WhatsApp via authkey.io.

    Free-text (no template): wid=None — sends as session message (works within 24hr window).
    Template: pass wid + body_values dict like {"1": "value", "2": "value"}.
    Media template: pass wid + msg_type="media" + header_data=<url>.
    """
    mobile = _normalize_number(to, cfg.WA_COUNTRY_CODE)
    authkey = cfg.AUTHKEY_IO
    country = cfg.WA_COUNTRY_CODE

    if not authkey:
        raise ValueError("AUTHKEY_IO not set")

    # ── Template message (wid provided)
    if wid:
        url = f"{AUTHKEY_BASE}/requestjson.php"
        payload = {
            "country_code": country,
            "mobile": mobile,
            "wid": wid,
            "type": msg_type,
        }
        if body_values:
            payload["bodyValues"] = {str(k): str(v) for k, v in body_values.items()}
        if header_data and msg_type == "media":
            payload["headerValues"] = {"headerData": header_data}

        resp = requests.post(
            url,
            headers={"Authorization": f"Basic {authkey}", "Content-Type": "application/json"},
            json=payload,
            timeout=10
        )
        resp.raise_for_status()
        log.info(f"WhatsApp template wid={wid} sent to {mobile[:4]}****")
        return resp.json()

    # ── Free-text (session/service message — free within 24hr window)
    # Uses GET API for simple text
    params = {
        "authkey": authkey,
        "mobile": mobile,
        "country_code": country,
        "message": message,
    }
    # If WA_MAIN_WID is set and message fits template, use it
    if cfg.WA_MAIN_WID:
        # Use text template with message as body variable 1
        url = f"{AUTHKEY_BASE}/request.php"
        params["wid"] = cfg.WA_MAIN_WID
        params["1"] = message[:1024]
    else:
        url = f"https://api.authkey.io/request"
        params["channel"] = "whatsapp"

    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    log.info(f"WhatsApp sent to {mobile[:4]}****: {message[:60]}...")
    return resp.json()


def send_whatsapp_template(to: str, wid: str,
                           body_values: dict = None,
                           header_data: str = None,
                           msg_type: str = "text") -> bool:
    """Convenience wrapper for template messages."""
    return send_whatsapp_safe(to, "", wid=wid,
                              body_values=body_values,
                              header_data=header_data,
                              msg_type=msg_type)


def send_whatsapp_bulk(recipients: list, wid: str,
                       body_values_per: list = None,
                       header_data: str = None,
                       msg_type: str = "text") -> dict:
    """
    Send to up to 200 numbers in one API call.
    recipients = ["919XXXXXXXX", ...]
    body_values_per = [{"1": "John"}, {"1": "Priya"}, ...] (optional, one per recipient)
    """
    authkey = cfg.AUTHKEY_IO
    if not authkey or not recipients:
        return {"error": "missing authkey or recipients"}

    url = f"{AUTHKEY_BASE}/requestjson_v2.0.php"
    data_list = []
    for i, number in enumerate(recipients[:200]):
        mobile = _normalize_number(number, cfg.WA_COUNTRY_CODE)
        entry = {"mobile": mobile}
        if body_values_per and i < len(body_values_per):
            entry["bodyValues"] = {str(k): str(v) for k, v in body_values_per[i].items()}
        if header_data:
            entry["headerValues"] = {"headerData": header_data}
        data_list.append(entry)

    payload = {
        "version": "2.0",
        "country_code": cfg.WA_COUNTRY_CODE,
        "wid": wid,
        "type": msg_type,
        "data": data_list,
    }
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Basic {authkey}", "Content-Type": "application/json"},
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
        log.info(f"Bulk WhatsApp wid={wid} sent to {len(data_list)} numbers")
        return resp.json()
    except Exception as e:
        log.error(f"Bulk WhatsApp failed: {e}")
        return {"error": str(e)}


def send_whatsapp_safe(to: str, message: str, **kwargs) -> bool:
    """Send WhatsApp, return True/False without raising."""
    if not cfg.AUTHKEY_IO or not to:
        return False
    try:
        send_whatsapp(to, message, **kwargs)
        return True
    except Exception as e:
        log.error(f"WhatsApp to {to} failed: {e}")
        return False


def notify_founder(message: str):
    if cfg.FOUNDER_NUMBER:
        send_whatsapp_safe(cfg.FOUNDER_NUMBER, message)


def notify_sales(message: str):
    if cfg.SALES_NUMBER:
        send_whatsapp_safe(cfg.SALES_NUMBER, message)


def notify_build(message: str):
    if cfg.BUILD_NUMBER:
        send_whatsapp_safe(cfg.BUILD_NUMBER, message)


# ─────────────────────────────────────────
# GOOGLE SHEETS
# ─────────────────────────────────────────
_sheets_client = None

def _get_sheets_client():
    global _sheets_client
    if _sheets_client:
        return _sheets_client
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    # Support both file path and JSON string
    if cfg.GOOGLE_CREDS_JSON:
        import tempfile
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        tf.write(cfg.GOOGLE_CREDS_JSON)
        tf.close()
        creds = Credentials.from_service_account_file(tf.name, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file(cfg.GOOGLE_CREDS_FILE, scopes=scopes)
    _sheets_client = gspread.authorize(creds)
    return _sheets_client


def get_sheet(sheet_id: str, worksheet: str = None):
    client = _get_sheets_client()
    ss = client.open_by_key(sheet_id)
    return ss.worksheet(worksheet) if worksheet else ss.sheet1


def sheet_read(sheet_id: str, worksheet: str = None) -> list[dict]:
    try:
        return get_sheet(sheet_id, worksheet).get_all_records()
    except Exception as e:
        log.error(f"Sheet read failed ({sheet_id}): {e}")
        return []


def sheet_append(sheet_id: str, row: list, worksheet: str = None):
    try:
        get_sheet(sheet_id, worksheet).append_row(row)
    except Exception as e:
        log.error(f"Sheet append failed: {e}")


# ─────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────
def send_email(
    to: str,
    to_name: str,
    subject: str,
    html: str,
    attachment: str = None
) -> bool:
    if not cfg.SENDGRID_KEY:
        return False
    msg = Mail(
        from_email=(cfg.FROM_EMAIL, cfg.FROM_NAME),
        to_emails=[(to, to_name)],
        subject=subject,
        html_content=html
    )
    if attachment and os.path.exists(attachment):
        with open(attachment, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        msg.attachment = Attachment(
            FileContent(data),
            FileName(os.path.basename(attachment)),
            FileType("application/pdf")
        )
    try:
        sg = SendGridAPIClient(cfg.SENDGRID_KEY)
        resp = sg.send(msg)
        return resp.status_code in (200, 202)
    except Exception as e:
        log.error(f"Email to {to} failed: {e}")
        return False


# ─────────────────────────────────────────
# PDF GENERATOR
# ─────────────────────────────────────────
def generate_pdf(path: str, title: str, sections: list) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(path, pagesize=A4,
        rightMargin=0.75*inch, leftMargin=0.75*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch)
    styles = getSampleStyleSheet()
    INK = colors.HexColor("#0f0f0e")
    GRAY = colors.HexColor("#7a7870")
    BORDER = colors.HexColor("#e8e8e5")

    title_s = ParagraphStyle("T", fontSize=28, textColor=INK, fontName="Helvetica-Bold", spaceAfter=4)
    h2_s = ParagraphStyle("H2", fontSize=13, textColor=INK, spaceBefore=18, spaceAfter=6, fontName="Helvetica-Bold")
    body_s = ParagraphStyle("B", fontSize=10, textColor=GRAY, leading=16, spaceAfter=8)
    cap_s = ParagraphStyle("C", fontSize=9, textColor=GRAY, spaceAfter=20)

    story = [
        Paragraph("Shyra AI", title_s),
        Paragraph(title, h2_s),
        Paragraph(f"Generated {datetime.now().strftime('%d %B %Y')} · rohan@sharkify.ai", cap_s),
        Spacer(1, 0.15*inch)
    ]

    for section in sections:
        if section.get("heading"):
            story.append(Paragraph(section["heading"], h2_s))
        body = section.get("body", "")
        if isinstance(body, str):
            for para in body.split("\n\n"):
                if para.strip():
                    story.append(Paragraph(para.strip(), body_s))
        elif isinstance(body, list):
            table = Table(body, repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), INK),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE", (0,0), (-1,-1), 9),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f5f5f3")]),
                ("GRID", (0,0), (-1,-1), 0.5, BORDER),
                ("LEFTPADDING", (0,0), (-1,-1), 8),
                ("RIGHTPADDING", (0,0), (-1,-1), 8),
                ("TOPPADDING", (0,0), (-1,-1), 5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ]))
            story.append(table)
        story.append(Spacer(1, 0.05*inch))

    story.extend([
        Spacer(1, 0.3*inch),
        Paragraph("© Shyra AI · Sharkify Technology Pvt Ltd · rohan@sharkify.ai", cap_s)
    ])
    doc.build(story)
    return path


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def ts() -> str:
    return datetime.now().isoformat()
