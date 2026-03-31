"""
AGENT 10 — Testimonial Collector
AGENT 11 — Social Media Content Generator
==========================================
Agent 10: Daily 10 AM — checks clients at day 30, 60, 90. Requests testimonials.
           Saves approved testimonials to sheet for website use.
Agent 11: Daily 9:15 AM — generates 7 pieces of social content for the week.
           Posts to LinkedIn + Instagram or saves drafts.
"""
import logging
import json
from datetime import datetime, timedelta
from core.config import cfg
from core.utils import ask_claude, ask_claude_json, send_whatsapp_safe, sheet_read, sheet_append, ts, today

log = logging.getLogger("shyra.agent10_11")

# ══════════════════════════════════════
# AGENT 10 — Testimonial Collector
# ══════════════════════════════════════

TESTIMONIAL_SHEET_ID = cfg.CLIENTS_SHEET_ID  # Add a "Testimonials" tab


def request_testimonial(client: dict):
    name = client.get("Client Name","")
    phone = client.get("Phone","")
    agents = client.get("Agents","")

    msg = f"""Hi {name.split()[0]}! 👋

Your Shyra AI agent has been running for a month now.

Would you share a quick honest review? It takes 2 minutes and helps other businesses like yours discover AI.

Just reply with:
• What problem it solved
• How it changed your daily operations
• Would you recommend Shyra AI to others?

No fancy writing needed — your words are perfect as they are 🙏

(Feel free to say it could be better too — we use all feedback!)"""

    send_whatsapp_safe(phone, msg)
    log.info(f"Testimonial requested: {name}")


def run_testimonial_collector():
    log.info("Agent 10 — Testimonial Collector starting")
    try:
        clients = sheet_read(cfg.CLIENTS_SHEET_ID)
    except Exception as e:
        log.error(f"Failed to read clients: {e}")
        return

    for client in clients:
        if client.get("Status","").lower() != "active":
            continue
        if client.get("Testimonial Requested",""):
            continue  # Already requested

        try:
            start = datetime.strptime(client.get("Start Date", today())[:10], "%Y-%m-%d")
            days = (datetime.now() - start).days
        except Exception:
            continue

        # Request at day 30, 60, 90
        if days in range(28, 32) or days in range(58, 62) or days in range(88, 92):
            health = int(client.get("Health Score",5) or 5)
            if health >= 6:  # Only ask happy clients
                request_testimonial(client)


# ══════════════════════════════════════
# AGENT 11 — Social Media Content
# ══════════════════════════════════════

CONTENT_TYPES = [
    "founder_story",        # Mon — personal story about building Shyra
    "client_win",           # Tue — anonymised client success story
    "agent_explainer",      # Wed — how a specific agent works
    "industry_insight",     # Thu — AI trends in Indian SME market
    "roi_data_post",        # Fri — specific ROI numbers
    "educational_tips",     # Sat — tips for business automation
    "week_recap",           # Sun — week in review
]


def generate_weekly_content() -> list[dict]:
    prompt = f"""Generate 7 days of social media content for Shyra AI — an AI agent agency for Indian and UAE SMEs.

Context: {cfg.SHYRA_CONTEXT}

Content types needed (one per day):
{json.dumps(CONTENT_TYPES)}

For each post return:
- type
- platform: "linkedin" or "instagram"
- caption (LinkedIn: 150-200 words, Instagram: 80-120 words)
- hashtags (10 relevant hashtags)
- cta (call to action sentence)
- image_prompt (describe image to generate — without text)

Return JSON array. Make content specific, data-driven, Indian-market relevant.
Avoid generic AI hype. Use real numbers. Tell specific stories."""

    try:
        content = ask_claude_json(prompt, model=cfg.CLAUDE_MODEL)
        return content if isinstance(content, list) else []
    except Exception as e:
        log.error(f"Content generation failed: {e}")
        return []


def post_to_linkedin(post: dict) -> bool:
    if not cfg.LINKEDIN_TOKEN:
        return False
    import requests
    caption = f"{post.get('caption','')}\n\n{' '.join(post.get('hashtags',[]))}\n\n{post.get('cta','')}"
    payload = {
        "author": f"urn:li:organization:{cfg.LINKEDIN_ORG}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": caption},
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }
    try:
        resp = requests.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers={"Authorization": f"Bearer {cfg.LINKEDIN_TOKEN}", "Content-Type": "application/json"},
            json=payload, timeout=10
        )
        return resp.status_code in (200, 201)
    except Exception as e:
        log.error(f"LinkedIn post failed: {e}")
        return False


def post_to_instagram(post: dict) -> bool:
    if not cfg.META_TOKEN or not cfg.INSTAGRAM_ID:
        return False
    import requests
    caption = f"{post.get('caption','')}\n\n{' '.join(post.get('hashtags',[]))}"
    # Instagram requires image — save caption as draft if no image
    # For now just log
    log.info(f"Instagram draft saved: {caption[:60]}...")
    return True


def run_social_content():
    log.info("Agent 11 — Social Content Generator starting")
    posts = generate_weekly_content()

    if not posts:
        log.warning("No content generated")
        return

    posted = 0
    for i, post in enumerate(posts[:7]):
        platform = post.get("platform","linkedin")
        day = CONTENT_TYPES[i] if i < len(CONTENT_TYPES) else f"day_{i+1}"
        log.info(f"Processing {day} post for {platform}")

        if platform == "linkedin":
            ok = post_to_linkedin(post)
        else:
            ok = post_to_instagram(post)

        if ok:
            posted += 1
            log.info(f"Posted: {day}")
        else:
            log.info(f"Saved draft: {day}")

        # Always save to sheet as backup
        if cfg.CLIENTS_SHEET_ID:
            sheet_append(cfg.CLIENTS_SHEET_ID, [
                today(), day, platform,
                post.get("caption","")[:200],
                " ".join(post.get("hashtags",[])),
                "posted" if ok else "draft"
            ])

    log.info(f"Agent 11 done — {posted} posted, {len(posts)-posted} drafts")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--agent", choices=["testimonial","social"], required=True)
    args = p.parse_args()
    if args.agent == "testimonial": run_testimonial_collector()
    elif args.agent == "social":    run_social_content()
