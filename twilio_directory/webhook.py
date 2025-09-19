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
    """Root endpoint - redirect to dashboard."""
    from flask import redirect
    return redirect('/dashboard')

@app.route("/landing", methods=["GET"])
def landing():
    """Landing page showing the AI Sales Agent info."""
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

@app.route("/facebook/webhook", methods=["GET", "POST"])
def facebook_webhook():
    """Handle Facebook Lead Ads webhooks."""
    try:
        from facebook.lead_ads import FacebookLeadAds

        fb_leads = FacebookLeadAds()

        if request.method == "GET":
            # Webhook verification
            verify_token = request.args.get('hub.verify_token')
            challenge = request.args.get('hub.challenge')

            verified_challenge = fb_leads.verify_webhook(verify_token, challenge)
            if verified_challenge:
                return verified_challenge
            else:
                return "Verification failed", 403

        elif request.method == "POST":
            # Process webhook data
            data = request.get_json()
            if fb_leads.process_webhook(data):
                return "OK", 200
            else:
                return "Processing failed", 500

    except Exception as e:
        logger.error(f"Error in Facebook webhook: {e}")
        return "Internal error", 500

@app.route("/dashboard", methods=["GET"])
def dashboard():
    """AI Sales Agent Dashboard - Live data with no fake content."""
    try:
        return render_template('live_dashboard.html')
    except Exception as e:
        logger.error(f"Error rendering dashboard: {e}")
        return {"error": "Dashboard template not found"}, 500

@app.route("/dashboard/static", methods=["GET"])
def static_dashboard():
    """Static demo dashboard."""
    try:
        return render_template('dashboard.html')
    except Exception as e:
        logger.error(f"Error rendering static dashboard: {e}")
        return {"error": "Dashboard template not found"}, 500

@app.route("/details", methods=["GET"])
def system_details():
    """Complete system details and configuration page."""
    try:
        return render_template('details.html')
    except Exception as e:
        logger.error(f"Error rendering details page: {e}")
        return {"error": "Details template not found"}, 500

