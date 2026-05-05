"""
AI NightShift SATX — Missed Call SMS Agent
Handles inbound calls and runs a Claude-powered SMS qualification conversation.
"""

import os
from flask import Flask, request, Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from twilio.twiml.messaging_response import MessagingResponse
import anthropic
import conversation_store

app = Flask(__name__)

# Clients
twilio_client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
TWILIO_FROM = os.environ["TWILIO_PHONE_NUMBER"]
OWNER_PHONE = os.environ.get("OWNER_PHONE", "+12108420614")
BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "AI NightShift SATX")
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://ainightshiftsatx.com")

SYSTEM_PROMPT = f"""You are a friendly, professional AI assistant for {BUSINESS_NAME}, a San Antonio-based business automation company.

Your job is to qualify leads via SMS after they missed a call to our business line.

CONVERSATION FLOW:
1. You already sent the opening text. Now respond to their reply.
2. Ask ONE question at a time — never multiple questions in one message.
3. Qualify by understanding: what kind of business they run, their biggest pain point, and if they want to book a free audit.
4. Keep messages SHORT — under 160 characters when possible. This is SMS.
5. Be warm and conversational, not robotic.
6. If they want to book or learn more, direct them to: {WEBSITE_URL}
7. If they seem uninterested or say stop/no thanks, politely end the conversation.
8. If they report an emergency or urgent issue, give them the owner's direct number: {OWNER_PHONE}

QUALIFICATION TARGETS:
- Small businesses under 20 employees
- Pain points: missed calls, no-shows, manual admin, slow follow-up
- Decision makers who can say yes to a free audit

RESPONSE FORMAT:
Return ONLY the SMS text to send. No quotes, no labels, no extra formatting.
Always end with a clear next step or question."""


@app.route("/call", methods=["POST"])
def handle_call():
    """Twilio hits this when someone calls the 855 number."""
    caller = request.form.get("From", "Unknown")
    
    # Play a greeting and hang up
   response = VoiceResponse()
        response.play("https://raw.githubusercontent.com/hefnerjm/ainightshift-sms-agent/main/greeting.mp3")
    )
    response.hangup()

    # Fire outbound SMS to the caller
    try:
        opening_message = (
            f"Hi! This is {BUSINESS_NAME}. Sorry we missed your call! "
            f"I'm an AI assistant — can I help you or connect you with our team? "
            f"What's your name and what brings you our way?"
        )
        twilio_client.messages.create(
            body=opening_message,
            from_=TWILIO_FROM,
            to=caller
        )
        # Initialize conversation
        conversation_store.set_stage(caller, "started")
        conversation_store.append_message(caller, "assistant", opening_message)
        print(f"[CALL] Missed call from {caller} — opening SMS sent")
    except Exception as e:
        print(f"[CALL ERROR] Could not send SMS to {caller}: {e}")

    return Response(str(response), mimetype="text/xml")


@app.route("/sms", methods=["POST"])
def handle_sms():
    """Twilio hits this when someone replies to our SMS."""
    caller = request.form.get("From", "Unknown")
    incoming_text = request.form.get("Body", "").strip()
    
    print(f"[SMS] From {caller}: {incoming_text}")

    # Opt-out handling
    if incoming_text.upper() in ["STOP", "UNSUBSCRIBE", "CANCEL", "QUIT", "END"]:
        conversation_store.clear(caller)
        return Response(str(MessagingResponse()), mimetype="text/xml")

    # Get or initialize conversation
    convo = conversation_store.get(caller)
    if not convo:
        # New conversation — they texted us directly without calling first
        conversation_store.set_stage(caller, "started")
        opening = (
            f"Hi! Thanks for reaching out to {BUSINESS_NAME}. "
            f"I'm an AI assistant. What's your name and how can we help?"
        )
        conversation_store.append_message(caller, "assistant", opening)
        convo = conversation_store.get(caller)

    # Add their message to history
    conversation_store.append_message(caller, "user", incoming_text)
    convo = conversation_store.get(caller)

    # Build messages for Claude
    messages = convo["history"]

    try:
        claude_response = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=messages
        )
        reply = claude_response.content[0].text.strip()
    except Exception as e:
        print(f"[CLAUDE ERROR] {e}")
        reply = f"Sorry, I had a technical hiccup! Please call us back or visit {WEBSITE_URL}"

    # Save Claude's reply to history
    conversation_store.append_message(caller, "assistant", reply)

    # Notify owner if Claude thinks this is a hot lead
    hot_keywords = ["book", "audit", "interested", "yes", "schedule", "call me", "when"]
    if any(kw in incoming_text.lower() for kw in hot_keywords):
        try:
            twilio_client.messages.create(
                body=f"[HOT LEAD] {caller} replied: \"{incoming_text}\"",
                from_=TWILIO_FROM,
                to=OWNER_PHONE
            )
        except Exception as e:
            print(f"[OWNER NOTIFY ERROR] {e}")

    print(f"[SMS] Replying to {caller}: {reply}")

    # Send reply via Twilio
    twilio_response = MessagingResponse()
    twilio_response.message(reply)
    return Response(str(twilio_response), mimetype="text/xml")


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "service": "ainightshift-sms-agent"}, 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
