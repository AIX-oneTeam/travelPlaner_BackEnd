from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from app.repository.redis_client import get_redis
from pydantic import BaseModel
router = APIRouter()

# 테스트 데이터 모델
class RedisItem(BaseModel):
    key: str
    value: str
    expires_in: Optional[int] = None  # 만료 시간(초)

# Post 테스트
@router.post("/items")
async def create_item(
    item: RedisItem,
    redis: Redis = Depends(get_redis)
):
    # 이미 존재하는 키인지 확인
    exists = await redis.exists(item.key)
    if exists:
        raise HTTPException(
            status_code=400,
            detail="Key already exists"
        )
    
    if item.expires_in:
        # 만료 시간이 설정된 경우
        await redis.set(
            item.key,
            item.value,
            ex=item.expires_in
        )
    else:
        # 만료 시간이 없는 경우
        await redis.set(item.key, item.value)
    
    return {
        "message": "Successfully created",
        "key": item.key,
        "value": item.value
    }

# 테스트 GET
@router.get("/items/{key}")
async def read_item(
    key: str,
    redis: Redis = Depends(get_redis)
):
    value = await redis.get(key)
    if value is None:
        raise HTTPException(
            status_code=404,
            detail="Key not found"
        )
    
    # 만료까지 남은 시간 확인 (초)
    ttl = await redis.ttl(key)
    
    return {
        "key": key,
        "value": value,
        "ttl": ttl if ttl > 0 else None
    }

# 테스트 Update 
@router.put("/items/{key}")
async def update_item(
    key: str,
    item: RedisItem,
    redis: Redis = Depends(get_redis)
):
    # 키가 존재하는지 확인
    exists = await redis.exists(key)
    if not exists:
        raise HTTPException(
            status_code=404,
            detail="Key not found"
        )
    
    if item.expires_in:
        await redis.set(
            key,
            item.value,
            ex=item.expires_in
        )
    else:
        await redis.set(key, item.value)
    
    return {
        "message": "Successfully updated",
        "key": key,
        "value": item.value
    }

# 테스트 Delete 
@router.delete("/items/{key}")
async def delete_item(
    key: str,
    redis: Redis = Depends(get_redis)
):
    # 키가 존재하는지 확인
    exists = await redis.exists(key)
    if not exists:
        raise HTTPException(
            status_code=404,
            detail="Key not found"
        )
    
    await redis.delete(key)
    return {"message": f"Successfully deleted key: {key}"}

# 모든 키 조회 (List)
@router.get("/items")
async def list_items(
    pattern: str = "*",
    redis: Redis = Depends(get_redis)
):
    keys = await redis.keys(pattern)
    items = []
    
    for key in keys:
        value = await redis.get(key)
        ttl = await redis.ttl(key)
        items.append({
            "key": key,
            "value": value,
            "ttl": ttl if ttl > 0 else None
        })
    
    return {"items": items}