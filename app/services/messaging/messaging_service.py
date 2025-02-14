from pyfcm import FCMNotification
from dotenv import load_dotenv
import os

load_dotenv()
FCM_API_KEY = os.getenv("FCM_API_KEY")
FCM_PROJECT_ID = os.getenv("FCM_PROJECT_ID")
PUSH_SERVICE = FCMNotification(project_id=FCM_PROJECT_ID)


def send_push_message(token: str, title: str, body: str, link: str):

    
    result = PUSH_SERVICE.notify_single_device(
        registration_id=token,
        message_title=title,
        message_body=body,
    )
    return result