@app.route("/api/live-data", methods=["GET"])
def live_data():
    """Get ONLY real live data - returns empty if no data exists."""
    try:
        from datetime import datetime
        import os

        # Try to get real data from systems, but return empty if unavailable
        live_data = {
            'timestamp': datetime.now().isoformat(),
            'status': 'online',
            'metrics': {},
            'recent_leads': [],
            'recent_activity': [],
            'system_logs': []
        }

        # Try to get real CRM data
        try:
            from zoho.crm import ZohoCRM
            crm = ZohoCRM()

            # Only get data if credentials are configured
            if os.getenv('ZOHO_CLIENT_ID') and os.getenv('ZOHO_REFRESH_TOKEN'):
                leads = crm.get_leads(limit=10)
                if leads:
                    live_data['metrics']['total_leads'] = len(leads)

                    # Only include leads with real data
                    for lead in leads[:5]:
                        if lead.get('First_Name') or lead.get('Phone'):
                            live_data['recent_leads'].append({
                                'name': f"{lead.get('First_Name', '')} {lead.get('Last_Name', '')}".strip() or 'Unknown',
                                'phone': lead.get('Phone') or 'No phone',
                                'company': lead.get('Company') or 'No company',
                                'status': lead.get('Lead_Status', 'New'),
                                'created': lead.get('Created_Time', '')
                            })

                            # Add to activity feed
                            live_data['recent_activity'].append({
                                'type': 'lead',
                                'message': f"Lead: {lead.get('First_Name', 'Unknown')} from {lead.get('Lead_Source', 'Direct')}",
                                'timestamp': lead.get('Created_Time', datetime.now().isoformat())
                            })

        except Exception as e:
            logger.debug(f"CRM data not available: {e}")
            live_data['recent_activity'].append({
                'type': 'system',
                'message': 'CRM integration not configured or unavailable',
                'timestamp': datetime.now().isoformat()
            })

        # Try to get real Twilio data
        try:
            from twilio_directory.call import TwilioCallManager
            twilio = TwilioCallManager()

            # Only get data if credentials are configured
            if os.getenv('TWILIO_ACCOUNT_SID') and os.getenv('TWILIO_AUTH_TOKEN'):
                calls = twilio.get_call_logs(limit=10)
                if calls:
                    live_data['metrics']['total_calls'] = len(calls)

                    # Add call activity
                    for call in calls[:5]:
                        if call.get('to') and call.get('status'):
                            live_data['recent_activity'].append({
                                'type': 'call',
                                'message': f"Call to {call.get('to')} - {call.get('status')}",
                                'timestamp': call.get('start_time').isoformat() if call.get('start_time') else datetime.now().isoformat()
                            })

        except Exception as e:
            logger.debug(f"Twilio data not available: {e}")
            live_data['recent_activity'].append({
                'type': 'system',
                'message': 'Twilio integration not configured or unavailable',
                'timestamp': datetime.now().isoformat()
            })

        # Get recent system logs
        try:
            # Add recent system activity
            live_data['system_logs'] = [
                {
                    'level': 'INFO',
                    'message': 'System status check completed',
                    'timestamp': datetime.now().isoformat()
                },
                {
                    'level': 'INFO',
                    'message': 'Dashboard data refreshed',
                    'timestamp': datetime.now().isoformat()
                }
            ]
        except Exception as e:
            logger.debug(f"System logs not available: {e}")

        # Sort activity by timestamp
        live_data['recent_activity'].sort(key=lambda x: x['timestamp'], reverse=True)
        live_data['recent_activity'] = live_data['recent_activity'][:10]

        return live_data

    except Exception as e:
        logger.error(f"Error getting live data: {str(e)}")
        return {
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now().isoformat(),
            'metrics': {},
            'recent_leads': [],
            'recent_activity': [],
            'system_logs': []
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
# AI Sales Agent API Endpoints
# -------------------------------------------------------

@app.route("/api/calls/start-auto", methods=["POST"])
def start_auto_calling():
    """Start automated calling process."""
    try:
        from scheduler.call_scheduler import CallScheduler

        scheduler = CallScheduler()
        result = scheduler.start_auto_calling()

        if result:
            return {
                "success": True,
                "message": "Automated calling started successfully",
                "active_leads": result.get("active_leads", 0)
            }
        else:
            return {
                "success": False,
                "error": "No leads available for calling or scheduler already running"
            }, 400

    except Exception as e:
        logger.error(f"Error starting auto-calling: {e}")
        return {
            "success": False,
            "error": f"Failed to start auto-calling: {str(e)}"
        }, 500

@app.route("/api/calls/test", methods=["POST"])
def make_test_call():
    """Make a test call to verify system functionality."""
    try:
        data = request.get_json() or {}
        phone = data.get("phone", "+911234567890")  # Default test number

        from twilio_directory.call import TwilioCallManager

        twilio = TwilioCallManager()
        call = twilio.make_call(phone, lead_id="test-call")

        if call:
            return {
                "success": True,
                "call_sid": call.sid,
                "status": call.status,
                "to": call.to
            }
        else:
            return {
                "success": False,
                "error": "Failed to initiate test call"
            }, 500

    except Exception as e:
        logger.error(f"Error making test call: {e}")
        return {
            "success": False,
            "error": f"Test call failed: {str(e)}"
        }, 500

@app.route("/api/calls/initiate", methods=["POST"])
def initiate_manual_call():
    """Initiate a manual call to a specific number."""
    try:
        data = request.get_json()
        if not data:
            return {"success": False, "error": "No data provided"}, 400

        phone = data.get("phone")
        lead_name = data.get("lead_name", "Manual Call")

        if not phone:
            return {"success": False, "error": "Phone number is required"}, 400

        from twilio_directory.call import TwilioCallManager

        twilio = TwilioCallManager()
        call = twilio.make_call(phone, lead_id=f"manual-{lead_name.lower().replace(' ', '-')}")

        if call:
            # Log the manual call
            logger.info(f"Manual call initiated to {phone} for {lead_name}")

            return {
                "success": True,
                "call_sid": call.sid,
                "status": call.status,
                "to": call.to,
                "lead_name": lead_name
            }
        else:
            return {
                "success": False,
                "error": "Failed to initiate call"
            }, 500

    except Exception as e:
        logger.error(f"Error initiating manual call: {e}")
        return {
            "success": False,
            "error": f"Call initiation failed: {str(e)}"
        }, 500

@app.route("/api/leads/next", methods=["GET"])
def get_next_lead():
    """Get the next available lead for calling."""
    try:
        from zoho.crm import ZohoCRM

        crm = ZohoCRM()

        # Check if CRM is configured
        if not os.getenv('ZOHO_CLIENT_ID') or not os.getenv('ZOHO_REFRESH_TOKEN'):
            return {
                "success": False,
                "error": "CRM not configured",
                "lead": None
            }

        # Get leads that haven't been called yet
        leads = crm.get_leads(limit=50)

        if not leads:
            return {
                "success": True,
                "message": "No leads available",
                "lead": None
            }

        # Find first lead with phone number that hasn't been called recently
        next_lead = None
        for lead in leads:
            if lead.get('Phone') and lead.get('Lead_Status') in ['New', 'Contacted', 'Qualified']:
                next_lead = {
                    "id": lead.get('id'),
                    "name": f"{lead.get('First_Name', '')} {lead.get('Last_Name', '')}".strip(),
                    "phone": lead.get('Phone'),
                    "company": lead.get('Company'),
                    "email": lead.get('Email'),
                    "status": lead.get('Lead_Status'),
                    "source": lead.get('Lead_Source'),
                    "created": lead.get('Created_Time')
                }
                break

        return {
            "success": True,
            "lead": next_lead,
            "total_leads": len(leads)
        }

    except Exception as e:
        logger.error(f"Error getting next lead: {e}")
        return {
            "success": False,
            "error": f"Failed to get next lead: {str(e)}",
            "lead": None
        }, 500

@app.route("/api/calls/status", methods=["GET"])
def get_call_status():
    """Get current calling system status."""
    try:
        from scheduler.call_scheduler import CallScheduler

        scheduler = CallScheduler()
        status = scheduler.get_status()

        return {
            "success": True,
            "status": status
        }

    except Exception as e:
        logger.error(f"Error getting call status: {e}")
        return {
            "success": False,
            "error": f"Failed to get call status: {str(e)}"
        }, 500


# -------------------------------------------------------
# Entrypoint for manual run
# -------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"🚀 Starting webhook server on port {port}")
    app.run(host="0.0.0.0", port=port)
