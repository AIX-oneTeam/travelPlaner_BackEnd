import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import HTTPException, RequestValidationError

from app.repository.db import lifespan
from app.repository.db import init_table_by_SQLModel
from app.routers.members.member_router import router as member_router
from app.routers.spots.spot_router import router as spot_router
from app.routers.plans.plan_router import router as plan_router
from app.routers.plans.plan_spots_router import router as plan_spots_router
from app.routers.oauths.google_oauth_router import router as google_oauth_router
from app.routers.oauths.kakao_oauth_router import router as kakao_oauth_router
from app.routers.oauths.naver_oauth_router import router as naver_oauth_router
from app.utils.oauths.jwt_utils import decode_jwt, refresh_access_token_naver
from app.routers.regions.region_router import router as region_router
from app.routers.agents.travel_all_schedule_agent_router import router as agent_router
from app.routers.agents.accommodation_agent_router import router as accommodation_router
from app.routers.agents.restaurant_agent_router import router as restaurant_agent_router
from app.routers.agents.site_agent_router import router as site_agent_router
from app.routers.agents.cafe_agent_router import router as cafe_router
from app.routers.chceklists.checklist_router import router as checklist_router
import os
from dotenv import load_dotenv
import logging

load_dotenv()

# 로그 설정
logging.basicConfig(
    # filename="app.log",  # 파일로 저장
    level=logging.INFO,  # 로그 레벨 설정
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # 로그 형식
    datefmt="%Y-%m-%d %H:%M:%S",  # 날짜 형식
    handlers=[
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)
logger.info("💡로그 설정 완료")

# FastAPI 애플리케이션 생성
app = FastAPI(lifespan=lifespan)


# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://easytravel.jomalang.com",
        "http://localhost:3000",
    ],  # 모든 출처 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT 인증이 필요없는 경로들
PUBLIC_PATHS = {
    "/",  # 메인 페이지
    "/docs",  # Swagger UI
    "/openapi.json",  # OpenAPI 스키마
    "/oauths/google/callback",  # 구글 OAuth
    "/oauths/kakao/callback",  # 카카오 OAuth
    "/oauths/naver/callback",  # 네이버 OAuth
    "/refresh-token",  # 토큰 갱신
    "/test/",  # 테스트 경로
}


@app.middleware("http")
async def jwt_auth_middleware(request: Request, call_next):
    """
    JWT 인증 미들웨어
    """
    try:
        # 현재 요청 경로 확인
        path = request.url.path
        logger.info(f"💡요청 경로: {request.url.path}")

        # 공개 경로는 인증 없이 통과
        if path in PUBLIC_PATHS:
            return await call_next(request)

        token = request.cookies.get("access_token")

        if not token:
            logger.warning("토큰이 없습니다.")
            request.state.user = None
            return await call_next(request)

        try:
            # JWT 토큰 검증
            user_data = decode_jwt(token)
            request.state.user = user_data
            return await call_next(request)

        except HTTPException as he:

            # 액세스 토큰 만료 시 리프레시 토큰으로 재발급 시도
            logger.info("💡액세스 토큰 만료 시 리프레시 토큰으로 재발급 시도")
            refresh_token = request.cookies.get("refresh_token")
            if not refresh_token:
                logger.warning("💡리프레시 토큰이 없습니다.")
                request.state.user = None
                return await call_next(request)

            try:
                logger.info("리프레시 토큰으로 액세스 토큰 재발급 시도")
                new_access_token = await refresh_access_token_naver(refresh_token)
                response = await call_next(request)
                response.set_cookie(
                    key="access_token",
                    value=new_access_token,
                    httponly=True,
                    secure=True,
                    samesite="Lax",
                    max_age=3600,  # 쿠키 만료 시간 추가
                )
                return response

            except Exception as e:
                # 리프레시 토큰 갱신 실패
                logger.warning("💡리프레시 토큰 갱신 실패")
                print(f"리프레시 토큰 갱신 실패: {str(e)}")
                response = await call_next(request)
                response.delete_cookie("access_token")
                response.delete_cookie("refresh_token")
                return response

    except Exception as e:
        logger.warning(f"💡JWT 미들웨어 오류 : {str(e)}")
        # 예상치 못한 오류 처리
        print(f"JWT 미들웨어 오류: {str(e)}")
        request.state.user = None
        return await call_next(request)


# 요청 데이터 검증 오류 처리
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_data = await request.json()  # 요청 데이터를 JSON으로 받기

    error_details = exc.errors()  # Pydantic 검증 오류 내용 가져오기

    print("==================================================")
    print("요청 데이터:", request_data)  # 콘솔 출력 (디버깅)

    print("==================================================")
    print("검증 실패:", error_details)  # 오류 정보 출력

    print("==================================================")

    return JSONResponse(
        status_code=422,
        content={
            "message": "요청 데이터 검증 실패",
            "errors": error_details,
            "request_data": request_data,
        },
    )


@app.get("/")
async def root():
    # 데이터베이스 초기화
    # await init_table_by_SQLModel()
    return HTMLResponse(
        """
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <title>EasyTravel Server</title>
        </head>
        <body>
            <h1>EasyTravel Server</h1>
            <p>API 서버가 정상적으로 작동 중입니다.</p>
        </body>
        </html>
        """
    )


# 리프레시 토큰을 사용해 액세스 토큰을 갱신하는 엔드포인트
@app.get("/refresh-token")
async def refresh_token(request: Request):
    """
    리프레시 토큰을 사용하여 새 액세스 토큰을 발급합니다.
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Refresh token not found")

    new_access_token = await refresh_access_token_naver(refresh_token)
    response = {"message": "Token refreshed successfully"}
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        secure=True,
        samesite="Lax",
    )
    return response


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """
    HTTPException 처리
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail},
    )


# 라우터 추가
app.include_router(google_oauth_router, prefix="/oauths/google", tags=["Google Oauth"])
app.include_router(kakao_oauth_router, prefix="/oauths/kakao", tags=["Kakao Oauth"])
app.include_router(naver_oauth_router, prefix="/oauths/naver", tags=["Naver Oauth"])
app.include_router(member_router, prefix="/members", tags=["members"])
app.include_router(plan_router, prefix="/plans", tags=["plans"])
app.include_router(spot_router, prefix="/spots", tags=["spots"])
app.include_router(plan_spots_router, prefix="/plan_spots", tags=["plan_spots"])
app.include_router(region_router, prefix="/regions", tags=["regions"])
app.include_router(agent_router, prefix="/agents", tags=["agents"])
app.include_router(accommodation_router, prefix="/agents", tags=["agents"])
app.include_router(restaurant_agent_router, prefix="/agents", tags=["agents"])
app.include_router(site_agent_router, prefix="/agents", tags=["agents"])
app.include_router(cafe_router, prefix="/agents", tags=["agents"])
app.include_router(checklist_router, prefix="/checklist", tags=["checklists"])



