"""
SHYRA + ELEVENLABS — Custom LLM Endpoint
==========================================
ElevenLabs Agents handles:
  - STT: their fine-tuned ASR (much better than browser, handles Indian accents)
  - TTS: 5,000+ voices, low-latency streaming, Indian English voice
  - Turn-taking: their proprietary model handles interruptions naturally

We provide:
  - The LLM: Claude Haiku via this endpoint
  - The intelligence: full Shyra sales conversation system prompt

ElevenLabs calls POST /elevenlabs/llm on every conversation turn.

Setup in ElevenLabs dashboard:
  1. Create agent → Agent tab → LLM → Custom LLM
  2. URL: https://api.shyra.pro/elevenlabs/llm
  3. Voice: "Aria" or "Priya" (Indian English, warm female)
  4. First message: "Hi! I'm Shyra's AI. Tell me about your business."
  5. System prompt: leave blank (our endpoint sends it)
"""

from flask import request, jsonify, Response, stream_with_context
import anthropic
import json
from core.config import cfg
from core.utils import log

# ElevenLabs expects this system prompt format for custom LLM
ELEVENLABS_SHYRA_SYSTEM = """You are Shyra — an intelligent AI sales agent speaking on behalf of shyra.pro. You are in a VOICE conversation, not a text chat.

SHYRA AI: Custom AI agents for Indian and UAE businesses.
Setup ₹20,000 · Monthly ₹2,000/agent · Live in 7 days · Payback 30-45 days.

VOICE RULES (critical — you are speaking, not typing):
- Keep every reply to 1-3 SHORT sentences. Voice is slower than text.
- No bullet points, no lists, no markdown — this is speech
- Natural pauses: use commas and periods to create breathing room
- Numbers spoken: say "twenty thousand rupees" not "₹20,000"
- Ask ONE question per turn. Never two.

CONVERSATION GOAL:
Have a warm, intelligent conversation. Understand their business. Recommend the right agent. Get their WhatsApp number.

WHAT YOU'RE LEARNING (through natural conversation):
- What business they run (pick up from how they speak)
- Their main problem
- How many WhatsApp messages they get daily
- Their website (ask around turn 4-5)
- Urgency

AGENTS YOU KNOW:
WhatsApp Order Assistant, Lead Qualifier, Appointment Booking, Invoice OCR to Tally, Payment Reminder, Chit Fund Manager, RERA Compliance, Delivery Tracking, and 45 more.

WHEN TO RECOMMEND:
After 4-5 exchanges. Be specific: "For a pharmacy handling 80 orders daily, the WhatsApp Order Assistant saves your team about 3 hours every day."

WHEN TO ASK FOR NUMBER:
After they show interest. Say: "What's your WhatsApp number? I'll send you a summary and a link to book a free call."

NEVER:
- Say "Great question" or "Certainly" — sounds robotic when spoken
- Give long answers — voice conversations need to be concise
- Use rupee symbol — say "rupees" instead
- Mention competitor names"""


