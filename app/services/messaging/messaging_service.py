import logging
from fastapi import HTTPException, Request
from pyfcm import FCMNotification
from dotenv import load_dotenv
from sqlmodel.ext.asyncio.session import AsyncSession
import os

from app.repository.fcmToken.fcm_token_respository import get_fcm_token
from app.services.members.member_service import get_member_id_by_request

load_dotenv()
logger = logging.getLogger(__name__)


# 파일 경로 상대 경로로 지정
FCM_SERVICE_ACCOUNT_JSON = os.path.join(os.path.dirname(__file__), "FCM_ADMIN.json")
FCM_PROJECT_ID = os.getenv("FCM_PROJECT_ID")

push_service = FCMNotification(service_account_file=FCM_SERVICE_ACCOUNT_JSON, project_id=FCM_PROJECT_ID)

def notify_message_to_one(token: str, title: str, body: str):
    
    result = push_service.notify(
        fcm_token=token,
        notification_title=title,
        notification_body=body,
        notification_image="https://easyTravel.jomalang.com/icons/complete.png",
    )
    return result

# 푸시 메시지 전송
async def send_push_message(request:Request, session:AsyncSession, title:str, body:str):
        try:
            member_id = await get_member_id_by_request(request, session)
            if member_id is not None:
                token = await get_fcm_token(member_id, session)
                logger.info(f"💡[ travel_all_schedule_agent_router ] token : {token}")
                if token is not None:
                    notify_message_to_one(token=token, title=title, body=body)
                else:
                    logger.info("💡[ travel_all_schedule_agent_router ] 회원 정보가 없습니다. 푸시 메시지 전송 실패.")
                    raise HTTPException(status_code=401, detail="회원 정보가 없습니다.")
            else:
                logger.info("💡[ travel_all_schedule_agent_router ] 회원 정보가 없습니다. 푸시 메시지 전송 실패.")
                raise HTTPException(status_code=401, detail="회원 정보가 없습니다.")
        except Exception as e:
            logger.error("💡[ travel_all_schedule_agent_router ] 푸시 메시지 전송 오류: {e}")




