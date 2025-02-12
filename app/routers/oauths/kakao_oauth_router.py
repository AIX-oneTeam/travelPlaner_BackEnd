import logging
from fastapi import APIRouter, Depends, HTTPException, Response
from app.data_models.data_model import Member
from app.repository.db import get_async_session
from app.repository.members.mebmer_repository import is_exist_member_by_email, save_member
from app.services.oauths.kakao_oauth_service import handle_kakao_callback
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter()

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@router.get("/callback")
async def kakao_callback(code: str, state: str, response: Response, session: AsyncSession = Depends(get_async_session)):
    """
    카카오 인증 콜백: 인증 코드를 받아 JWT와 Refresh Token을 쿠키에 저장.
    """
    redirect_url = "http://localhost:3000"
    try:
        # 1. 인증 코드 수신 로그
        logger.info(f"[Kakao Callback] 받은 인증 코드: {code}")

        # 2. 인증 코드 처리 및 사용자 정보 가져오기
        try:
            user_data = await handle_kakao_callback(code, state)
            logger.info(f"[Kakao Callback] 사용자 정보 처리 성공: {user_data}")
        except Exception as e:
            logger.error(f"[Kakao Callback] 사용자 정보 처리 실패: {e}")
            raise HTTPException(status_code=400, detail=f"카카오 인증 실패: 사용자 정보 처리 중 오류 발생")   
        # 3. JWT 토큰 쿠키 저장
        try:
            logger.info("[Kakao Callback] JWT 토큰 쿠키 저장 시작")

            response.set_cookie(
                key="access_token",
                value=user_data["access_token"],
                max_age=3600,
                samesite="None",
                secure=True,
                httponly=True,
            )
            logger.info("[Kakao Callback] JWT 토큰 쿠키 저장 완료")
        except Exception as e:
            logger.error(f"[Kakao Callback] JWT 토큰 쿠키 저장 실패: {e}")
            raise HTTPException(status_code=500, detail="JWT 토큰 쿠키 저장 중 오류 발생")

        # 4. Refresh Token 쿠키 저장
        try:
            logger.info("[Kakao Callback] Refresh Token 쿠키 저장 시작")
            response.set_cookie(
                key="refresh_token",
                value=user_data["refresh_token"],
                max_age=30 * 24 * 60 * 60,
                samesite="None",
                secure=True,
                httponly=True
            )
            logger.info("[Kakao Callback] Refresh Token 쿠키 저장 완료")
        except Exception as e:
            logger.error(f"[Kakao Callback] Refresh Token 쿠키 저장 실패: {e}")
            raise HTTPException(status_code=500, detail="Refresh Token 쿠키 저장 중 오류 발생")
        

        # 5. 프론트엔드로 리다이렉트
        try:
            logger.info("[Kakao Callback] 회원 정보 데이터 베이스 시작")

            if not await is_exist_member_by_email(user_data["email"], "kakao", session):
                await save_member(Member(
                    email=user_data["email"],
                    name=user_data["nickname"],
                    nickname=user_data["nickname"],
                    picture_url=user_data["profile_url"],
                    roles=user_data["roles"],
                    access_token=user_data["access_token"],
                    refresh_token=user_data["refresh_token"],
                    oauth="kakao"), session)


            return {"content": "카카오 로그인 성공",
                    "nickname": user_data["nickname"],
                    "email":user_data["email"],
                    "profile_url":user_data["profile_url"],
                    "roles":user_data["roles"],}

        except Exception as e:
            logger.error(f"[Kakao Callback] 회원 정보 데이터 베이스 저장 실패: {e}")
            raise HTTPException(status_code=500, detail="회원 정보 데이터 베이스 저장 중 오류 발생")

    except Exception as e:
        logger.error(f"[Kakao Callback] 예외 발생: {e}")
        raise HTTPException(status_code=400, detail=f"카카오 인증 실패: {str(e)}")

