"""
AGENT 01 — Lead Scraper
========================
Daily 7 AM: Scrapes Google Maps for SME leads in target cities.
Scores each lead with Claude. Saves to Sheets.
"""
import requests
import logging
import time
from core.config import cfg
from core.utils import ask_claude_json, sheet_append, sheet_read, today

log = logging.getLogger("shyra.agent01")

TARGETS = [
    # (city, business_type, search_query)
    ("Hyderabad", "pharmacy",      "medical store Hyderabad"),
    ("Hyderabad", "clinic",        "clinic doctor Hyderabad"),
    ("Hyderabad", "restaurant",    "restaurant Hyderabad"),
    ("Hyderabad", "real_estate",   "real estate agent Hyderabad"),
    ("Hyderabad", "ca_firm",       "CA chartered accountant Hyderabad"),
    ("Hyderabad", "logistics",     "courier logistics Hyderabad"),
    ("Hyderabad", "coaching",      "coaching institute Hyderabad"),
    ("Hyderabad", "retail",        "supermarket kirana Hyderabad"),
    ("Hyderabad", "construction",  "construction builder Hyderabad"),
    ("Mumbai",    "restaurant",    "restaurant Mumbai"),
    ("Bangalore", "clinic",        "clinic doctor Bangalore"),
    ("Dubai",     "restaurant",    "Indian restaurant Dubai"),
]

DAILY_LIMIT = 30  # leads per run


def scrape_google_maps(query: str, limit: int = 5) -> list[dict]:
    """Call Google Places API."""
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": cfg.MAPS_API_KEY}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results", [])[:limit]
        leads = []
        for r in results:
            leads.append({
                "name": r.get("name", ""),
                "address": r.get("formatted_address", ""),
                "rating": r.get("rating", 0),
                "reviews": r.get("user_ratings_total", 0),
                "place_id": r.get("place_id", ""),
                "types": ", ".join(r.get("types", [])[:3]),
            })
        return leads
    except Exception as e:
        log.error(f"Maps scrape failed for '{query}': {e}")
        return []


def get_place_details(place_id: str) -> dict:
    """Get phone number from Place Details API."""
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {"place_id": place_id, "fields": "formatted_phone_number,website", "key": cfg.MAPS_API_KEY}
    try:
        resp = requests.get(url, params=params, timeout=8)
        data = resp.json().get("result", {})
        return {
            "phone": data.get("formatted_phone_number", ""),
            "website": data.get("website", ""),
        }
    except Exception:
        return {"phone": "", "website": ""}


def score_lead(lead: dict, biz_type: str) -> dict:
    """Claude scores and enriches each lead."""
    prompt = f"""Business lead to score for AI agent sales:

Name: {lead['name']}
Type: {biz_type}
Address: {lead['address']}
Rating: {lead['rating']} ({lead['reviews']} reviews)

Score this lead for Shyra AI WhatsApp agent sales:
1-10 score based on: size (more reviews = bigger), AI readiness, affordability

Return JSON only:
{{"score": 1-10, "priority": "hot/warm/cold", "pain_hypothesis": "one sentence", "suggested_agent": "agent name", "opening_line": "personalized first WhatsApp message (2 sentences, mention their business name)"}}"""

    try:
        return ask_claude_json(prompt)
    except Exception:
        return {"score": 5, "priority": "warm", "pain_hypothesis": "Manual customer handling", "suggested_agent": "WhatsApp Support Agent", "opening_line": f"Hi! I came across {lead['name']} — would you be open to seeing how AI can save 3+ hours daily?"}


def load_existing_leads() -> set:
    """Get names already in sheet to avoid duplicates."""
    try:
        rows = sheet_read(cfg.LEADS_SHEET_ID)
        return {r.get("Business Name", "").lower() for r in rows if r.get("Business Name")}
    except Exception:
        return set()


def run():
    log.info("Agent 01 — Lead Scraper starting")
    if not cfg.MAPS_API_KEY:
        log.warning("No Google Maps API key — skipping scrape")
        return

    existing = load_existing_leads()
    count = 0

    for city, biz_type, query in TARGETS:
        if count >= DAILY_LIMIT:
            break
        log.info(f"Scraping: {query}")
        leads = scrape_google_maps(query, limit=5)

        for lead in leads:
            if count >= DAILY_LIMIT:
                break
            name_lower = lead["name"].lower()
            if name_lower in existing:
                log.debug(f"Skip duplicate: {lead['name']}")
                continue

            # Get contact details
            details = get_place_details(lead["place_id"])
            lead.update(details)

            # Score
            scored = score_lead(lead, biz_type)
            existing.add(name_lower)

            # Save to sheet
            sheet_append(cfg.LEADS_SHEET_ID, [
                lead["name"],           # Business Name
                biz_type,               # Type
                city,                   # City
                lead["address"],        # Address
                lead["phone"],          # Phone
                lead["website"],        # Website
                lead["rating"],         # Rating
                lead["reviews"],        # Reviews
                scored.get("score"),    # AI Score
                scored.get("priority"), # Priority
                scored.get("pain_hypothesis"),  # Pain
                scored.get("suggested_agent"),  # Suggested Agent
                scored.get("opening_line"),     # Opening Line
                today(),                # Date Scraped
                "new",                  # Status
                "",                     # Last Contacted
            ])
            count += 1
            log.info(f"Lead saved: {lead['name']} ({scored.get('priority')}) score={scored.get('score')}")
            time.sleep(0.3)  # rate limit

    log.info(f"Agent 01 done — {count} leads saved")


if __name__ == "__main__":
    run()
