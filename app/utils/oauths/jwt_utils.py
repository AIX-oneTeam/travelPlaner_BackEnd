import datetime
import os
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
import jwt
import base64
import json
import logging
from sqlmodel.ext.asyncio.session import AsyncSession
from app.data_models.data_model import Member
from app.repository.db import get_async_session, get_async_session_manual
from app.repository.members.mebmer_repository import get_member_by_email_and_provider

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 환경 변수 로드
load_dotenv()
JWT_SECRET_KEY = str(os.getenv("JWT_SECRET_KEY", ""))
JWT_REFRESH_SECRET_KEY = str(os.getenv("JWT_REFRESH_SECRET_KEY", ""))
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
# naver Secret Key 및 Algorithm 설정
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7  # 리프레시 토큰 유효기간

def base64_encode(data: dict) -> str:
    """딕셔너리를 Base64로 인코딩"""
    json_string = json.dumps(data)  # JSON 형식 문자열로 변환
    encoded_data = base64.urlsafe_b64encode(json_string.encode("utf-8")).decode("utf-8")
    return encoded_data


def base64_decode(encoded_data: str) -> dict:
    """Base64로 인코딩된 데이터를 디코딩"""
    decoded_bytes = base64.urlsafe_b64decode(encoded_data.encode("utf-8"))
    return json.loads(decoded_bytes.decode("utf-8"))

def decode_jwt(token: str) -> dict:
    """
    서명없는 JWT 디코딩
    """
    try:
        # JWT 디코딩
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload
    except jwt.ExpiredSignatureError:
        raise jwt.ExpiredSignatureError("토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        raise jwt.InvalidTokenError("유효하지 않은 토큰입니다.")
    except Exception as e:
        raise e


def verify_jwt_token(token: str = Depends(oauth2_scheme)) -> dict:
    """
    JWT 검증
    """
    try:
        # JWT 디코딩
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        # Base64 디코딩된 Payload 반환
        return base64_decode(payload["data"])
    except jwt.ExpiredSignatureError:
        raise jwt.ExpiredSignatureError("토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        raise jwt.InvalidTokenError("유효하지 않은 토큰입니다.")
    except Exception as e:
        raise e


def create_refresh_token(user_email: str, provider: str) -> str:
    """
    Refresh Token 생성
    """
    current_time = datetime.datetime.now()
    exp_time = current_time + datetime.timedelta(days=30)  # 30일 후 만료

    # Payload 생성
    payload = {
        'iss': 'EasyTravel',
        'sub': user_email,
        'exp': int(exp_time.timestamp()),
        'iat': int(current_time.timestamp()),
        'provider': provider
    }
    # JWT 생성
    refresh_token = jwt.encode({"data": payload}, JWT_REFRESH_SECRET_KEY, algorithm="HS256")
    return refresh_token

def create_jwt_naver(provider: str, data: dict = None, member_info: Member = None) -> str:
    """
    Access Token 생성
    """
    to_encode = {}
    if member_info is not None:
        current_time = datetime.datetime.utcnow()  # 현재 시간
        exp_time = current_time + datetime.timedelta(days=1)  # 1일 후 만료
        to_encode ={
            "iss": "EasyTravel",  # 발급자
            "sub": str(member_info.id),  # 사용자 식별자
            "provider": str(member_info.oauth),  # 소셜 로그인 제공자
            "nickname": member_info.name,  # 닉네임
            "email": member_info.email,  # 이메일
            "roles": member_info.roles if member_info and member_info.roles else "USER",
            "profile_image": member_info.picture_url,  # 프로필 이미지
            "exp": int(exp_time.timestamp()),  # 만료 시간
            "iat": int(current_time.timestamp())  # 발급 시간
        }

    if data is not None:
        to_encode = data.copy()
        expire = datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})  # 만료 시간 추가
        to_encode.update({"provider": provider})
        to_encode.update({"roles": member_info.roles if member_info and member_info.roles else "USER"})
    
    
    token = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return token

