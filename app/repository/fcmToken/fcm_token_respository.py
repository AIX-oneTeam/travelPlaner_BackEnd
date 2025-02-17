import logging
from sqlmodel import select
from app.data_models.data_model import MessageToken
from sqlmodel.ext.asyncio.session import AsyncSession

logger = logging.getLogger(__name__)

async def save_fcm_token(member_id: int, fcm_token: str, session: AsyncSession):
    logger.info("💡[ fcm_token_respository ] save_fcm_token() : ", member_id, fcm_token)
    try:
        session.add(MessageToken(member_id=member_id, token=fcm_token))
    except Exception as e:
        logger.error("💡[ fcm_token_respository ] save_fcm_token() 에러 : ", e)

async def get_fcm_token(member_id: int, session: AsyncSession):
    logger.info("💡[ fcm_token_respository ] get_fcm_token() : ", member_id)
    try:
        result = await session.exec(select(MessageToken).where(MessageToken.member_id == member_id))
        fcm_token = result.first()
        if fcm_token is None:
            return None
        return fcm_token.token
    except Exception as e:
        logger.error("💡[ fcm_token_respository ] get_fcm_token() 에러 : ", e)

