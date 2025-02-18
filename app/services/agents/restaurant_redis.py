from typing import List, Optional
import json
from datetime import timedelta
import logging
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class RestaurantRedisService:
    """Redis를 활용한 식당 추천 관리 서비스"""

    KEY_PREFIX = "recommended_restaurants:"
    EXPIRATION_HOURS = 1  # 1시간 후 자동 삭제

    def __init__(self, redis: Redis):
        """
        생성자에서 Redis 인스턴스를 주입받습니다.
        :param redis: 의존성 주입된 Redis 인스턴스
        """
        self.redis = redis

    def _generate_key(self, member_id: Optional[int], main_location: str) -> str:
        """Redis 키 생성
        Args:
            member_id: 사용자 ID (Optional)
            main_location: 위치 정보 (예: "부산광역시 - 해운대구")
        """
        if member_id:
            return f"{self.KEY_PREFIX}member:{member_id}:{main_location}"
        return f"{self.KEY_PREFIX}location:{main_location}"

    async def add_recommended_restaurants(
        self,
        restaurants: List[dict],
        main_location: str,
        member_id: Optional[int] = None,
    ) -> None:
        """추천된 식당 목록을 Redis에 저장"""
        try:
            # 의존성 주입된 Redis 인스턴스를 사용합니다.
            redis_client: Redis = self.redis
            key = self._generate_key(member_id, main_location)
            # spots 배열에서 식당 이름만 추출
            restaurant_names = restaurants

            # 기존 데이터가 있다면 합치기
            existing_data = await redis_client.get(key)
            if existing_data:
                existing_names = json.loads(existing_data)
                restaurant_names = list(set(existing_names + restaurant_names))

            # 새로운 데이터 저장
            await redis_client.set(
                key,
                json.dumps(restaurant_names),
                ex=timedelta(hours=self.EXPIRATION_HOURS).seconds,
            )
            logger.info(
                f"🟣 Redis에 저장된 식당 수: {len(restaurant_names)}, Key: {key}"
            )
            print(f"🟣 Redis에 저장된 식당: {restaurant_names}")
            logger.info(f"🟣 Redis에 저장된 식당: {restaurant_names}")
            print(f"🟣 Redis에 저장된 식당 수: {len(restaurant_names)}, Key: {key}")
        except Exception as e:
            logger.error(f"🟣 Redis 저장 중 오류 발생 - Key: {key}, Error: {e}")
            raise

    async def get_excluded_restaurants(
        self, main_location: str, member_id: Optional[int] = None
    ) -> List[str]:
        """Redis에 저장된 추천 식당 목록 조회"""
        try:
            redis_client: Redis = self.redis
            key = self._generate_key(member_id, main_location)

            data = await redis_client.get(key)
            excluded_restaurants = json.loads(data) if data else []
            logger.info(
                f"🟣 Redis에서 조회된 제외 식당 수: {len(excluded_restaurants)}, Key: {key}"
            )
            print(f"🟣 Redis에서 조회된 제외 식당: {excluded_restaurants}")
            return excluded_restaurants
        except Exception as e:
            logger.error(f"🟣 Redis 조회 중 오류 발생 - Key: {key}, Error: {e}")
            return []

    async def clear_restaurants(
        self, main_location: str, member_id: Optional[int] = None
    ) -> None:
        """특정 위치에 대한 추천 식당 목록 삭제"""
        try:
            redis_client: Redis = self.redis
            key = self._generate_key(member_id, main_location)

            await redis_client.delete(key)
            logger.info(f"🟣 Redis 데이터 삭제 완료 - Key: {key}")
            print(f"🟣 Redis 데이터 삭제 완료 - Key: {key}")
        except Exception as e:
            logger.error(f"🟣 Redis 데이터 삭제 중 오류 발생 - Key: {key}, Error: {e}")
            raise
