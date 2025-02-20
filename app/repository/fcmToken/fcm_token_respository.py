import logging
from sqlmodel import select, update
from app.data_models.data_model import MessageToken
from sqlmodel.ext.asyncio.session import AsyncSession

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

async def get_fcm_token(member_id: int, session: AsyncSession):
    logger.info(f"💡[ fcm_token_respository ] get_fcm_token() : {member_id}")
    try:
        result = await session.exec(select(MessageToken).where(MessageToken.member_id == member_id))
        # 항상 첫 번째 반환
        fcm_token = result.first()
        if fcm_token is None:
            return None
        return fcm_token.token
    except Exception as e:
        logger.error("💡[ fcm_token_respository ] get_fcm_token() 에러 : ", e)

async def save_fcm_token(member_id: int, fcm_token: str, session: AsyncSession):
    logger.info(f"💡[ fcm_token_respository ] save_fcm_token() : {member_id}, {fcm_token}")
    try:
        # 이미 존재하는 토큰인지 확인
        existing_token = await get_fcm_token(member_id=member_id, session=session)
        # 존재하지 않으면 저장
        if existing_token is None:
            session.add(MessageToken(member_id=member_id, token=fcm_token))
            logger.info(f"💡[ fcm_token_respository ] save_fcm_token() 새 fcm토큰을 저장합니다. : {member_id}, {fcm_token}")
        # 존재하되 같으면 무시
        elif existing_token == fcm_token:
            logger.info(f"💡[ fcm_token_respository ] save_fcm_token() 같은 fcm토큰이 이미 존재합니다. : {member_id}, {fcm_token}")
            return
        # 존재하되 다르면 업데이트
        else:
            logger.info(f"💡[ fcm_token_respository ] save_fcm_token() fcm 토큰 업데이트 : {member_id}, {fcm_token}")
            # 토큰 업데이트
            query = update(MessageToken).where(MessageToken.member_id == member_id).values(token=fcm_token)
            await session.exec(query)
            await session.commit()
        logger.info(f"💡[ fcm_token_respository ] save_fcm_token() 완료 : {member_id}, {fcm_token}")
    except Exception as e:
        logger.error(f"💡[ fcm_token_respository ] save_fcm_token() 에러 : {e}")



