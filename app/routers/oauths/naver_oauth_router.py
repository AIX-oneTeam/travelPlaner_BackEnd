from fastapi import APIRouter, Depends, HTTPException, Response, Request

from app.data_models.data_model import Member
from app.repository.members.mebmer_repository import is_exist_member_by_email, save_member
from app.services.oauths.naver_oauth_service import get_login_url, handle_callback
from app.repository.db import get_async_session
from sqlmodel.ext.asyncio.session import AsyncSession



router = APIRouter()


@router.get("/callback")
async def naver_callback(code: str, state: str, response: Response, session: AsyncSession = Depends(get_async_session)):
    """
    네이버 인증 콜백 처리 및 JWT 쿠키 저장
    """
    try:
        user_data = await handle_callback(code, state)
        access_token = user_data["access_token"]
        refresh_token = user_data["refresh_token"]

        # JWT를 쿠키에 저장
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,  # 브라우저에서 접근 불가능하도록 설정
            secure=True,    # HTTPS를 통해서만 전송되도록 설정 (로컬 테스트 중에는 False로 변경 가능)
            samesite="None", # 쿠키 정책 설정
        )

        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,
            samesite="None",
        )

        if not await is_exist_member_by_email(user_data["email"], "naver", session):
            print("---------------------------------------")
            print("💡naver_user_data", user_data)
            print("---------------------------------------")
            await save_member(Member(
                email=user_data["email"],
                name=user_data["nickname"],
                nickname=user_data["nickname"],
                picture_url=user_data["profile_url"],
                roles=user_data["roles"],
                access_token=user_data["access_token"],
                refresh_token=user_data["refresh_token"],
                oauth="naver"), session)

        return {"content": "네이버 로그인 성공",
                "nickname": user_data["nickname"],
                "email":user_data["email"],
                "profile_url":user_data["profile_url"],
                "roles":user_data["roles"],}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"네이버 인증 실패: {e}") 