from typing import List, Optional
from enum import Enum
import logging
import json
from redis.asyncio import Redis
from datetime import timedelta

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

"""
에이전트가 찾은 장소 Redis 저장, 조회
category: site, accommodation, restaurant, cafe
"""

class SpotCachingService:
    """Redis를 활용한 장소 관리 서비스"""

    EXPIRATION_HOURS = 60*60*24 #하루

    def __init__(self, redis_client: Redis):
        """
        생성자에서 Redis 인스턴스를 주입받습니다.
        :param redis: 의존성 주입된 Redis 인스턴스
        """
        self.redis = redis_client
                
    async def add_spots(self, category:str, main_location:str, spots: dict) -> None:
        try:
            # Redis 연결 확인
            await self.redis.ping()
            logger.info("Redis connection successful")
            # 전달 받은 데이터 확인
            logger.info(f"🟣 캐싱 ---- Received spots data: {spots}")
            logger.info(f"🟣 캐싱 ---- Location: {main_location}")
            logger.info(f"🟣 캐싱 ---- Category: {category}")

            key = f"{category}:{main_location}"
            added_count = 0

            for spot in spots.get("spots", []):
                spot_json = json.dumps(spot)  # JSON 문자열 변환
                added = await self.redis.sadd(key, spot_json)  # Redis SET에 추가            
                if added:  
                    added_count += 1

            await self.redis.expire(key, self.EXPIRATION_HOURS)
            logger.info(f"🟣 [CachingSpots] - {added_count}개의 새로운 {category} 추가 완료. ")

        except Exception as e:
            logger.error(f"🟣 [CachingSpots] - add_spot : 저장 중 오류 발생: {str(e)}")
            raise
        
    async def get_spots(self, category:str, main_location: str):
        key = f"{category}:{main_location}"
        spots = await self.redis.smembers(key)  # Redis SET에서 모든 값 가져오기
        return [json.loads(spot) for spot in spots]  # JSON을 다시 dict로 변환

