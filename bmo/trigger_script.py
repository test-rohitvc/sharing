import imaplib
import email
import requests
import time
import os

# --- Configuration via Environment Variables ---
# os.getenv will pull the variable, or return None if it doesn't exist.
TRIGGER_EMAIL = os.getenv("TRIGGER_EMAIL", "trigger@bmo.in") 
TRIGGER_PASSWORD = os.getenv("TRIGGER_PASSWORD")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
MAIL_SERVER = os.getenv("MAIL_SERVER")

def check_inbox():
    # Safety check to ensure all variables are loaded
    if not all([TRIGGER_EMAIL, TRIGGER_PASSWORD, WEBHOOK_URL, MAIL_SERVER]):
        print("Error: Missing required environment variables. Please check your configuration.")
        return

    try:
        # Connect to the mail server
        mail = imaplib.IMAP4(MAIL_SERVER)
        mail.login(TRIGGER_EMAIL, TRIGGER_PASSWORD)
        mail.select('inbox')

        # Search for unread emails
        status, messages = mail.search(None, 'UNSEEN')
        
        for num in messages[0].split():
            # Fetch the email
            res, msg_data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            
            # Extract basic info
            subject = msg["subject"]
            sender = msg["from"]

            # Fire the webhook
            payload = {
                "triggered_by": TRIGGER_EMAIL,
                "sender": sender,
                "subject": subject
            }
            response = requests.post(WEBHOOK_URL, json=payload)
            
            if response.status_code in [200, 201, 202]:
                print(f"Success: Webhook fired for email from {sender}")
            else:
                print(f"Warning: Webhook returned status code {response.status_code}")

        mail.logout()
    except Exception as e:
        print(f"Error checking {TRIGGER_EMAIL}: {e}")

# Run continuously
print(f"Bot is now listening for emails on {TRIGGER_EMAIL}...")
while True:
    check_inbox()
    time.sleep(10) # Check every 10 seconds
