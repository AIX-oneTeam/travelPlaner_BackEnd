import logging
from fastapi import Request
from collections import Counter
from app.repository.members.mebmer_repository import get_memberId_by_email,get_member_signup_count
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



async def get_member_signup_count_service(session: AsyncSession):
    
    # 리포지토리 함수 호풀
    crate_dates = await get_member_signup_count(session)

    #날짜를 문자열로 변환
    date_string= [
        dt.strftime("%Y-%m-%d")
        for dt in crate_dates  if dt is not None
    ]
    # 나온 결과를 집계
    counts = Counter(date_string)

    #
    signup_counts = [
        {"signup_date": date, "member_count": count}
        for date , count in counts.items()
    ]
    
    signup_counts.sort(key=lambda x: x["signup_date"], reverse=True)

    return signup_counts
        

