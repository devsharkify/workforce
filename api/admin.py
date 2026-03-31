"""
SHYRA ADMIN — API Key Management Routes
=========================================
Mounted at /admin/* in the main Flask server.
Protected by ADMIN_TOKEN env var.
Lets you read, write, and test all API keys without SSH.

Add to server.py:
  from api.admin import admin_bp
  app.register_blueprint(admin_bp)
"""
import os
import json
import logging
import requests
from flask import Blueprint, request, jsonify
from functools import wraps

log = logging.getLogger("shyra.admin")

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")  # Set this in Railway env vars

# All keys Shyra needs, grouped by service
KEY_GROUPS = {
    "AI": [
        {"key": "ANTHROPIC_API_KEY",  "label": "Anthropic (Claude)", "required": True,
         "hint": "sk-ant-...", "docs": "https://console.anthropic.com/"},
    ],
    "WhatsApp": [
        {"key": "WA_API_KEY",         "label": "360dialog API Key",  "required": True,
         "hint": "Your 360dialog channel API key", "docs": "https://hub.360dialog.com/"},
        {"key": "WA_API_URL",         "label": "360dialog Base URL", "required": True,
         "hint": "https://waba.360dialog.io/v1",   "docs": ""},
        {"key": "WA_MAIN_NUMBER",     "label": "Main WA Number",     "required": True,
         "hint": "919XXXXXXXXX (no +)",             "docs": ""},
        {"key": "WA_SUPPORT_NUMBER",  "label": "Support WA Number",  "required": False,
         "hint": "919XXXXXXXXX (no +)",             "docs": ""},
        {"key": "WA_VERIFY_TOKEN",    "label": "Webhook Verify Token","required": True,
         "hint": "shyra_prod_2025",                 "docs": ""},
    ],
    "Team": [
        {"key": "FOUNDER_NUMBER",     "label": "Founder WhatsApp",   "required": True,  "hint": "919XXXXXXXXX", "docs": ""},
        {"key": "SALES_NUMBER",       "label": "Sales Team WhatsApp","required": False, "hint": "919XXXXXXXXX", "docs": ""},
        {"key": "BUILD_NUMBER",       "label": "Build Team WhatsApp","required": False, "hint": "919XXXXXXXXX", "docs": ""},
    ],
    "Email": [
        {"key": "SENDGRID_KEY",       "label": "SendGrid API Key",   "required": True,
         "hint": "SG.xxxx...", "docs": "https://app.sendgrid.com/settings/api_keys"},
    ],
    "Google": [
        {"key": "MAPS_API_KEY",       "label": "Google Maps API Key","required": True,
         "hint": "AIzaSy...", "docs": "https://console.cloud.google.com/"},
        {"key": "GOOGLE_CREDS_JSON",  "label": "Google Service Account JSON", "required": True,
         "hint": 'Paste full JSON: {"type":"service_account",...}', "docs": "https://console.cloud.google.com/iam-admin/serviceaccounts"},
        {"key": "LEADS_SHEET_ID",     "label": "Leads Sheet ID",     "required": True,
         "hint": "From Google Sheets URL", "docs": ""},
        {"key": "CLIENTS_SHEET_ID",   "label": "Clients Sheet ID",   "required": True,
         "hint": "From Google Sheets URL", "docs": ""},
        {"key": "CALLS_SHEET_ID",     "label": "Calls Sheet ID",     "required": False,
         "hint": "From Google Sheets URL", "docs": ""},
    ],
    "Billing": [
        {"key": "RAZORPAY_KEY",       "label": "Razorpay Key ID",    "required": True,
         "hint": "rzp_live_...", "docs": "https://dashboard.razorpay.com/app/keys"},
        {"key": "RAZORPAY_SECRET",    "label": "Razorpay Secret",    "required": True,
         "hint": "Your secret key", "docs": ""},
    ],
    "Social": [
        {"key": "META_TOKEN",         "label": "Meta Access Token",  "required": False,
         "hint": "For Facebook/Instagram posting", "docs": "https://developers.facebook.com/"},
        {"key": "META_PAGE_ID",       "label": "Meta Page ID",       "required": False, "hint": "", "docs": ""},
        {"key": "INSTAGRAM_ID",       "label": "Instagram Account ID","required": False, "hint": "", "docs": ""},
        {"key": "LINKEDIN_TOKEN",     "label": "LinkedIn Access Token","required": False,
         "hint": "For LinkedIn posting", "docs": "https://www.linkedin.com/developers/"},
        {"key": "LINKEDIN_ORG",       "label": "LinkedIn Org ID",    "required": False, "hint": "", "docs": ""},
    ],
    "System": [
        {"key": "ADMIN_TOKEN",        "label": "Admin Panel Password","required": True,
         "hint": "Set a strong secret — this protects this panel", "docs": ""},
        {"key": "SENTRY_DSN",         "label": "Sentry DSN",         "required": False,
         "hint": "For error tracking", "docs": "https://sentry.io/"},
        {"key": "REDIS_URL",          "label": "Redis URL",          "required": False,
         "hint": "redis://localhost:6379/0", "docs": ""},
        {"key": "ENV",                "label": "Environment",        "required": True,
         "hint": "production", "docs": ""},
        {"key": "PORT",               "label": "Port",               "required": True,
         "hint": "8000", "docs": ""},
    ],
}

