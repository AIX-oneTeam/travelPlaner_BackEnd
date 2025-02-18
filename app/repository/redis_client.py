import logging
from typing import Optional
from redis.asyncio import Redis
from redis.exceptions import ConnectionError
from fastapi import FastAPI

import os
from dotenv import load_dotenv
load_dotenv()
REDIS_URL = os.getenv("REDIS_URL")

logger = logging.getLogger(__name__)

# 전역 변수로 Redis 클라이언트 관리
redis_client: Optional[Redis] = None

async def init_redis(app: FastAPI) -> None:
    """Redis 연결을 초기화하는 함수"""
    global redis_client
        
    try:
        redis_client = Redis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        await redis_client.ping()
        logger.info("Redis 연결 성공")
        
        # FastAPI 앱에 Redis 클라이언트 저장
        app.state.redis = redis_client
        
    except ConnectionError as e:
        logger.error(f"Redis 연결 실패: {str(e)}")
        raise

async def close_redis() -> None:
    """Redis 연결을 종료하는 함수"""
    global redis_client
    
    if redis_client:
        await redis_client.close()
        logger.info("Redis 연결 종료")
        redis_client = None

async def get_redis_client() -> Redis:
    """현재 Redis 클라이언트를 반환하는 함수"""
    if not redis_client:
        raise ConnectionError("Redis client is not initialized")
    return redis_client

# FastAPI 의존성 주입을 위한 함수
async def get_redis() -> Redis:
    """의존성 주입을 위한 Redis 클라이언트 제공 함수"""
    return await get_redis_client()
