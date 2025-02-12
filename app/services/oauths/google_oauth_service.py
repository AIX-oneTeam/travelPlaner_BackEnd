from fastapi import HTTPException
from google_auth_oauthlib.flow import Flow
import httpx
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import os
from app.utils.oauths.jwt_utils import create_jwt_google, create_jwt_kakao, create_refresh_token, decode_jwt


# Load .env variables
load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


async def handle_google_callback(code: str, state: str):

    if not code:
        raise HTTPException(status_code=400, detail="인가 코드가 필요합니다.")

    # 액세스 토큰 요청 데이터
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
        "state": state
    }

    try:
        # Google 토큰 엔드포인트로 요청
        async with httpx.AsyncClient() as client:
            response = await client.post(GOOGLE_TOKEN_URL, data=data)
            response.raise_for_status()
            token_data = response.json()

        # 응답 데이터 확인
        access_token = token_data.get("access_token")
        id_token = token_data.get("id_token")

        if not access_token or not id_token:
            raise HTTPException(status_code=500, detail="액세스 토큰을 가져오는데 실패했습니다.")

        # ID 토큰 디코딩
        user_info = decode_jwt(id_token)
        print("-------------------google_oauth_service.py-------------------")
        print(user_info)
        print("------------------------------------------------------------")

        access_token_google = create_jwt_google(provider="google", auth_info=user_info)
        refresh_token_google = create_refresh_token(user_info.get("email"))
        print("access_token_google", access_token_google)
        print("refresh_token_google", refresh_token_google)

        return ({
            "email": user_info.get("email"),
            "nickname": user_info.get("name"),
            "profile_url": user_info.get("picture"),
            "roles": ["USER"],
            "access_token": access_token_google,
            "refresh_token": refresh_token_google
            }
        )

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Error exchanging code for token: {e.response.text}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
