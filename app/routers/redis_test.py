from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from app.repository.redis_client import get_redis

router = APIRouter()

@router.get("/test")
async def test_redis(redis: Redis = Depends(get_redis)):
    # Redis에 key-value 저장
    await redis.set("test_key_again", "test_value_again")
    # Redis에서 값 조회
    value = await redis.get("test_key_again")
    return {"value": value}