SENSITIVE_KEYS = {
    "ANTHROPIC_API_KEY", "WA_API_KEY", "SENDGRID_KEY", "MAPS_API_KEY",
    "RAZORPAY_KEY", "RAZORPAY_SECRET", "GOOGLE_CREDS_JSON", "ADMIN_TOKEN",
    "META_TOKEN", "LINKEDIN_TOKEN"
}


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Admin-Token", "") or request.args.get("token", "")
        if not ADMIN_TOKEN:
            return jsonify({"error": "ADMIN_TOKEN not set on server"}), 403
        if token != ADMIN_TOKEN:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ── GET /admin/keys — return all keys with current values (masked)
@admin_bp.route("/keys", methods=["GET"])
@require_auth
def get_keys():
    result = {}
    for group, keys in KEY_GROUPS.items():
        result[group] = []
        for k in keys:
            env_val = os.environ.get(k["key"], "")
            masked = _mask(env_val, k["key"])
            result[group].append({
                **k,
                "value": masked,
                "set": bool(env_val),
            })
    return jsonify(result), 200


# ── POST /admin/keys — save one key to env (runtime only; see note)
@admin_bp.route("/keys", methods=["POST"])
@require_auth
def set_key():
    """
    Sets an env var in the CURRENT PROCESS (runtime).
    For permanent storage, update Railway env vars via the Railway dashboard
    or use the Railway API (see /admin/railway-update).
    """
    data = request.json or {}
    key = data.get("key", "").strip().upper()
    value = data.get("value", "").strip()

    if not key or key not in _all_keys():
        return jsonify({"error": "Unknown key"}), 400

    os.environ[key] = value
    log.info(f"Admin set: {key} = {_mask(value, key)}")
    return jsonify({"status": "ok", "key": key, "masked": _mask(value, key)}), 200


# ── POST /admin/keys/bulk — save multiple keys at once
@admin_bp.route("/keys/bulk", methods=["POST"])
@require_auth
def set_keys_bulk():
    data = request.json or {}
    updates = data.get("keys", {})
    saved = []
    errors = []

    for key, value in updates.items():
        key = key.strip().upper()
        if key not in _all_keys():
            errors.append(f"Unknown key: {key}")
            continue
        os.environ[key] = str(value).strip()
        saved.append(key)
        log.info(f"Admin bulk set: {key}")

    # Reload config
    try:
        from core.config import cfg
        cfg.__init__()
    except Exception:
        pass

    return jsonify({"saved": saved, "errors": errors}), 200


