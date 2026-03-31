"""
SHYRA PRODUCTION — Master Orchestrator
=========================================
Single process that runs all scheduled agents.
Deploy as Railway service — always on.

Schedule:
  07:00 daily   — Lead Scraper (Agent 01)
  07:30 daily   — Morning Briefing (Agent 15)
  09:00 daily   — Outreach Agent (Agent 02)
  09:15 daily   — Social Content (Agent 11)
  10:00 daily   — Testimonials (Agent 10)
  20:00 daily   — Churn Predictor (Agent 07)
  21:00 daily   — Quality Monitor (Agent 14)
  10:00 daily   — Payment Status Check (Agent 08)
  Mon 08:00     — Competitor Intel (Agent 12)
  1st 09:00     — ROI Reports (Agent 05)
  5th 09:00     — Upsell Detector (Agent 06)
  25th 09:00    — Raise Invoices (Agent 08)
  27th 10:00    — Payment Reminder 1 (Agent 08)
  30th 10:00    — Payment Reminder 2 (Agent 08)
  5th+1 10:00   — Final Payment Notice (Agent 08)
  Daily 10:30   — Referral Agent (Agent 13)
"""
import logging
import threading
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from core.config import cfg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("shyra.orchestrator")


def safe_run(agent_name: str, fn, *args, **kwargs):
    """Run any agent with error isolation — one failure doesn't stop others."""
    try:
        log.info(f"▶ Starting {agent_name}")
        fn(*args, **kwargs)
        log.info(f"✓ {agent_name} complete")
    except Exception as e:
        log.error(f"✗ {agent_name} failed: {e}", exc_info=True)
        try:
            from core.utils import notify_founder
            notify_founder(f"⚠️ Agent failed: {agent_name}\n{str(e)[:200]}")
        except Exception:
            pass


def main():
    log.info("═══════════════════════════════════")
    log.info("  SHYRA AI — Production Orchestrator")
    log.info(f"  ENV: {cfg.ENV} | Port: {cfg.PORT}")
    log.info("═══════════════════════════════════")

    # Import all agents
    from agents import (
        lead_scraper, outreach_agent,
        roi_upsell, churn_predictor, billing_agent,
        testimonial_social, intel_referral, quality_briefing,
    )

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")

    # ── Daily agents
    scheduler.add_job(
        lambda: safe_run("Lead Scraper", lead_scraper.run),
        CronTrigger(hour=7, minute=0), id="lead_scraper"
    )
    scheduler.add_job(
        lambda: safe_run("Morning Briefing", quality_briefing.run_morning_briefing),
        CronTrigger(hour=7, minute=30), id="morning_briefing"
    )
    scheduler.add_job(
        lambda: safe_run("Outreach Agent", outreach_agent.run),
        CronTrigger(hour=9, minute=0), id="outreach"
    )
    scheduler.add_job(
        lambda: safe_run("Social Content", testimonial_social.run_social_content),
        CronTrigger(day_of_week="mon", hour=9, minute=15), id="social_content"
    )
    scheduler.add_job(
        lambda: safe_run("Testimonials", testimonial_social.run_testimonial_collector),
        CronTrigger(hour=10, minute=0), id="testimonials"
    )
    scheduler.add_job(
        lambda: safe_run("Payment Check", billing_agent.check_payments),
        CronTrigger(hour=10, minute=15), id="payment_check"
    )
    scheduler.add_job(
        lambda: safe_run("Referral Agent", intel_referral.run_referral_agent),
        CronTrigger(hour=10, minute=30), id="referral"
    )
    scheduler.add_job(
        lambda: safe_run("Churn Predictor", churn_predictor.run),
        CronTrigger(hour=20, minute=0), id="churn"
    )
    scheduler.add_job(
        lambda: safe_run("Quality Monitor", quality_briefing.run_quality_monitor),
        CronTrigger(hour=21, minute=0), id="quality"
    )

    # ── Weekly
    scheduler.add_job(
        lambda: safe_run("Knowledge Distiller", agent16.run),
        CronTrigger(day_of_week="sun", hour=6, minute=0), id="kb_distiller"
    )
    scheduler.add_job(
        lambda: safe_run("Competitor Intel", intel_referral.run_competitor_intel),
        CronTrigger(day_of_week="mon", hour=8, minute=0), id="intel"
    )

    # ── Monthly
    scheduler.add_job(
        lambda: safe_run("ROI Reports", roi_upsell.run_roi_reports),
        CronTrigger(day=1, hour=9, minute=0), id="roi_reports"
    )
    scheduler.add_job(
        lambda: safe_run("Upsell Detector", roi_upsell.run_upsell_detector),
        CronTrigger(day=5, hour=9, minute=0), id="upsell"
    )
    scheduler.add_job(
        lambda: safe_run("Raise Invoices", billing_agent.raise_monthly_invoices),
        CronTrigger(day=25, hour=9, minute=0), id="invoices"
    )
    scheduler.add_job(
        lambda: safe_run("Payment Reminder 1", billing_agent.send_payment_reminders, 1),
        CronTrigger(day=27, hour=10, minute=0), id="remind1"
    )
    scheduler.add_job(
        lambda: safe_run("Payment Reminder 2", billing_agent.send_payment_reminders, 2),
        CronTrigger(day=30, hour=10, minute=0), id="remind2"
    )
    scheduler.add_job(
        lambda: safe_run("Final Payment Notice", billing_agent.send_payment_reminders, 3),
        CronTrigger(day=5, month="2-12", hour=10, minute=0), id="remind_final"
    )

    # ── Start API server in background thread
    def start_api():
        import sys; sys.path.insert(0, ".")
        from api.server import app
        import gunicorn.app.base

        class StandaloneApplication(gunicorn.app.base.BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()
            def load_config(self):
                for key, value in self.options.items():
                    self.cfg.set(key.lower(), value)
            def load(self):
                return self.application

        options = {
            "bind": f"0.0.0.0:{cfg.PORT}",
            "workers": 2,
            "timeout": 120,
            "accesslog": "-",
            "errorlog": "-",
        }
        StandaloneApplication(app, options).run()

    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()
    log.info(f"API server started on port {cfg.PORT}")

    # Print schedule summary
    jobs = scheduler.get_jobs()
    log.info(f"Scheduled {len(jobs)} jobs:")
    for job in jobs:
        log.info(f"  {job.id}: {job.trigger}")

    log.info("Orchestrator running. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Orchestrator stopped.")


# Make agents importable
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Create agents package shims
import types

agents_module = types.ModuleType("agents")
sys.modules["agents"] = agents_module

# Import each agent module
import importlib.util

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    setattr(agents_module, name, mod)

base = os.path.join(os.path.dirname(__file__), "agents")
_load("lead_scraper",       f"{base}/01_lead_scraper.py")
_load("outreach_agent",     f"{base}/02_outreach_agent.py")
_load("roi_upsell",         f"{base}/05_06_roi_upsell.py")
_load("churn_predictor",    f"{base}/07_churn_predictor.py")
_load("billing_agent",      f"{base}/08_billing_agent.py")
_load("testimonial_social", f"{base}/10_11_testimonial_social.py")
_load("intel_referral",     f"{base}/12_13_intel_referral.py")
_load("quality_briefing",   f"{base}/14_15_quality_briefing.py")
_load("agent16",           f"{base}/16_knowledge_distiller.py")


if __name__ == "__main__":
    main()
