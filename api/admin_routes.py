"""
SHYRA ADMIN — API Key Management Routes
=========================================
Add these routes to api/server.py

Protected by ADMIN_PASSWORD env var.
Keys stored in Railway environment variables via Railway API,
or fallback to local .env file for dev.

Routes:
  GET  /admin          — Admin panel HTML
  GET  /admin/keys     — List all keys (masked)
  POST /admin/keys     — Save / update keys
  POST /admin/test     — Test a specific key
  GET  /admin/health   — Check which services are connected
"""
import os
import json
import hashlib
import requests
import functools
from flask import request, jsonify, make_response

# ── Admin password — set ADMIN_PASSWORD in env
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "shyra_admin_2025")
ADMIN_TOKEN = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()[:32]

# ── All managed keys with metadata
MANAGED_KEYS = [
    # group, key, label, required, placeholder, type, hint
    ("AI",       "ANTHROPIC_API_KEY",   "Anthropic API Key",       True,  "sk-ant-...",         "secret", "Get from console.anthropic.com"),
    ("WhatsApp", "WA_API_KEY",          "360dialog API Key",        True,  "your_360dialog_key", "secret", "From 360dialog partner hub"),
    ("WhatsApp", "WA_API_URL",          "360dialog API URL",        True,  "https://waba.360dialog.io/v1", "text", ""),
    ("WhatsApp", "WA_MAIN_NUMBER",      "Main WhatsApp Number",     True,  "919XXXXXXXXX",       "text",   "Prospects inbox — include country code"),
    ("WhatsApp", "WA_SUPPORT_NUMBER",   "Support WhatsApp Number",  False, "919XXXXXXXXX",       "text",   "Existing clients inbox"),
    ("WhatsApp", "WA_VERIFY_TOKEN",     "Webhook Verify Token",     True,  "shyra_prod_2025",    "text",   "Set the same in 360dialog dashboard"),
    ("Team",     "FOUNDER_NUMBER",      "Founder WhatsApp",         True,  "919XXXXXXXXX",       "text",   "Rohan's number"),
    ("Team",     "SALES_NUMBER",        "Sales Team WhatsApp",      False, "919XXXXXXXXX",       "text",   "Gets lead alerts"),
    ("Team",     "BUILD_NUMBER",        "Build Team WhatsApp",      False, "919XXXXXXXXX",       "text",   "Gets onboarding tasks"),
    ("Email",    "SENDGRID_KEY",        "SendGrid API Key",         True,  "SG.xxxxx",           "secret", "From sendgrid.com/settings/api_keys"),
    ("Google",   "MAPS_API_KEY",        "Google Maps API Key",      True,  "AIzaSy...",          "secret", "Enable Places API + Custom Search"),
    ("Google",   "GOOGLE_CREDS_JSON",   "Google Service Account",   True,  '{"type":"service_account"...}', "textarea", "Paste full JSON from GCP console"),
    ("Google",   "LEADS_SHEET_ID",      "Leads Sheet ID",           True,  "1BxiMVs0...",        "text",   "From Google Sheets URL"),
    ("Google",   "CLIENTS_SHEET_ID",    "Clients Sheet ID",         True,  "1BxiMVs0...",        "text",   ""),
    ("Google",   "CALLS_SHEET_ID",      "Calls Sheet ID",           False, "1BxiMVs0...",        "text",   ""),
    ("Billing",  "RAZORPAY_KEY",        "Razorpay Key ID",          True,  "rzp_live_...",       "secret", "From razorpay.com/app/keys"),
    ("Billing",  "RAZORPAY_SECRET",     "Razorpay Key Secret",      True,  "your_secret",        "secret", ""),
    ("Social",   "META_TOKEN",          "Meta Access Token",        False, "",                   "secret", "For Instagram/Facebook posting"),
    ("Social",   "META_PAGE_ID",        "Meta Page ID",             False, "",                   "text",   ""),
    ("Social",   "INSTAGRAM_ID",        "Instagram Account ID",     False, "",                   "text",   ""),
    ("Social",   "LINKEDIN_TOKEN",      "LinkedIn Access Token",    False, "",                   "secret", "For LinkedIn posting"),
    ("Social",   "LINKEDIN_ORG",        "LinkedIn Organisation ID", False, "",                   "text",   ""),
    ("System",   "SENTRY_DSN",          "Sentry DSN",               False, "https://...@sentry.io/...", "text", "Error tracking"),
    ("System",   "REDIS_URL",           "Redis URL",                False, "redis://localhost:6379/0", "text", "For conversation state"),
    ("System",   "ADMIN_PASSWORD",      "Admin Panel Password",     True,  "shyra_admin_2025",   "secret", "Change this immediately"),
]


def admin_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        token = request.cookies.get("admin_token") or request.headers.get("X-Admin-Token", "")
        if token != ADMIN_TOKEN:
            if request.path == "/admin" and request.method == "GET":
                return make_response(login_html(), 200)
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


def mask_value(key: str, value: str) -> str:
    """Mask secrets but show enough to confirm they're set."""
    if not value:
        return ""
    secret_keys = ["KEY", "SECRET", "TOKEN", "PASSWORD", "DSN", "CREDS"]
    if any(s in key for s in secret_keys) and key != "WA_API_URL":
        if len(value) <= 8:
            return "••••••••"
        return value[:4] + "••••••••" + value[-4:]
    return value


def save_to_env_file(updates: dict) -> bool:
    """Write to .env file for local dev."""
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    try:
        # Read existing
        existing = {}
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        existing[k.strip()] = v.strip()
        # Merge
        existing.update({k: v for k, v in updates.items() if v})
        # Write
        with open(env_path, "w") as f:
            for k, v in existing.items():
                f.write(f"{k}={v}\n")
        # Also update os.environ live
        for k, v in updates.items():
            if v:
                os.environ[k] = v
        return True
    except Exception as e:
        log.error(f"Env save failed: {e}")
        return False


