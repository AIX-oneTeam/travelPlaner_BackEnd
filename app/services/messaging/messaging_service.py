from pyfcm import FCMNotification
from dotenv import load_dotenv
import base64
import json
import os

load_dotenv()

FCM_SERVICE_ACCOUNT_JSON = "./services/messaging/easytravel-8cf1e-firebase-adminsdk-fbsvc-b1ba2a4a9c.json"
FCM_PROJECT_ID = os.getenv("FCM_PROJECT_ID")

push_service = FCMNotification(service_account_file=FCM_SERVICE_ACCOUNT_JSON, project_id=FCM_PROJECT_ID)

def send_push_message(token: str, title: str, body: str, link: str):
    
    result = push_service.notify(
        fcm_token=token,
        notification_title=title,
        notification_body=body,
        notification_image=link,
    )
    return result




