"""
SHYRA PRODUCTION — Core Config
================================
Single source of truth for all settings.
All values from environment variables.
"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    # ── Environment
    ENV: str = os.getenv("ENV", "production")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    PORT: int = int(os.getenv("PORT", "8000"))

    # ── AI
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = "claude-opus-4-6"
    CLAUDE_MODEL_FAST: str = "claude-haiku-4-5-20251001"

    # ── WhatsApp (authkey.io)
    AUTHKEY_IO: str = os.getenv("AUTHKEY_IO", "")            # authkey.io API key
    WA_MAIN_WID: str = os.getenv("WA_MAIN_WID", "")          # Default text template WID
    WA_COUNTRY_CODE: str = os.getenv("WA_COUNTRY_CODE", "91")
    # Kept for backwards compat checks
    WA_API_KEY: str = os.getenv("AUTHKEY_IO", "")
    WA_MAIN_NUMBER: str = os.getenv("WA_MAIN_NUMBER", "")     # prospects
    WA_SUPPORT_NUMBER: str = os.getenv("WA_SUPPORT_NUMBER", "") # existing clients
    WA_VERIFY_TOKEN: str = os.getenv("WA_VERIFY_TOKEN", "shyra_prod_2025")

    # ── Internal team
    FOUNDER_NUMBER: str = os.getenv("FOUNDER_NUMBER", "")
    SALES_NUMBER: str = os.getenv("SALES_NUMBER", "")
    BUILD_NUMBER: str = os.getenv("BUILD_NUMBER", "")

    # ── Email
    SENDGRID_KEY: str = os.getenv("SENDGRID_KEY", "")
    FROM_EMAIL: str = "rohan@sharkify.ai"
    FROM_NAME: str = "Shyra AI"

    # ── Google
    MAPS_API_KEY: str = os.getenv("MAPS_API_KEY", "")
    GOOGLE_CREDS_JSON: str = os.getenv("GOOGLE_CREDS_JSON", "")  # JSON string
    GOOGLE_CREDS_FILE: str = os.getenv("GOOGLE_CREDS_FILE", "credentials.json")
    LEADS_SHEET_ID: str = os.getenv("LEADS_SHEET_ID", "")
    CLIENTS_SHEET_ID: str = os.getenv("CLIENTS_SHEET_ID", "")
    CALLS_SHEET_ID: str = os.getenv("CALLS_SHEET_ID", "")

    # ── Razorpay
    RAZORPAY_KEY: str = os.getenv("RAZORPAY_KEY", "")
    RAZORPAY_SECRET: str = os.getenv("RAZORPAY_SECRET", "")

    # ── Meta
    META_TOKEN: str = os.getenv("META_TOKEN", "")
    META_PAGE_ID: str = os.getenv("META_PAGE_ID", "")
    INSTAGRAM_ID: str = os.getenv("INSTAGRAM_ID", "")
    LINKEDIN_TOKEN: str = os.getenv("LINKEDIN_TOKEN", "")
    LINKEDIN_ORG: str = os.getenv("LINKEDIN_ORG", "")

    # ── Redis (for conversation state)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # ── Sentry (error tracking)
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")

    # ── Business context
    SHYRA_CONTEXT: str = """
Shyra AI builds custom AI agents for Indian and UAE businesses.
Setup: ₹20,000 one-time. Monthly: ₹2,000. Live in 7 days.
HQ: Hyderabad (Sharkify Technology Pvt Ltd). USA: Roku Digital Inc.
Serving: Hyderabad, Mumbai, Bangalore, Dubai, US & Europe.
Email: rohan@sharkify.ai
"""

cfg = Config()

# Validate critical keys on startup
def validate():
    missing = []
    for key in ["ANTHROPIC_API_KEY", "WA_API_KEY", "SENDGRID_KEY"]:
        if not getattr(cfg, key):
            missing.append(key)
    if missing:
        import logging
        logging.warning(f"Missing env vars: {missing}")
    return len(missing) == 0
