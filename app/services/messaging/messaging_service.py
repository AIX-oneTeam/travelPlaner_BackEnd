from pyfcm import FCMNotification
from dotenv import load_dotenv
import os

load_dotenv()


# 파일 경로 상대 경로로 지정
FCM_SERVICE_ACCOUNT_JSON = os.path.join(os.path.dirname(__file__), "easytravel-8cf1e-firebase-adminsdk-fbsvc-b1ba2a4a9c.json")
FCM_PROJECT_ID = os.getenv("FCM_PROJECT_ID")

push_service = FCMNotification(service_account_file=FCM_SERVICE_ACCOUNT_JSON, project_id=FCM_PROJECT_ID)

def send_push_message(token: str, title: str, body: str):
    
    result = push_service.notify(
        fcm_token=token,
        notification_title=title,
        notification_body=body,
        notification_image="https://easyTravel.jomalang.com/icons/Easy_Travel.png",
    )
    return result



