import os
import time
import threading
from datetime import datetime, timedelta
from queue import Queue, PriorityQueue
from dataclasses import dataclass
from typing import Optional, Dict, Any
from utils.logger import logger

@dataclass
class ScheduledCall:
    """Represents a scheduled call"""
    priority: int
    scheduled_time: datetime
    lead_id: str
    lead_data: Dict[Any, Any]
    attempt_number: int = 1
    max_attempts: int = 3

    def __lt__(self, other):
        return self.scheduled_time < other.scheduled_time

class CallScheduler:
    """Manages automatic call scheduling and retry logic"""

    def __init__(self):
        self.call_queue = PriorityQueue()
        self.active_calls = {}
        self.completed_calls = {}
        self.failed_calls = {}

        self.is_running = False
        self.scheduler_thread = None

        # Configuration
        self.calling_hours_start = int(os.getenv('CALLING_HOURS_START', '9'))  # 9 AM
        self.calling_hours_end = int(os.getenv('CALLING_HOURS_END', '19'))    # 7 PM
        self.retry_delay_minutes = int(os.getenv('RETRY_DELAY_MINUTES', '240'))  # 4 hours
        self.call_interval_minutes = int(os.getenv('CALL_INTERVAL_MINUTES', '5'))  # 5 minutes between calls
        self.max_concurrent_calls = int(os.getenv('MAX_CONCURRENT_CALLS', '1'))

    def start_scheduler(self):
        """Start the call scheduler"""
        if not self.is_running:
            self.is_running = True
            self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self.scheduler_thread.start()
            logger.info("📅 Call scheduler started")

    def stop_scheduler(self):
        """Stop the call scheduler"""
        self.is_running = False
        if self.scheduler_thread:
            self.scheduler_thread.join()
        logger.info("📅 Call scheduler stopped")

    def schedule_immediate_call(self, lead_id: str, lead_data: Dict[Any, Any]) -> bool:
        """Schedule an immediate call for a new lead"""
        try:
            if not self._is_calling_hours():
                # Schedule for next business hours
                next_call_time = self._get_next_calling_time()
                logger.info(f"Outside calling hours, scheduling call for {next_call_time}")
            else:
                # Schedule immediately with small delay
                next_call_time = datetime.now() + timedelta(minutes=2)

            scheduled_call = ScheduledCall(
                priority=1,  # High priority for new leads
                scheduled_time=next_call_time,
                lead_id=lead_id,
                lead_data=lead_data,
                attempt_number=1
            )

            self.call_queue.put((scheduled_call.priority, scheduled_call.scheduled_time, scheduled_call))
            logger.info(f"📞 Call scheduled for lead {lead_id} at {next_call_time}")

            return True

        except Exception as e:
            logger.error(f"Error scheduling immediate call for lead {lead_id}: {str(e)}")
            return False

    def schedule_retry_call(self, lead_id: str, lead_data: Dict[Any, Any], attempt_number: int) -> bool:
        """Schedule a retry call for a failed attempt"""
        try:
            if attempt_number >= 3:  # Max retry attempts
                logger.info(f"Max retry attempts reached for lead {lead_id}, moving to failed queue")
                self.failed_calls[lead_id] = {
                    'lead_data': lead_data,
                    'final_attempt': attempt_number,
                    'failed_time': datetime.now()
                }
                return False

            # Calculate retry time
            retry_time = datetime.now() + timedelta(minutes=self.retry_delay_minutes)

            # Ensure retry is during calling hours
            if not self._is_time_in_calling_hours(retry_time):
                retry_time = self._get_next_calling_time()

            scheduled_call = ScheduledCall(
                priority=2,  # Lower priority for retries
                scheduled_time=retry_time,
                lead_id=lead_id,
                lead_data=lead_data,
                attempt_number=attempt_number + 1
            )

            self.call_queue.put((scheduled_call.priority, scheduled_call.scheduled_time, scheduled_call))
            logger.info(f"🔄 Retry call scheduled for lead {lead_id} at {retry_time} (attempt {attempt_number + 1})")

            return True

        except Exception as e:
            logger.error(f"Error scheduling retry call for lead {lead_id}: {str(e)}")
            return False

    def _scheduler_loop(self):
        """Main scheduler loop"""
        logger.info("📅 Scheduler loop started")

        while self.is_running:
            try:
                current_time = datetime.now()

                # Check if we're in calling hours
                if not self._is_calling_hours():
                    logger.debug("Outside calling hours, sleeping...")
                    time.sleep(300)  # Check every 5 minutes
                    continue

                # Check if we can make more calls
                if len(self.active_calls) >= self.max_concurrent_calls:
                    logger.debug("Max concurrent calls reached, waiting...")
                    time.sleep(60)  # Check every minute
                    continue

                # Check for scheduled calls
                if not self.call_queue.empty():
                    priority, scheduled_time, scheduled_call = self.call_queue.get()

                    if scheduled_time <= current_time:
                        # Time to make the call
                        self._initiate_call(scheduled_call)
                    else:
                        # Put it back in queue if not time yet
                        self.call_queue.put((priority, scheduled_time, scheduled_call))

                time.sleep(30)  # Check every 30 seconds

            except Exception as e:
                logger.error(f"Error in scheduler loop: {str(e)}")
                time.sleep(60)

    def _initiate_call(self, scheduled_call: ScheduledCall):
        """Initiate a call for a scheduled lead"""
        try:
            lead_id = scheduled_call.lead_id
            lead_data = scheduled_call.lead_data
            attempt_number = scheduled_call.attempt_number

            logger.info(f"📞 Initiating call for lead {lead_id} (attempt {attempt_number})")

            # Import here to avoid circular imports
            from twilio_directory.call import TwilioCallManager

            # Mark as active call
            self.active_calls[lead_id] = {
                'scheduled_call': scheduled_call,
                'start_time': datetime.now(),
                'status': 'initiating'
            }

            # Initiate the call
            twilio = TwilioCallManager()
            phone = lead_data.get('Phone')
            name = f"{lead_data.get('First_Name', '')} {lead_data.get('Last_Name', '')}".strip()

            if not phone:
                logger.error(f"No phone number for lead {lead_id}")
                self._handle_call_failure(lead_id, 'no_phone')
                return

            call_result = twilio.initiate_call(phone, lead_id, name)

            if call_result:
                logger.info(f"✅ Call initiated successfully for lead {lead_id}")
                self.active_calls[lead_id]['status'] = 'calling'
                self.active_calls[lead_id]['call_sid'] = call_result['call_sid']

                # Update CRM with call attempt
                self._update_crm_call_status(lead_id, 'Call Initiated', attempt_number)

            else:
                logger.error(f"❌ Failed to initiate call for lead {lead_id}")
                self._handle_call_failure(lead_id, 'initiation_failed')

        except Exception as e:
            logger.error(f"Error initiating call for lead {scheduled_call.lead_id}: {str(e)}")
            self._handle_call_failure(scheduled_call.lead_id, 'exception')

    def _handle_call_failure(self, lead_id: str, reason: str):
        """Handle call failure and decide on retry"""
        try:
            if lead_id in self.active_calls:
                scheduled_call = self.active_calls[lead_id]['scheduled_call']
                lead_data = scheduled_call.lead_data
                attempt_number = scheduled_call.attempt_number

                logger.info(f"📞 Call failed for lead {lead_id}, reason: {reason}")

                # Remove from active calls
                del self.active_calls[lead_id]

                # Update CRM
                self._update_crm_call_status(lead_id, f'Call Failed - {reason}', attempt_number)

                # Schedule retry if applicable
                if reason not in ['no_phone'] and attempt_number < 3:
                    self.schedule_retry_call(lead_id, lead_data, attempt_number)
                else:
                    # Move to failed calls
                    self.failed_calls[lead_id] = {
                        'lead_data': lead_data,
                        'reason': reason,
                        'final_attempt': attempt_number,
                        'failed_time': datetime.now()
                    }

        except Exception as e:
            logger.error(f"Error handling call failure for lead {lead_id}: {str(e)}")

    def handle_call_completion(self, lead_id: str, call_status: str, call_result: Dict[Any, Any]):
        """Handle call completion from webhook"""
        try:
            if lead_id in self.active_calls:
                scheduled_call = self.active_calls[lead_id]['scheduled_call']
                lead_data = scheduled_call.lead_data

                logger.info(f"📞 Call completed for lead {lead_id}, status: {call_status}")

                # Remove from active calls
                del self.active_calls[lead_id]

                # Move to completed calls
                self.completed_calls[lead_id] = {
                    'scheduled_call': scheduled_call,
                    'completion_time': datetime.now(),
                    'call_status': call_status,
                    'call_result': call_result
                }

                # Update CRM
                self._update_crm_call_status(lead_id, f'Call Completed - {call_status}', scheduled_call.attempt_number)

                # Handle different call outcomes
                if call_status in ['no-answer', 'busy']:
                    # Schedule retry
                    self.schedule_retry_call(lead_id, lead_data, scheduled_call.attempt_number)
                elif call_status in ['completed', 'answered']:
                    logger.info(f"✅ Call successfully completed for lead {lead_id}")
                else:
                    logger.warning(f"⚠️ Unexpected call status for lead {lead_id}: {call_status}")

        except Exception as e:
            logger.error(f"Error handling call completion for lead {lead_id}: {str(e)}")

    def _update_crm_call_status(self, lead_id: str, status: str, attempt_number: int):
        """Update CRM with call status"""
        try:
            from zoho.crm import ZohoCRM

            crm = ZohoCRM()
            notes = f"Auto-call attempt {attempt_number}: {status} at {datetime.now().isoformat()}"
            crm.add_conversation_notes(lead_id, notes)

        except Exception as e:
            logger.error(f"Error updating CRM for lead {lead_id}: {str(e)}")

    def _is_calling_hours(self) -> bool:
        """Check if current time is within calling hours"""
        current_hour = datetime.now().hour
        return self.calling_hours_start <= current_hour < self.calling_hours_end

    def _is_time_in_calling_hours(self, check_time: datetime) -> bool:
        """Check if a specific time is within calling hours"""
        return self.calling_hours_start <= check_time.hour < self.calling_hours_end

    def _get_next_calling_time(self) -> datetime:
        """Get the next available calling time"""
        current_time = datetime.now()

        # If today and within hours, return current time
        if self._is_calling_hours():
            return current_time

        # Otherwise, schedule for next calling hours
        if current_time.hour < self.calling_hours_start:
            # Later today
            next_time = current_time.replace(hour=self.calling_hours_start, minute=0, second=0, microsecond=0)
        else:
            # Tomorrow
            next_time = (current_time + timedelta(days=1)).replace(
                hour=self.calling_hours_start, minute=0, second=0, microsecond=0
            )

        return next_time

    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status for dashboard"""
        return {
            'queue_size': self.call_queue.qsize(),
            'active_calls': len(self.active_calls),
            'completed_calls': len(self.completed_calls),
            'failed_calls': len(self.failed_calls),
            'is_running': self.is_running,
            'in_calling_hours': self._is_calling_hours()
        }

    def get_recent_activity(self, limit: int = 10) -> list:
        """Get recent call activity for dashboard"""
        activity = []

        # Add recent completed calls
        for lead_id, call_data in list(self.completed_calls.items())[-limit//2:]:
            activity.append({
                'type': 'completed',
                'lead_id': lead_id,
                'timestamp': call_data['completion_time'],
                'status': call_data['call_status']
            })

        # Add recent failed calls
        for lead_id, call_data in list(self.failed_calls.items())[-limit//2:]:
            activity.append({
                'type': 'failed',
                'lead_id': lead_id,
                'timestamp': call_data['failed_time'],
                'reason': call_data['reason']
            })

        # Sort by timestamp
        activity.sort(key=lambda x: x['timestamp'], reverse=True)

        return activity[:limit]