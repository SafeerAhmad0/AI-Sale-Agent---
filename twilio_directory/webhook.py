import os
import logging
from flask import Flask, request, Response, render_template
from twilio.twiml.voice_response import VoiceResponse, Gather

# -------------------------------------------------------
# Logging setup
# -------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("TwilioWebhook")

# -------------------------------------------------------
# Flask app
# -------------------------------------------------------
app = Flask(__name__)

# Get base URL from environment (.env should have WEBHOOK_BASE_URL=https://xxx.ngrok-free.app/outbound)
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL")
if not WEBHOOK_BASE_URL:
    logger.error("❌ WEBHOOK_BASE_URL not set in environment!")
else:
    logger.info(f"✅ Using WEBHOOK_BASE_URL = {WEBHOOK_BASE_URL}")


# -------------------------------------------------------
# Helper to send TwiML safely
# -------------------------------------------------------
def twiml_response(response: VoiceResponse):
    xml_str = str(response)
    logger.debug(f"📡 Returning TwiML:\n{xml_str}")
    return Response(xml_str, mimetype="application/xml")


# -------------------------------------------------------
# Routes
# -------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    """Root endpoint showing the AI Sales Agent landing page."""
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering template: {e}")
        # Fallback to JSON response
        return {
            "status": "running",
            "service": "AI Sales Agent Webhook",
            "endpoints": [
                "/twilio/voice/<lead_id>",
                "/twilio/gather",
                "/twilio/status",
                "/twilio/recording"
            ]
        }

@app.route("/api/status", methods=["GET"])
def api_status():
    """API endpoint to check system status."""
    return {
        "status": "running",
        "service": "AI Voice Sales Agent",
        "version": "1.0.0",
        "components": {
            "webhook_server": "online",
            "twilio_integration": "configured",
            "openai_integration": "configured",
            "zoho_crm_integration": "configured"
        },
        "endpoints": {
            "webhook": "/twilio/voice/<lead_id>",
            "gather": "/twilio/gather",
            "status_callback": "/twilio/status",
            "recording_callback": "/twilio/recording"
        },
        "features": [
            "Hindi voice calls",
            "AI-powered lead qualification",
            "CRM integration",
            "Automated calling",
            "Conversation logging"
        ]
    }

@app.route("/test", methods=["GET"])
def test_endpoint():
    """Test endpoint for health checks."""
    return {
        "message": "AI Voice Sales Agent is working correctly!",
        "timestamp": "2025-09-17T14:55:32Z",
        "status": "healthy"
    }

@app.route("/twilio/voice/<lead_id>", methods=["POST"])
def handle_voice(lead_id):
    """Initial handler when call connects."""
    try:
        logger.info(f"📞 Incoming call for lead {lead_id}")
        logger.debug(f"Request form: {request.form}")

        vr = VoiceResponse()
        gather = Gather(
            input="speech dtmf",
            action=f"{WEBHOOK_BASE_URL}/twilio/gather?lead_id={lead_id}",
            method="POST",
            timeout=5,
        )
        gather.say("Hello! This is your AI sales agent. Can you hear me clearly?")
        vr.append(gather)

        # If no input, continue
        vr.say("We didn’t get your response. Goodbye!")
        vr.hangup()

        return twiml_response(vr)

    except Exception as e:
        logger.exception(f"❌ Error in /twilio/voice/{lead_id}: {e}")
        vr = VoiceResponse()
        vr.say("Sorry, an internal error occurred.")
        vr.hangup()
        return twiml_response(vr)


@app.route("/twilio/gather", methods=["POST"])
def handle_gather():
    """Handles speech or keypad input from user."""
    try:
        lead_id = request.args.get("lead_id")
        logger.info(f"🎤 Gather response for lead {lead_id}")
        logger.debug(f"Request form: {request.form}")

        user_input = request.form.get("SpeechResult") or request.form.get("Digits")
        logger.info(f"👉 User input: {user_input}")

        vr = VoiceResponse()
        if user_input:
            vr.say(f"You said {user_input}. Thank you for your response.")
        else:
            vr.say("We didn’t catch that. Goodbye.")
        vr.hangup()

        return twiml_response(vr)

    except Exception as e:
        logger.exception(f"❌ Error in /twilio/gather: {e}")
        vr = VoiceResponse()
        vr.say("Sorry, an internal error occurred.")
        vr.hangup()
        return twiml_response(vr)



@app.route("/twilio/status", methods=["POST"])
def call_status():
    status = request.form.get("CallStatus")
    sid = request.form.get("CallSid")
    logger.info(f"📞 Call {sid} changed status to {status}")
    return "OK", 200


@app.route("/twilio/recording", methods=["POST"])
def handle_recording():
    """Receives call recording events."""
    logger.info(f"🎙️ Recording event: {request.form.to_dict()}")
    return ("", 204)


# -------------------------------------------------------
# Entrypoint for manual run
# -------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"🚀 Starting webhook server on port {port}")
    app.run(host="0.0.0.0", port=port)
