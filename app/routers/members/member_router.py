from typing import Optional
from fastapi import APIRouter, Depends, Query, Request, Response
from app.dtos.common.response import ErrorResponse, SuccessResponse
from app.repository.db import get_async_session
from sqlmodel.ext.asyncio.session import AsyncSession

from app.repository.fcmToken.fcm_token_respository import save_fcm_token
from app.repository.members.mebmer_repository import get_memberId_by_email

router = APIRouter()

@router.get("/logout")
async def logout(response: Response):
    """
    로그아웃 처리: 쿠키 삭제
    """
    response.delete_cookie(key="access_token", secure=False, samesite="None", httponly=True)
    response.delete_cookie(key="refresh_token", secure=False, samesite="None", httponly=True)
    print("로그아웃 되었습니다.")
    return {"message": "로그아웃 되었습니다."}

@router.post("/fcmToken")
async def reg_fcm_token(request: Request, fcm_token: str, email:Optional[str] = Query(...), session: AsyncSession = Depends(get_async_session)):
    """_summary_

    Args:
        fcm_token (str): 디바이스를 구분하는 fcm 토큰
    """
    try:
        if request.state.user is not None:
            member_email = request.state.user.get("email")
            member_id = await get_memberId_by_email(member_email, session)
            print("💡[ member_router ] member_id : ", member_id)
        else:
            member_id = await get_memberId_by_email(email, session)
            print("💡[ member_router ] member_id : ", member_id)
        # 1. 토큰 저장
        await save_fcm_token(member_id, fcm_token, session)
        return SuccessResponse(message="토큰 저장에 성공했습니다.")
    except Exception as e:
        return ErrorResponse(message="토큰 저장에 실패했습니다.", error_detail=e)
        


