import os
import httpx
from dotenv import load_dotenv
from app.utils.oauths.jwt_utils import create_jwt_kakao, create_refresh_token, decode_jwt


# .env 파일 로드
load_dotenv()

# 환경 변수 설정 후에 변수 할당
KAKAO_CLIENT_ID = os.getenv("KAKAO_CLIENT_ID")
KAKAO_REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI")

# 디버깅 로그 추가

async def get_access_token(code: str, state: str) -> str:
    """
    카카오로부터 액세스 토큰을 가져옵니다.     #
    :param code: 카카오 로그인 인증 코드
    :return: 액세스 토큰 (str)
    """
    print("---------------------------------------")
    print("start get_access_token")
    print("---------------------------------------")
    token_url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": KAKAO_CLIENT_ID,
        "redirect_uri": KAKAO_REDIRECT_URI,
        "code": code,
        "state": state
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        async with httpx.AsyncClient() as client:   #
            response = await client.post(token_url, data=data, headers=headers)
            response.raise_for_status()
            token_data = response.json()
            return token_data.get("access_token")
    except httpx.HTTPStatusError as e:
        raise Exception(f"Failed to fetch access token: {e.response.text}") from e
    except Exception as e:
        raise Exception("An unexpected error occurred while fetching access token") from e


async def fetch_user_info(access_token: str) -> dict:
    """
    액세스 토큰을 사용해 카카오 사용자 정보를 가져옵니다.
    :param access_token: 카카오 액세스 토큰
    :return: 사용자 정보 (dict)
    """
    print("---------------------------------------")
    print("start fetch_user_info")
    print("---------------------------------------")
    user_info_url = "https://kapi.kakao.com/v2/user/me"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:

        async with httpx.AsyncClient() as client:
            response = await client.get(user_info_url, headers=headers)
            response.raise_for_status()
            user_info = response.json()
            return user_info
    except httpx.HTTPStatusError as e:
        raise Exception(f"Failed to fetch user info: {e.response.text}") from e
    except Exception as e:
        raise Exception("An unexpected error occurred while fetching user info") from e


async def handle_kakao_callback(code: str, state:str) -> dict:
    try:
        # 액세스 토큰 받기
        access_token = await get_access_token(code, state)

        if not access_token:
            raise ValueError("토큰이 유효하지 않습니다.")

        # 사용자 정보 받기
        user_info = await fetch_user_info(access_token)

        if not user_info:
            raise ValueError("Failed to get user info")
        # JWT 토큰 생성 
        try:
            jwt_token = create_jwt_kakao(provider="kakao", auth_info=user_info)

        except Exception as jwt_error:
            raise jwt_error
        # Refresh 토큰 생성
        try:
            refresh_token = create_refresh_token(user_info)

        except Exception as refresh_error:
            raise refresh_error

        payload = decode_jwt(jwt_token)

        # 반환할 사용자 정보 구성
        user_data = {
            "nickname": payload["nickname"], 
            "email": payload["email"],
            "profile_url": payload["profile_image"],
            "roles": ["USER"],
            "access_token": jwt_token,
            "refresh_token": refresh_token,

            "user_info": user_info
        }

        
        return user_data

    except Exception as e:
        raise Exception(f"Failed to handle Kakao callback: {str(e)}") from e