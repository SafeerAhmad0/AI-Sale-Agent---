import os
import requests
import logging
from datetime import datetime
from utils.logger import logger

class FacebookLeadAds:
    """Facebook Lead Ads integration for automatic lead pulling"""

    def __init__(self):
        self.access_token = os.getenv('FACEBOOK_ACCESS_TOKEN')
        self.page_id = os.getenv('FACEBOOK_PAGE_ID')
        self.app_secret = os.getenv('FACEBOOK_APP_SECRET')
        self.verify_token = os.getenv('FACEBOOK_VERIFY_TOKEN', 'ai_sales_agent_verify')

        if not all([self.access_token, self.page_id]):
            logger.warning("Facebook credentials not fully configured")

        self.base_url = "https://graph.facebook.com/v18.0"

    def verify_webhook(self, verify_token, challenge):
        """Verify Facebook webhook"""
        if verify_token == self.verify_token:
            logger.info("Facebook webhook verified successfully")
            return challenge
        else:
            logger.error("Facebook webhook verification failed")
            return None

    def process_webhook(self, data):
        """Process incoming Facebook Lead Ads webhook"""
        try:
            logger.info(f"Processing Facebook webhook: {data}")

            if 'entry' not in data:
                logger.warning("No entry data in Facebook webhook")
                return False

            for entry in data['entry']:
                if 'changes' in entry:
                    for change in entry['changes']:
                        if change.get('field') == 'leadgen':
                            lead_id = change['value']['leadgen_id']
                            page_id = change['value']['page_id']

                            logger.info(f"New lead detected: {lead_id} from page {page_id}")

                            # Fetch lead details
                            lead_data = self.get_lead_details(lead_id)
                            if lead_data:
                                return self.process_new_lead(lead_data)

            return True

        except Exception as e:
            logger.error(f"Error processing Facebook webhook: {str(e)}")
            return False

    def get_lead_details(self, lead_id):
        """Fetch detailed lead information from Facebook"""
        try:
            url = f"{self.base_url}/{lead_id}"
            params = {
                'access_token': self.access_token,
                'fields': 'id,created_time,field_data,form,ad_id,campaign_id'
            }

            response = requests.get(url, params=params)
            response.raise_for_status()

            lead_data = response.json()
            logger.info(f"Retrieved lead details: {lead_data}")

            return self.parse_lead_data(lead_data)

        except Exception as e:
            logger.error(f"Error fetching lead details for {lead_id}: {str(e)}")
            return None

    def parse_lead_data(self, raw_data):
        """Parse Facebook lead data into standard format"""
        try:
            parsed_lead = {
                'facebook_lead_id': raw_data['id'],
                'created_time': raw_data.get('created_time'),
                'ad_id': raw_data.get('ad_id'),
                'campaign_id': raw_data.get('campaign_id'),
                'source': 'Facebook Lead Ads'
            }

            # Parse field data
            field_data = raw_data.get('field_data', [])
            for field in field_data:
                field_name = field['name'].lower()
                field_value = field['values'][0] if field['values'] else ''

                # Map common field names
                if field_name in ['full_name', 'name']:
                    name_parts = field_value.split(' ', 1)
                    parsed_lead['First_Name'] = name_parts[0]
                    parsed_lead['Last_Name'] = name_parts[1] if len(name_parts) > 1 else ''
                elif field_name in ['first_name']:
                    parsed_lead['First_Name'] = field_value
                elif field_name in ['last_name']:
                    parsed_lead['Last_Name'] = field_value
                elif field_name in ['phone_number', 'phone']:
                    parsed_lead['Phone'] = field_value
                elif field_name in ['email']:
                    parsed_lead['Email'] = field_value
                elif field_name in ['company', 'company_name']:
                    parsed_lead['Company'] = field_value
                elif field_name in ['city']:
                    parsed_lead['City'] = field_value
                elif field_name in ['state']:
                    parsed_lead['State'] = field_value
                elif field_name in ['interest', 'product_interest']:
                    parsed_lead['Product_Interest'] = field_value
                elif field_name in ['budget']:
                    parsed_lead['Budget'] = field_value
                elif field_name in ['timeline']:
                    parsed_lead['Timeline'] = field_value
                else:
                    # Store custom fields
                    parsed_lead[f'custom_{field_name}'] = field_value

            # Set default values
            parsed_lead.setdefault('Lead_Status', 'New')
            parsed_lead.setdefault('Lead_Source', 'Facebook Lead Ads')

            logger.info(f"Parsed lead data: {parsed_lead}")
            return parsed_lead

        except Exception as e:
            logger.error(f"Error parsing lead data: {str(e)}")
            return None

    def process_new_lead(self, lead_data):
        """Process new lead - sync to CRM and trigger call"""
        try:
            logger.info(f"Processing new lead: {lead_data.get('First_Name', 'Unknown')} {lead_data.get('Last_Name', '')}")

            # Import here to avoid circular imports
            from zoho.crm import ZohoCRM
            from scheduler.call_scheduler import CallScheduler

            # Sync to Zoho CRM
            crm = ZohoCRM()
            zoho_lead_id = crm.create_lead(lead_data)

            if zoho_lead_id:
                logger.info(f"Lead synced to Zoho CRM with ID: {zoho_lead_id}")

                # Schedule automatic call
                scheduler = CallScheduler()
                call_scheduled = scheduler.schedule_immediate_call(zoho_lead_id, lead_data)

                if call_scheduled:
                    logger.info(f"Auto-call scheduled for lead {zoho_lead_id}")
                    return True
                else:
                    logger.warning(f"Failed to schedule call for lead {zoho_lead_id}")
                    return False
            else:
                logger.error("Failed to sync lead to Zoho CRM")
                return False

        except Exception as e:
            logger.error(f"Error processing new lead: {str(e)}")
            return False

    def get_lead_forms(self):
        """Get all lead forms for the page"""
        try:
            url = f"{self.base_url}/{self.page_id}/leadgen_forms"
            params = {
                'access_token': self.access_token,
                'fields': 'id,name,status,leads_count'
            }

            response = requests.get(url, params=params)
            response.raise_for_status()

            forms = response.json().get('data', [])
            logger.info(f"Retrieved {len(forms)} lead forms")

            return forms

        except Exception as e:
            logger.error(f"Error fetching lead forms: {str(e)}")
            return []

    def test_connection(self):
        """Test Facebook API connection"""
        try:
            url = f"{self.base_url}/me"
            params = {'access_token': self.access_token}

            response = requests.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            logger.info(f"Facebook API connection successful: {data.get('name', 'Unknown')}")
            return True

        except Exception as e:
            logger.error(f"Facebook API connection failed: {str(e)}")
            return False

    def subscribe_to_webhooks(self):
        """Subscribe to lead generation webhooks"""
        try:
            url = f"{self.base_url}/{self.page_id}/subscribed_apps"
            params = {
                'access_token': self.access_token,
                'subscribed_fields': 'leadgen'
            }

            response = requests.post(url, params=params)
            response.raise_for_status()

            logger.info("Successfully subscribed to Facebook lead generation webhooks")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe to webhooks: {str(e)}")
            return False