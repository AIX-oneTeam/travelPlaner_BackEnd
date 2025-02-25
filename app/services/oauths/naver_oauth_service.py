import secrets
import httpx
import os
import dotenv
import logging

from app.utils.oauths.jwt_utils import create_refresh_token

dotenv.load_dotenv()

NAVER_TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
NAVER_PROFILE_URL = "https://openapi.naver.com/v1/nid/me"

NAVER_CLIENT_ID: str = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET: str = os.getenv("NAVER_CLIENT_SECRET")
NAVER_REDIRECT_URI: str = os.getenv("NAVER_REDIRECT_URI")

logging.getLogger("__name__").setLevel(logging.INFO)


async def get_naver_access_token(code: str, state: str) -> dict:
    """
    네이버로부터 액세스 토큰을 가져옵니다.
    """
    params = {
        "grant_type": "authorization_code",
        "client_id": NAVER_CLIENT_ID,
        "client_secret": NAVER_CLIENT_SECRET,
        "redirect_uri": NAVER_REDIRECT_URI,
        "code": code,
        "state": state,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(NAVER_TOKEN_URL, params=params)
        response.raise_for_status()
        print("naver access token response", response.json())
        return response.json() 

async def get_naver_user_profile(access_token: str) -> dict:
    """
    네이버 사용자 프로필 정보를 가져옵니다.
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        response = await client.get(NAVER_PROFILE_URL, headers=headers)
        response.raise_for_status()
        logging.info("💡naver_user_profile", response.json())
        return response.json()


def get_login_url() -> str:
    """
    네이버 로그인 URL을 생성합니다.
    """
    state = secrets.token_urlsafe(16)  # 고유한 state 값 생성
    return (
        f"https://nid.naver.com/oauth2.0/authorize"
        f"?response_type=code"
        f"&client_id={NAVER_CLIENT_ID}"
        f"&redirect_uri={NAVER_REDIRECT_URI}"
        f"&state={state}"
    )


async def handle_callback(code: str, state: str) -> dict:
    """
    네이버 콜백 처리 및 사용자 정보 가져오기.
    액세스 토큰과 리프레시 토큰을 반환하고,
    리프레시 토큰으로 액세스 토큰을 갱신할 수도 있습니다.
    """
    # 액세스 토큰 및 리프레시 토큰 가져오기
    token_response = await get_naver_access_token(code, state)
    access_token = token_response.get("access_token")
    refresh_token = create_refresh_token(provider="naver", user_email=token_response.get("email"))

    if not access_token:
        raise ValueError("Access token not found")

    # 사용자 정보 가져오기
    user_profile = await get_naver_user_profile(access_token)
    print("---------------------------------------")
    print("💡naver_user_profile", user_profile)
    print("---------------------------------------")

    # 사용자 정보와 토큰 반환
    return {
            "nickname": user_profile.get("response", {}).get("name"),
            "email": user_profile.get("response", {}).get("email"),
            "profile_url": user_profile.get("response", {}).get("profile_image"),
            "roles": user_profile.get("response", {}).get("roles"),
            "access_token": access_token,
            "refresh_token": refresh_token
        }
    
