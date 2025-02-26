import asyncio
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import HTTPException, RequestValidationError
from huggingface_hub import get_session

from app.dtos.common.response import ErrorResponse
from app.repository.db import lifespan
from app.repository.db import init_table_by_SQLModel
from app.routers.members.member_router import router as member_router
from app.routers.spots.spot_router import router as spot_router
from app.routers.plans.plan_router import router as plan_router
from app.routers.plans.plan_spots_router import router as plan_spots_router
from app.routers.oauths.google_oauth_router import router as google_oauth_router
from app.routers.oauths.kakao_oauth_router import router as kakao_oauth_router
from app.routers.oauths.naver_oauth_router import router as naver_oauth_router
from app.utils.oauths.jwt_utils import decode_jwt, refresh_access_token
from app.routers.regions.region_router import router as region_router
from app.routers.agents.travel_all_schedule_agent_router import router as agent_router
from app.routers.agents.accommodation_agent_router import router as accommodation_router
from app.routers.agents.restaurant_agent_router import router as restaurant_agent_router
from app.routers.agents.site_agent_router import router as site_agent_router
from app.routers.agents.cafe_agent_router import router as cafe_router
from app.routers.chceklists.checklist_router import router as checklist_router
from sqlmodel.ext.asyncio.session import AsyncSession
from app.routers.voice_router import router as voice_router
from app.routers.inquiries.inquiry_router import router as inquiry_router
from app.routers.survey.survey_router import router as survey_router
from app.routers.agents.agent_metrics_router import router as agent_metrics_router
import os
from dotenv import load_dotenv
import logging
# import agentops
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
logging.getLogger("sqlalchemy.engine").setLevel(logging.DEBUG)
logging.getLogger("sqlalchemy.pool").setLevel(logging.DEBUG)
logging.getLogger("sqlalchemy.orm").setLevel(logging.DEBUG)


logger = logging.getLogger(__name__)
logger.info("💡로그 설정 완료")

# AGENTOPS_API_KEY = os.getenv("AGENTOPS_API_KEY")
# agentops.init(AGENTOPS_API_KEY)
# logger.info("--------------agentops api key가 존재합니다") if AGENTOPS_API_KEY else logger.info("agentops api키가 없습니다")

# FastAPI 애플리케이션 생성
app = FastAPI(lifespan=lifespan)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://easytravel.jomalang.com",
        "http://admin-easytravel.jomalang.com",
        "http://localhost:3001",
        "http://localhost:3000",
        "http://localhost:3000/checkList"
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
        refresh_token = request.cookies.get("refresh_token")

        # 액세스 토큰이 없지만 리프레시 토큰이 있는 경우
        if not token and refresh_token:
            try:
                logger.info("💡액세스 토큰 없음, 리프레시 토큰으로 재발급 시도")
                new_access_token = await refresh_access_token(refresh_token)
                logger.info(f"💡새로운 액세스 토큰: {new_access_token}")
                # 새로운 액세스 토큰 요청에 저장
                request.state.user = decode_jwt(new_access_token)

                response = await call_next(request)
                response.set_cookie(
                    key="access_token",
                    value=new_access_token,
                    httponly=True,
                    secure=True,
                    samesite="None",
                    max_age=3600,
                )
                return response
            except Exception as e:
                logger.warning(f"💡리프레시 토큰으로 재발급 실패 다시 로그인 해주세요 {e}")
                response = ErrorResponse(
                    status_code=401,
                    message="올바르지 않은 리프레시 토큰입니다.",
                )
                # 잘못된 토큰 삭제
                response.delete_cookie(key="access_token", secure=True, samesite="None", httponly=True)
                response.delete_cookie(key="refresh_token", secure=True, samesite="None", httponly=True)
                return response

        # 토큰도 없고 리프레시 토큰도 없는 경우 (로그인 없이 진행되는 로직)
        if not token and not refresh_token:
            logger.warning("💡토큰이 없습니다.")
            request.state.user = None
            return await call_next(request)

        # 토큰이 있을 경우
        try:
            # JWT 토큰 검증
            user_data = decode_jwt(token)
            request.state.user = user_data
            return await call_next(request)

        # 액세스 토큰 만료시 리프레시 토큰으로 재발급 시도
        except HTTPException as he:
            logger.info("💡액세스 토큰 만료 시 리프레시 토큰으로 재발급 시도")
            refresh_token = request.cookies.get("refresh_token")
            if not refresh_token:
                logger.warning("💡리프레시 토큰이 없습니다.")
                request.state.user = None
                return await call_next(request)

            try:
                logger.info("리프레시 토큰으로 액세스 토큰 재발급 시도")
                new_access_token = await refresh_access_token(refresh_token)
                logger.info(f"💡새로운 액세스 토큰: {new_access_token}")
                # 새로운 액세스 토큰 요청에 저장
                request.state.user = decode_jwt(new_access_token)
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
                logger.warning(f"💡리프레시 토큰으로 재발급 실패 다시 로그인 해주세요 {e}")
                response = ErrorResponse(
                    status_code=401,
                    message="올바르지 않은 리프레시 토큰입니다.",
                )
                # 잘못된 토큰 삭제
                response.delete_cookie(key="access_token", secure=True, samesite="None", httponly=True)
                response.delete_cookie(key="refresh_token", secure=True, samesite="None", httponly=True)
                return response

    except Exception as e:
        logger.warning(f"💡JWT 미들웨어 오류 : {str(e)}")
        # 예상치 못한 에러
        request.state.user = None
        return ErrorResponse(
            status_code=500,
            error_detail=str(e),
            message="jwt 미들웨어에서 발생한 오류",
        )


# 요청 데이터 검증 오류 처리
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_data = await request.json()  # 요청 데이터를 JSON으로 받기

    error_details = exc.errors()  # Pydantic 검증 오류 내용 가져오기

    logger.info(f"요청 데이터: {request_data}")  # 콘솔 출력 (디버깅)

    logger.info(f"검증 실패: {error_details}")  # 오류 정보 출력


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
app.include_router(voice_router, prefix="/voice", tags=["voice"])
app.include_router(inquiry_router, prefix="/inquiries", tags=["inquiry"])
app.include_router(survey_router, prefix="/survey", tags=["survey"])
app.include_router(agent_metrics_router, prefix="/agents", tags=["agents"])