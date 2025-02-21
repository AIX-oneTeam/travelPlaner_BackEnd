import logging
from fastapi import Request
from app.repository.members.mebmer_repository import get_memberId_by_email
from sqlmodel.ext.asyncio.session import AsyncSession

logger = logging.getLogger(__name__)


async def get_member_id_by_request(request: Request, session: AsyncSession):
    try:
        if request.state.user is not None:
            email = request.state.user.get("email")
            provider = request.state.user.get("provider")
            member_id = await get_memberId_by_email(email=email, session=session, provider=provider)
            logger.info(f"💡[ member_service ] get_member_id_by_request() member_id : {member_id}")
            return member_id
        else:
            logger.info("💡[ member_service ] get_member_id_by_request() 회원 정보가 없습니다.")
            return None
    except Exception as e:
        logger.error(f"💡[ member_service ] get_member_id_by_request() 에러 : {e}")

