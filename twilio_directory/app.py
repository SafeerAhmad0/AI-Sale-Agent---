from flask import Flask, request, Response
import logging
import os

app = Flask(__name__)
logger = logging.getLogger("TwilioWebhook")
logging.basicConfig(level=logging.INFO)

@app.route("/")
def home():
    return "✅ Flask server is running"

@app.route("/webhook", methods=["POST"])
def webhook():
    logger.info("📞 Incoming call webhook triggered")
    logger.info(f"Request data: {request.form.to_dict()}")

    twiml_response = """
    <Response>
        <Say>Hello, this is a test call from your Flask server!</Say>
    </Response>
    """
    return Response(twiml_response, mimetype="text/xml")

@app.route("/twilio/status", methods=["POST"])
def call_status():
    status = request.form.get("CallStatus")
    sid = request.form.get("CallSid")
    logger.info(f"📞 Call {sid} changed status to {status}")
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

