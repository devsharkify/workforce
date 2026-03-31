"""
AGENT 16 — Knowledge Distiller
================================
Weekly: reads all saved conversations, extracts patterns,
updates the knowledge base that the chat agent reads from.

This is how Shyra's chat agent gets smarter over time.

Every week it learns:
- What questions prospects ask most
- Which answers lead to bookings
- Which industries/cities convert best
- What objections come up and how to handle them
- What phrases, tones, triggers lead to phone number shared

The KB is injected into the chat agent's system prompt on every conversation.
"""
import logging
from datetime import datetime, timedelta
from core.config import cfg
from core.utils import ask_claude, ask_claude_json, sheet_read, sheet_append, get_sheet, ts, today

log = logging.getLogger("shyra.agent16")

CONVO_SHEET_TAB = "Conversations"
KB_SHEET_TAB = "KnowledgeBase"


def load_recent_conversations(days: int = 7) -> list[dict]:
    """Load conversations from the last N days."""
    try:
        rows = sheet_read(cfg.LEADS_SHEET_ID, CONVO_SHEET_TAB)
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        recent = [r for r in rows if r.get("Date", "") >= cutoff]
        log.info(f"Loaded {len(recent)} conversations (last {days} days)")
        return recent
    except Exception as e:
        log.error(f"Failed to load conversations: {e}")
        return []


def distill_knowledge(conversations: list[dict]) -> dict:
    """Claude reads all conversations and extracts learnings."""
    if not conversations:
        return {}

    # Build a digest of conversations for Claude
    digest = []
    for i, c in enumerate(conversations[:50]):  # Max 50 convos per run
        outcome = c.get("Outcome", "unknown")
        industry = c.get("Industry", "")
        city = c.get("City", "")
        turns = int(c.get("Turns", 0) or 0)
        phone_shared = c.get("PhoneShared", "no")
        summary = c.get("Summary", "")[:200]
        digest.append(f"[{i+1}] outcome={outcome} industry={industry} city={city} turns={turns} phone={phone_shared}\n{summary}")

    digest_text = "\n\n".join(digest)

    prompt = f"""You are analysing {len(conversations)} chat conversations from Shyra AI's website chatbot.
Shyra AI sells AI agents to Indian/UAE SMEs. ₹20,000 setup + ₹2,000/month.

CONVERSATIONS:
{digest_text}

Extract actionable intelligence to make the chat agent smarter.

Return JSON (be specific and data-driven, not generic):
{{
  "top_questions": ["top 5 questions prospects ask most"],
  "best_opening_responses": ["2-3 specific first replies that lead to conversions"],
  "industries_that_convert": ["top 3 industries with highest booking rate"],
  "industries_that_ghost": ["top 2 industries that engage but never book"],
  "cities_converting": ["cities showing highest conversion"],
  "common_objections": [
    {{"objection": "...", "best_rebuttal": "..."}}
  ],
  "triggers_that_get_phone": ["specific phrases/moves that lead to phone number shared"],
  "drop_off_points": ["where conversations typically die"],
  "optimal_convo_length": "X-Y exchanges for best conversion",
  "price_objection_handling": "best response to price concerns based on data",
  "language_insights": "observations on Hindi/Telugu/English mix",
  "time_patterns": "best times of day / days of week",
  "system_prompt_additions": "2-3 specific instructions to add to the chat agent system prompt based on learnings"
}}"""

    try:
        kb = ask_claude_json(prompt)
        log.info("Knowledge distilled successfully")
        return kb
    except Exception as e:
        log.error(f"Knowledge distillation failed: {e}")
        return {}


def save_knowledge_base(kb: dict):
    """Save distilled knowledge to Sheets KB tab."""
    try:
        ws = get_sheet(cfg.LEADS_SHEET_ID, KB_SHEET_TAB)
        # Clear and rewrite
        ws.clear()
        ws.append_row(["Key", "Value", "Updated"])
        for key, value in kb.items():
            if isinstance(value, list):
                val_str = " | ".join(
                    f"{v.get('objection','')}: {v.get('best_rebuttal','')}"
                    if isinstance(v, dict) else str(v)
                    for v in value
                )
            else:
                val_str = str(value)
            ws.append_row([key, val_str[:500], ts()])
        log.info(f"Knowledge base saved — {len(kb)} entries")
    except Exception as e:
        log.error(f"KB save failed: {e}")


def load_knowledge_base() -> str:
    """
    Load KB and format as a system prompt injection.
    Called by the chat agent on every conversation start.
    """
    try:
        rows = sheet_read(cfg.LEADS_SHEET_ID, KB_SHEET_TAB)
        if not rows:
            return ""

        kb_lines = ["LEARNINGS FROM PAST CONVERSATIONS (use to improve responses):"]
        key_map = {
            "top_questions":           "Top questions prospects ask",
            "best_opening_responses":  "Best opening responses",
            "industries_that_convert": "Industries that convert best",
            "common_objections":       "Common objections + rebuttals",
            "triggers_that_get_phone": "What gets them to share phone",
            "drop_off_points":         "Where conversations drop off",
            "optimal_convo_length":    "Optimal conversation length",
            "price_objection_handling":"Handling price objections",
            "language_insights":       "Language/tone insights",
            "system_prompt_additions": "IMPORTANT additional instructions",
        }
        for row in rows:
            key = row.get("Key", "")
            val = row.get("Value", "")
            if key in key_map and val:
                kb_lines.append(f"• {key_map[key]}: {val}")

        return "\n".join(kb_lines)
    except Exception as e:
        log.warning(f"KB load failed (using base prompt): {e}")
        return ""


def save_conversation(
    session_id: str,
    summary: str,
    industry: str,
    city: str,
    turns: int,
    phone_shared: bool,
    outcome: str,  # 'booked', 'lead', 'ghosted', 'browsing'
    notable_exchanges: str = ""
):
    """
    Called by the chat API after each completed conversation.
    Saves to Sheets for future distillation.
    """
    try:
        sheet_append(cfg.LEADS_SHEET_ID, [
            session_id, today(), industry, city,
            turns, "yes" if phone_shared else "no",
            outcome, summary[:300], notable_exchanges[:200],
        ], CONVO_SHEET_TAB)
    except Exception as e:
        log.warning(f"Conversation save failed: {e}")


def run():
    log.info("Agent 16 — Knowledge Distiller starting")

    convos = load_recent_conversations(days=7)
    if len(convos) < 5:
        log.info(f"Only {len(convos)} conversations — need at least 5 to distill. Skipping.")
        return

    kb = distill_knowledge(convos)
    if not kb:
        return

    save_knowledge_base(kb)

    # Log summary to console
    log.info("=== Knowledge Base Updated ===")
    for key, val in kb.items():
        preview = str(val)[:80] if not isinstance(val, list) else str(val[0])[:80]
        log.info(f"  {key}: {preview}")

    log.info(f"Agent 16 done — KB updated from {len(convos)} conversations")


if __name__ == "__main__":
    run()
