from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from app.repository.redis_client import get_redis
from pydantic import BaseModel
import redis.asyncio as aioredis
router = APIRouter()

import redis
import json

# 데이터 모델
class RecommendationItem(BaseModel):
    category: str  # 호텔, 관광지, 맛집, 카페 중 하나
    name: List[str]  # ✅ 리스트로 저장할 값

async def save_category(redis, member_id, main_location, category, name):
    key = f"member:{member_id}:{main_location}"  # 🔥 모든 데이터를 이 키에 저장!
    
    # 기존 데이터 가져오기
    all_categories = await redis.hgetall(key)
    
    # 새로운 카테고리 데이터 추가
    all_categories[category] = json.dumps(name, ensure_ascii=False)
    
    # 업데이트된 데이터 저장
    await redis.hset(key, mapping=all_categories)


# 🔥 POST: 장소 저장
router = APIRouter()

@router.post("/recommendations/{member_id}/{main_location}", response_model=None)
async def add_recommendation(
    member_id: str,
    main_location: str,
    item: RecommendationItem,
    redis = Depends(get_redis)  # ✅ 타입 제거
):
    if item.category not in ["호텔", "관광지", "맛집", "카페"]:
        raise HTTPException(status_code=400, detail="Invalid category")

    await save_category(redis, member_id, main_location, item.category, item.name)
    
    return {
        "message": "Successfully added recommendation",
        "member_id": member_id,
        "main_location": main_location,
        "category": item.category,
        "name": item.name
    }

# 🔥 GET: 통합 조회
@router.get("/recommendations/{member_id}/{main_location}", response_model=None)
async def get_recommendations(
    member_id: str,
    main_location: str,
    redis = Depends(get_redis)  # ✅ 타입 제거
):
    key = f"member:{member_id}:{main_location}"
    data = await redis.hgetall(key)
    if not data:
        raise HTTPException(status_code=404, detail="No recommendations found")
    
    # ✅ JSON 문자열을 리스트로 디코딩
    decoded_data = {
        k: json.loads(v) if v.startswith('[') else v
        for k, v in data.items()
    }
    return decoded_data

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