def register_elevenlabs_routes(app):
    """Register ElevenLabs routes on the Flask app."""

    @app.route("/elevenlabs/llm", methods=["POST"])
    def elevenlabs_llm():
        """
        ElevenLabs Custom LLM endpoint.
        Receives conversation history, returns Claude's response.
        Supports both streaming and non-streaming.
        """
        data = request.json or {}

        # ElevenLabs sends messages in OpenAI format
        messages = data.get("messages", [])

        # Filter to only user/assistant messages (skip system)
        convo = [m for m in messages if m.get("role") in ("user", "assistant")]

        if not convo:
            return jsonify({"content": "Hi! Tell me about your business.", "role": "assistant"}), 200

        # Load knowledge base if available
        kb_injection = ""
        try:
            from agents.agent16 import load_knowledge_base
            kb_injection = load_knowledge_base()
        except Exception:
            pass

        system = ELEVENLABS_SHYRA_SYSTEM
        if kb_injection:
            system += f"\n\nLEARNINGS FROM PAST CONVERSATIONS:\n{kb_injection}"

        # Check if ElevenLabs wants streaming
        stream = data.get("stream", False)

        try:
            client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)

            if stream:
                # Streaming response (lower latency for voice)
                def generate():
                    with client.messages.stream(
                        model=cfg.CLAUDE_MODEL_FAST,
                        max_tokens=150,  # Keep voice replies short
                        system=system,
                        messages=convo
                    ) as stream_obj:
                        for text in stream_obj.text_stream:
                            # ElevenLabs expects SSE format for streaming
                            chunk = json.dumps({"content": text, "role": "assistant"})
                            yield f"data: {chunk}\n\n"
                    yield "data: [DONE]\n\n"

                return Response(
                    stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no"
                    }
                )
            else:
                # Non-streaming
                resp = client.messages.create(
                    model=cfg.CLAUDE_MODEL_FAST,
                    max_tokens=150,
                    system=system,
                    messages=convo
                )
                reply = resp.content[0].text.strip()
                log.info(f"ElevenLabs LLM reply: {reply[:60]}...")
                return jsonify({
                    "content": reply,
                    "role": "assistant"
                }), 200

        except Exception as e:
            log.error(f"ElevenLabs LLM error: {e}")
            return jsonify({
                "content": "I'd love to help. Could you tell me a bit about your business?",
                "role": "assistant"
            }), 200


    @app.route("/elevenlabs/agent-config", methods=["GET"])
    def elevenlabs_agent_config():
        """
        Returns agent configuration.
        Optional — ElevenLabs can also read this from their dashboard.
        """
        return jsonify({
            "agent_name": "Shyra AI",
            "voice": "Aria",  # Indian English female voice
            "language": "en",
            "first_message": "Hi! I'm Shyra's AI. Tell me about your business — what do you do?",
            "system_prompt": ELEVENLABS_SHYRA_SYSTEM,
            "max_duration_seconds": 600,
            "turn_timeout": 7,
        }), 200


    @app.route("/elevenlabs/post-call", methods=["POST"])
    def elevenlabs_post_call():
        """
        ElevenLabs calls this after each conversation ends (post-call webhook).
        Verifies webhook signature using ELEVENLABS_WEBHOOK_SECRET.
        """
        import hmac, hashlib, time

        secret = os.getenv("ELEVENLABS_WEBHOOK_SECRET", "")
        if secret:
            sig_header = request.headers.get("ElevenLabs-Signature", "")
            # ElevenLabs signature format: t=timestamp,v1=hash
            try:
                parts = dict(p.split("=", 1) for p in sig_header.split(","))
                ts = parts.get("t", "")
                sig = parts.get("v1", "")
                # Reject if timestamp > 5 minutes old
                if abs(time.time() - float(ts)) > 300:
                    return jsonify({"error": "Timestamp expired"}), 401
                payload = f"{ts}.{request.get_data(as_text=True)}"
                expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(expected, sig):
                    return jsonify({"error": "Invalid signature"}), 401
            except Exception as e:
                log.warning(f"Webhook signature check failed: {e}")
                return jsonify({"error": "Signature verification failed"}), 401

        data = request.json or {}

        conversation_id = data.get("conversation_id", "")
        transcript = data.get("transcript", [])
        metadata = data.get("metadata", {})
        analysis = data.get("analysis", {})

        if not transcript:
            return jsonify({"status": "ok"}), 200

        # Build conversation text for Claude analysis
        convo_text = "\n".join([
            f"{m.get('role','').upper()}: {m.get('message','')}"
            for m in transcript
            if m.get("message")
        ])

        log.info(f"ElevenLabs post-call: {conversation_id}, {len(transcript)} turns")

        # Claude extracts lead info from the voice conversation
        try:
            from core.utils import ask_claude_json, send_whatsapp_safe, notify_sales, sheet_append
            from core.config import cfg
            from core.utils import ts

            extract = ask_claude_json(f"""Extract lead info from this voice conversation transcript:

{convo_text[:2000]}

Return JSON:
{{"name":"","business":"","type":"","city":"","phone":"","pain":"","agent_recommended":"","interest_level":"hot/warm/cold","booked_call":true/false,"summary":"2 sentences"}}
""")

            # Save to leads sheet
            if cfg.LEADS_SHEET_ID:
                sheet_append(cfg.LEADS_SHEET_ID, [
                    extract.get("name",""),
                    extract.get("business",""),
                    extract.get("type",""),
                    extract.get("city",""),
                    extract.get("phone",""),
                    "",  # email
                    extract.get("pain","")[:120],
                    "",  # volume
                    "",  # score
                    extract.get("interest_level",""),
                    extract.get("agent_recommended",""),
                    extract.get("summary",""),
                    ts(),
                    "elevenlabs_voice",
                    "new"
                ])

            # Alert sales if hot
            if extract.get("interest_level") == "hot" or extract.get("booked_call"):
                phone = extract.get("phone","")
                notify_sales(f"""*Hot Voice Lead* 🎤

Name: {extract.get('name','')}
Business: {extract.get('business','')}
Phone: {phone}
Pain: {extract.get('pain','')}
Rec: {extract.get('agent_recommended','')}
Booked: {'Yes ✅' if extract.get('booked_call') else 'No'}

Transcript ID: {conversation_id}""")

            # Save for Agent 16 learning
            try:
                from agents.agent16 import save_conversation
                save_conversation(
                    session_id=conversation_id,
                    summary=extract.get("summary",""),
                    industry=extract.get("type",""),
                    city=extract.get("city",""),
                    turns=len(transcript),
                    phone_shared=bool(extract.get("phone")),
                    outcome="booked" if extract.get("booked_call") else extract.get("interest_level","browsing")
                )
            except Exception:
                pass

        except Exception as e:
            log.error(f"Post-call processing error: {e}")

        return jsonify({"status": "ok"}), 200
