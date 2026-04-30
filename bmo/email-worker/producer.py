import imaplib
import email
import requests
import time
import os
import uuid

# Import the celery app instance we just created
from celery_app import app as celery_app

# --- 1. Configuration via Environment Variables ---
# Email Settings
TRIGGER_EMAIL = os.getenv("TRIGGER_EMAIL", "trigger@bmo.in") 
TRIGGER_PASSWORD = os.getenv("TRIGGER_PASSWORD")
MAIL_SERVER = os.getenv("MAIL_SERVER", "10.0.1.90")

# FileBrowser Settings
FB_BASE_URL = os.getenv("FILEBROWSER_URL", "http://10.0.1.90:8080")
FB_USER = os.getenv("FILEBROWSER_USER", "admin")
FB_PASS = os.getenv("FILEBROWSER_PASS")

# --- 2. FileBrowser API Helper Functions ---
def get_fb_token():
    url = f"{FB_BASE_URL}/api/login"
    payload = {"username": FB_USER, "password": FB_PASS}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.text 
    except Exception as e:
        print(f"FileBrowser Auth Error: {e}")
        return None

def upload_attachment_to_fb(token, filename, file_data, folder_name):
    dest_path = f"Email_Attachments/{folder_name}/{filename}"
    upload_url = f"{FB_BASE_URL}/api/resources/{dest_path}"
    headers = {"X-Auth": token}
    
    try:
        response = requests.post(upload_url, data=file_data, headers=headers)
        if response.status_code in [200, 201]:
            return f"{FB_BASE_URL}/files/{dest_path}"
        else:
            print(f"FileBrowser Upload Failed: {response.text}")
            return None
    except Exception as e:
        print(f"FileBrowser Upload Error: {e}")
        return None

# --- 3. Core Email Processing Logic ---
def check_inbox():
    if not all([TRIGGER_EMAIL, TRIGGER_PASSWORD, MAIL_SERVER, FB_USER, FB_PASS]):
        print("Error: Missing required environment variables.")
        return

    try:
        mail = imaplib.IMAP4(MAIL_SERVER)
        mail.login(TRIGGER_EMAIL, TRIGGER_PASSWORD)
        mail.select('inbox')

        status, messages = mail.search(None, 'UNSEEN')
        
        for num in messages[0].split():
            res, msg_data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            
            sender = msg.get("From")
            to = msg.get("To")
            cc = msg.get("Cc")
            bcc = msg.get("Bcc")
            subject = msg.get("Subject")
            
            message_id = msg.get("Message-ID")
            in_reply_to = msg.get("In-Reply-To")
            references = msg.get("References")
            
            body_text = ""
            uploaded_attachments = []
            email_uuid = str(uuid.uuid4())[:8] 

            if msg.is_multipart():
                fb_token = None 
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))

                    if content_type == "text/plain" and "attachment" not in content_disposition:
                        body_text += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    
                    elif "attachment" in content_disposition:
                        filename = part.get_filename()
                        if filename:
                            file_data = part.get_payload(decode=True)
                            
                            if not fb_token:
                                fb_token = get_fb_token()
                            
                            if fb_token:
                                print(f"Uploading {filename} to FileBrowser...")
                                file_link = upload_attachment_to_fb(fb_token, filename, file_data, email_uuid)
                                
                                if file_link:
                                    uploaded_attachments.append({
                                        "title": filename,
                                        "link": file_link,
                                        "mime_type": content_type
                                    })
            else:
                body_text = msg.get_payload(decode=True).decode('utf-8', errors='ignore')

            # --- Construct Payload ---
            payload = {
                "routing": {"from": sender, "to": to, "cc": cc, "bcc": bcc},
                "thread_meta": {"subject": subject, "message_id": message_id, "in_reply_to": in_reply_to, "references": references},
                "content": {"body": body_text.strip(), "attachments": uploaded_attachments}
            }
            
            # --- Fire to RabbitMQ via Celery ---
            # 'process_email_job' is the name the consumer will be listening for
            try:
                result = celery_app.send_task(
                    "process_email_job", 
                    kwargs={"email_payload": payload}
                )
                print(f"Task pushed to queue successfully. Task ID: {result.id} | Subject: {subject}")

                mail.store(num, '+FLAGS', '\\Seen')
                print("Email marked as SEEN.")
            except Exception as e:
                print(f"Failed to push task to RabbitMQ: {e}")

        mail.logout()
    except Exception as e:
        print(f"System Error: {e}")

# --- 4. Main Loop ---
if __name__ == "__main__":
    print(f"Integration Bot listening on {TRIGGER_EMAIL}...")
    while True:
        check_inbox()
        time.sleep(10)