def get_railway_service_id() -> str:
    return os.getenv("RAILWAY_SERVICE_ID", "")


def save_to_railway(updates: dict) -> dict:
    """
    Save variables to Railway environment via Railway API.
    Requires RAILWAY_API_TOKEN env var.
    """
    token = os.getenv("RAILWAY_API_TOKEN", "")
    service_id = get_railway_service_id()
    if not token or not service_id:
        return {"success": False, "reason": "RAILWAY_API_TOKEN or RAILWAY_SERVICE_ID not set — saving to .env only"}

    project_id = os.getenv("RAILWAY_PROJECT_ID", "")
    env_id = os.getenv("RAILWAY_ENVIRONMENT_ID", "production")

    mutation = """
mutation upsertVariables($input: VariableCollectionUpsertInput!) {
  variableCollectionUpsert(input: $input)
}
"""
    variables_payload = [{"name": k, "value": v} for k, v in updates.items() if v]

    try:
        resp = requests.post(
            "https://backboard.railway.app/graphql/v2",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "query": mutation,
                "variables": {
                    "input": {
                        "projectId": project_id,
                        "environmentId": env_id,
                        "serviceId": service_id,
                        "variables": {item["name"]: item["value"] for item in variables_payload}
                    }
                }
            },
            timeout=15
        )
        data = resp.json()
        if data.get("data", {}).get("variableCollectionUpsert"):
            return {"success": True, "saved_to": "Railway + .env"}
        return {"success": False, "reason": str(data.get("errors", "Unknown error"))}
    except Exception as e:
        return {"success": False, "reason": str(e)}


def test_key(key_name: str, value: str) -> dict:
    """Test if a specific API key works."""
    try:
        if key_name == "ANTHROPIC_API_KEY":
            import anthropic as ac
            client = ac.Anthropic(api_key=value)
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=10,
                messages=[{"role": "user", "content": "hi"}]
            )
            return {"ok": True, "msg": "Anthropic connected"}

        elif key_name == "WA_API_KEY":
            resp = requests.get(
                f"{os.getenv('WA_API_URL', 'https://waba.360dialog.io/v1')}/configs/webhook",
                headers={"D360-API-KEY": value}, timeout=8
            )
            return {"ok": resp.status_code < 400, "msg": f"360dialog: HTTP {resp.status_code}"}

        elif key_name == "SENDGRID_KEY":
            resp = requests.get(
                "https://api.sendgrid.com/v3/user/profile",
                headers={"Authorization": f"Bearer {value}"}, timeout=8
            )
            return {"ok": resp.status_code == 200, "msg": f"SendGrid: {'connected' if resp.status_code == 200 else 'invalid key'}"}

        elif key_name == "MAPS_API_KEY":
            resp = requests.get(
                f"https://maps.googleapis.com/maps/api/place/textsearch/json?query=test&key={value}",
                timeout=8
            )
            data = resp.json()
            ok = data.get("status") not in ("REQUEST_DENIED", "INVALID_REQUEST")
            return {"ok": ok, "msg": f"Google Maps: {data.get('status')}"}

        elif key_name in ("RAZORPAY_KEY", "RAZORPAY_SECRET"):
            rz_key = os.getenv("RAZORPAY_KEY") if key_name == "RAZORPAY_SECRET" else value
            rz_secret = os.getenv("RAZORPAY_SECRET") if key_name == "RAZORPAY_KEY" else value
            resp = requests.get(
                "https://api.razorpay.com/v1/payments?count=1",
                auth=(rz_key, rz_secret), timeout=8
            )
            return {"ok": resp.status_code == 200, "msg": f"Razorpay: {'connected' if resp.status_code == 200 else f'error {resp.status_code}'}"}

    except Exception as e:
        return {"ok": False, "msg": str(e)[:80]}

    return {"ok": None, "msg": "No test available for this key"}


def login_html() -> str:
    return """<!DOCTYPE html>
<html>
<head>
<title>Shyra Admin</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a0a;display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:'SF Mono',monospace}
.box{background:#111;border:1px solid #222;border-radius:16px;padding:40px;width:360px;text-align:center}
.logo{font-size:13px;letter-spacing:.25em;color:#f97316;margin-bottom:32px;text-transform:uppercase}
input{width:100%;background:#0a0a0a;border:1px solid #333;border-radius:8px;padding:12px 16px;color:#fff;font-size:14px;margin-bottom:16px;outline:none;font-family:inherit}
input:focus{border-color:#f97316}
button{width:100%;background:linear-gradient(135deg,#f97316,#a855f7);color:#fff;border:none;border-radius:8px;padding:13px;font-size:13px;cursor:pointer;letter-spacing:.05em}
.err{color:#ef4444;font-size:12px;margin-top:8px;display:none}
</style>
</head>
<body>
<div class="box">
  <div class="logo">● Shyra Admin</div>
  <input type="password" id="pwd" placeholder="Admin password" onkeydown="if(event.key==='Enter')login()">
  <button onclick="login()">Enter</button>
  <div class="err" id="err">Wrong password</div>
</div>
<script>
function login(){
  const pwd = document.getElementById('pwd').value;
  fetch('/admin/auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pwd})})
  .then(r=>r.json()).then(d=>{
    if(d.token){
      document.cookie='admin_token='+d.token+';path=/;max-age=86400';
      location.reload();
    } else {
      document.getElementById('err').style.display='block';
    }
  });
}
</script>
</body>
</html>"""
