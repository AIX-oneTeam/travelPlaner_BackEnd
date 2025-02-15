from sqlmodel import select
from app.data_models.data_model import FcmToken
from sqlmodel.ext.asyncio.session import AsyncSession


async def save_fcm_token(member_id: int, fcm_token: str, session: AsyncSession):
    print("💡[ fcm_token_respository ] save_fcm_token() : ", member_id, fcm_token)
    try:
        session.add(FcmToken(member_id=member_id, fcm_token=fcm_token))
    except Exception as e:
        print("💡[ fcm_token_respository ] save_fcm_token() 에러 : ", e)

async def get_fcm_token(member_id: int, session: AsyncSession):
    print("💡[ fcm_token_respository ] get_fcm_token() : ", member_id)
    try:
        result = await session.exec(select(FcmToken).where(FcmToken.member_id == member_id))
        fcm_token = result.first()
        return fcm_token
    except Exception as e:
        print("💡[ fcm_token_respository ] get_fcm_token() 에러 : ", e)

