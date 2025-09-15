import os
from twilio.rest import Client
from twilio.base.exceptions import TwilioException
from utils.logger import logger


class TwilioCallManager:
    """Manages Twilio voice calls for the AI sales agent"""

    def __init__(self):
        logger.info("Initializing Twilio client...")

        self.account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.phone_number = os.getenv('TWILIO_PHONE_NUMBER')
        self.webhook_base_url = os.getenv('WEBHOOK_BASE_URL')

        logger.debug(f"Account SID: {self.account_sid}")
        logger.debug(f"Auth Token: {'*' * len(self.auth_token) if self.auth_token else None}")
        logger.debug(f"Phone Number (FROM): {self.phone_number}")
        logger.debug(f"Webhook Base URL: {self.webhook_base_url}")

        if not all([self.account_sid, self.auth_token, self.phone_number, self.webhook_base_url]):
            raise ValueError("❌ Missing required Twilio environment variables")

        self.client = Client(self.account_sid, self.auth_token)

    def test_connection(self):
        """Test Twilio connection by fetching account and verifying credentials."""
        try:
            logger.info("🔄 Testing Twilio connection...")

            # Fetch account details
            account = self.client.api.accounts(self.account_sid).fetch()
            logger.info(f"✅ Connected to Twilio account: {account.friendly_name}")

            # Verify phone numbers
            incoming_numbers = self.client.incoming_phone_numbers.list(limit=20)
            numbers = [num.phone_number for num in incoming_numbers]
            logger.info(f"📞 Incoming numbers on account: {numbers}")

            if self.phone_number not in numbers:
                logger.warning(
                    f"⚠️ Configured phone number {self.phone_number} "
                    f"is not listed among Twilio incoming numbers!"
                )

            return True
        except Exception as e:
            logger.exception(f"❌ Twilio connection test failed: {str(e)}")
            return False

    def initiate_call(self, lead_phone, lead_id, lead_name=""):
        """Initiate a voice call to a lead"""
        try:
            formatted_phone = self._format_phone_number(lead_phone)
            webhook_url = f"{self.webhook_base_url}/twilio/voice/{lead_id}"

            logger.info(f"📞 Initiating call to {lead_name} ({formatted_phone})")
            logger.debug(f"Webhook URL: {webhook_url}")

            call_params = {
                'to': formatted_phone,
                'from_': self.phone_number,
                'url': webhook_url,
                'method': 'POST',
                'status_callback': f"{self.webhook_base_url}/twilio/status",
                'status_callback_event': ['initiated', 'ringing', 'answered', 'completed'],
                'status_callback_method': 'POST',
                'record': True,
                'recording_status_callback': f"{self.webhook_base_url}/twilio/recording",
                'recording_status_callback_method': 'POST'
            }

            logger.debug(f"Call Params: {call_params}")

            call = self.client.calls.create(**call_params)

            logger.info(f"✅ Call initiated - Call SID: {call.sid}, Status: {call.status}")
            return {
                'call_sid': call.sid,
                'status': call.status,
                'to': formatted_phone,
                'lead_id': lead_id
            }

        except TwilioException as e:
            logger.error(f"❌ Twilio error initiating call to {lead_phone}: {str(e)}")
            return None
        except Exception as e:
            logger.exception(f"❌ Unexpected error initiating call to {lead_phone}: {str(e)}")
            return None

    def _format_phone_number(self, phone):
        """Format phone number for Twilio"""
        cleaned = ''.join(c for c in phone if c.isdigit() or c == '+')

        if not cleaned.startswith('+'):
            if cleaned.startswith('91') and len(cleaned) == 12:
                cleaned = '+' + cleaned
            elif cleaned.startswith('03') and len(cleaned) == 11:  # Pakistani number
                cleaned = '+92' + cleaned[1:]
            elif len(cleaned) == 10:  # Indian mobile number
                cleaned = '+91' + cleaned
            elif len(cleaned) == 11 and cleaned.startswith('0'):
                cleaned = '+92' + cleaned[1:]  # Assume Pakistani
            else:
                cleaned = '+' + cleaned

        logger.debug(f"Formatted phone number: {cleaned}")
        return cleaned

    def get_call_status(self, call_sid):
        """Get the current status of a call"""
        try:
            call = self.client.calls(call_sid).fetch()
            logger.info(f"📊 Call status for {call_sid}: {call.status}, Duration: {call.duration}")
            return {
                'sid': call.sid,
                'status': call.status,
                'duration': call.duration,
                'start_time': call.start_time,
                'end_time': call.end_time,
                'price': call.price,
                'price_unit': call.price_unit
            }
        except TwilioException as e:
            logger.error(f"❌ Failed to get call status for {call_sid}: {str(e)}")
            return None

    def end_call(self, call_sid):
        """End an active call"""
        try:
            call = self.client.calls(call_sid).update(status='completed')
            logger.info(f"✅ Ended call {call_sid}")
            return True
        except TwilioException as e:
            logger.error(f"❌ Failed to end call {call_sid}: {str(e)}")
            return False

    def get_call_logs(self, limit=50):
        """Get recent call logs"""
        try:
            calls = self.client.calls.list(limit=limit)
            logs = [
                {
                    'sid': call.sid,
                    'to': call.to,
                    'from_': call.from_formatted,
                    'status': call.status,
                    'start_time': call.start_time,
                    'duration': call.duration,
                    'price': call.price
                }
                for call in calls
            ]
            logger.info(f"📑 Retrieved {len(logs)} recent call logs")
            return logs
        except TwilioException as e:
            logger.error(f"❌ Failed to get call logs: {str(e)}")
            return []