def create_jwt_kakao(provider: str, auth_info: dict = None, member_info: Member = None) -> str:
    """
    Access Token 생성 (사용자 정보 포함)
    """
    current_time = datetime.datetime.utcnow()  # 현재 시간
    exp_time = current_time + datetime.timedelta(days=1)  # 1일 후 만료

    # 필요한 사용자 정보를 포함한 Access Token 생성
    if auth_info is not None:
        payload = {
            "iss": "EasyTravel",  # 발급자
            "sub": str(auth_info.get("id")),  # 사용자 식별자
            "provider": provider,  # 소셜 로그인 제공자
            "nickname": auth_info.get("properties", {}).get("nickname"),  # 닉네임
            "email": auth_info.get("kakao_account", {}).get("email"),  # 이메일
            "profile_image": auth_info.get("properties", {}).get("profile_image"),  # 프로필 이미지
            "exp": int(exp_time.timestamp()),  # 만료 시간
            "iat": int(current_time.timestamp()),  # 발급 시간
            "roles": member_info.roles if member_info and member_info.roles else "USER"
            }
    
    if member_info is not None:
        payload = {
            "iss": "EasyTravel",  # 발급자
            "sub": str(member_info.id),  # 사용자 식별자
            "provider": str(member_info.oauth),  # 소셜 로그인 제공자
            "nickname": member_info.name,  # 닉네임
            "email": member_info.email,  # 이메일
            "roles": member_info.roles if member_info and member_info.roles else "USER",
            "profile_image": member_info.picture_url,  # 프로필 이미지
            "exp": int(exp_time.timestamp()),  # 만료 시간
            "iat": int(current_time.timestamp())  # 발급 시간
        }
    print("Access Token Payload:", payload)  # 디버깅: 생성된 payload 확인
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")
    return token

def create_jwt_google(provider: str, auth_info: dict = None, member_info: Member = None) -> str:
    """
    Access Token 생성 (사용자 정보 포함)
    """
    current_time = datetime.datetime.now()  # 현재 시간
    exp_time = current_time + datetime.timedelta(days=1)  # 1일 후 만료

    # 필요한 사용자 정보를 포함한 Access Token 생성
    if auth_info is not None:
        payload = {
            "iss": "EasyTravel",  # 발급자
            "sub": str(auth_info.get("id")),  # 사용자 식별자
            "provider": provider,  # 소셜 로그인 제공자
            "nickname": auth_info.get("name"),  # 닉네임
            "email": auth_info.get("email"),  # 이메일
            "profile_image": auth_info.get("picture"),  # 프로필 이미지
            "exp": int(exp_time.timestamp()),  # 만료 시간
            "iat": int(current_time.timestamp()),  # 발급 시간
            "roles": member_info.roles if member_info and member_info.roles else "USER"
        }
    if member_info is not None:
        payload = {
            "iss": "EasyTravel",  # 발급자
            "sub": str(member_info.id),  # 사용자 식별자
            "provider": str(member_info.oauth),  # 소셜 로그인 제공자
            "nickname": member_info.name,  # 닉네임
            "roles": member_info.roles if member_info and member_info.roles else "USER",
            "email": member_info.email,  # 이메일
            "profile_image": member_info.picture_url,  # 프로필 이미지
            "exp": int(exp_time.timestamp()),  # 만료 시간
            "iat": int(current_time.timestamp())  # 발급 시간
        }
    print("Access Token Payload:", payload)  # 디버깅: 생성된 payload 확인
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")
    return token
    

def decode_jwt_naver(token: str) -> dict:
    """
    JWT 디코딩 및 검증
    """
    try:
        # JWT 디코딩 및 검증
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def refresh_access_token(refresh_token: str) -> str:
    """
    리프레시 토큰으로 새 액세스 토큰 발급
    """
    try:
        # 리프레시 토큰 디코딩
        payload = decode_jwt(refresh_token)
        logger.info(f"💡[ jwt_utils ] refresh_access_token() payload : {payload}")
        logger.info(f"💡[ jwt_utils ] refresh_access_token() payload type : {type(payload)}")

        # TODO: 리프레시 토큰 검증

        # 새 액세스 토큰 생성 (python 3.10 이상)
        email = payload["data"]["sub"]
        provider = payload["data"]["provider"]
        logger.info(f"💡[ jwt_utils ] refresh_access_token() email : {email}")
        logger.info(f"💡[ jwt_utils ] refresh_access_token() provider : {provider}")

        # 수동 세션 획득
        session = await get_async_session_manual()
        member_info = await get_member_by_email_and_provider(email, provider, session)
        await session.commit();
        await session.close()

        match provider:
            case "naver":
                new_access_token = create_jwt_naver(provider=provider, member_info = member_info)
            case "kakao":
                new_access_token = create_jwt_kakao(provider=provider, member_info = member_info)
            case "google":
                new_access_token = create_jwt_google(provider=provider, member_info = member_info)

        return new_access_token
    except Exception as e:
        logger.error(f"[ jwt_utils ] refresh_access_token() 에러 : {e}")
        raise HTTPException(status_code=401, detail="올바르지 않은 리프레시 토큰입니다.")