# ── POST /admin/test — test if a key actually works
@admin_bp.route("/test/<key_name>", methods=["POST"])
@require_auth
def test_key(key_name):
    key_name = key_name.upper()
    value = os.environ.get(key_name, "")

    if not value:
        return jsonify({"status": "not_set", "message": "Key not configured"}), 200

    result = _test_key(key_name, value)
    return jsonify(result), 200


# ── GET /admin/status — overall system health
@admin_bp.route("/status", methods=["GET"])
@require_auth
def status():
    checks = {}
    required_keys = [k["key"] for g in KEY_GROUPS.values() for k in g if k["required"]]

    for key in required_keys:
        checks[key] = bool(os.environ.get(key, ""))

    all_set = all(checks.values())
    pct = int(sum(checks.values()) / len(checks) * 100) if checks else 0

    return jsonify({
        "ready": all_set,
        "completion": pct,
        "checks": checks,
        "missing": [k for k, v in checks.items() if not v],
    }), 200


# ── GET /admin/export — export all keys as .env format (for backup)
@admin_bp.route("/export", methods=["GET"])
@require_auth
def export_env():
    lines = ["# Shyra AI — Environment Variables Export"]
    for group, keys in KEY_GROUPS.items():
        lines.append(f"\n# {group}")
        for k in keys:
            val = os.environ.get(k["key"], "")
            lines.append(f"{k['key']}={val}")

    return "\n".join(lines), 200, {
        "Content-Type": "text/plain",
        "Content-Disposition": "attachment; filename=shyra.env"
    }


def _mask(value: str, key: str) -> str:
    if not value:
        return ""
    if key not in SENSITIVE_KEYS:
        return value
    if len(value) <= 8:
        return "••••••••"
    return value[:4] + "••••••••" + value[-4:]


def _all_keys() -> set:
    return {k["key"] for g in KEY_GROUPS.values() for k in g}


def _test_key(key_name: str, value: str) -> dict:
    """Test if a key actually works by hitting the real API."""
    try:
        if key_name == "ANTHROPIC_API_KEY":
            import anthropic
            client = anthropic.Anthropic(api_key=value)
            client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=10,
                                   messages=[{"role": "user", "content": "hi"}])
            return {"status": "ok", "message": "Anthropic API key is valid"}

        elif key_name == "WA_API_KEY":
            url = os.environ.get("WA_API_URL", "https://waba.360dialog.io/v1") + "/configs/webhook"
            resp = requests.get(url, headers={"D360-API-KEY": value}, timeout=8)
            if resp.status_code < 400:
                return {"status": "ok", "message": "WhatsApp API key is valid"}
            return {"status": "error", "message": f"HTTP {resp.status_code}"}

        elif key_name == "SENDGRID_KEY":
            resp = requests.get("https://api.sendgrid.com/v3/scopes",
                               headers={"Authorization": f"Bearer {value}"}, timeout=8)
            if resp.ok:
                return {"status": "ok", "message": "SendGrid key is valid"}
            return {"status": "error", "message": f"HTTP {resp.status_code}"}

        elif key_name == "MAPS_API_KEY":
            resp = requests.get("https://maps.googleapis.com/maps/api/place/textsearch/json",
                               params={"query": "test", "key": value}, timeout=8)
            data = resp.json()
            if data.get("status") not in ("REQUEST_DENIED", "INVALID_REQUEST"):
                return {"status": "ok", "message": "Google Maps key is valid"}
            return {"status": "error", "message": data.get("error_message", "Invalid key")}

        elif key_name == "RAZORPAY_KEY":
            import razorpay
            rz = razorpay.Client(auth=(value, os.environ.get("RAZORPAY_SECRET", "")))
            rz.order.all({"count": 1})
            return {"status": "ok", "message": "Razorpay credentials are valid"}

        elif key_name == "GOOGLE_CREDS_JSON":
            json.loads(value)  # Basic JSON validation
            return {"status": "ok", "message": "Valid JSON — connect Google Sheets to fully verify"}

        else:
            return {"status": "unknown", "message": "No test available for this key"}

    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid JSON format"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:120]}
