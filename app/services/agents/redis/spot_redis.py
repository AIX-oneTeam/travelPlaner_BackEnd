from typing import List, Optional
from enum import Enum
import logging
import json
from redis.asyncio import Redis
from datetime import timedelta

logger = logging.getLogger(__name__)


class SpotCategory(str, Enum):
    CAFE = "cafe"
    RESTAURANT = "restaurant"
    SITE = "site"
    ACCOMMODATION = "accommodation"


class SpotRedisService:
    """Redis를 활용한 범용 장소 관리 서비스"""

    EXPIRATION_HOURS = 5 / 60  # 5분

    def __init__(self, redis_client: Redis):
        """
        생성자에서 Redis 인스턴스를 주입받습니다.
        :param redis: 의존성 주입된 Redis 인스턴스
        """
        self.redis = redis_client

    def _generate_key(self, category: SpotCategory) -> str:
        """Redis 키 생성
        Args:
            category: 장소 카테고리
        """
        return category.value

    async def add_spots(
        self, category: SpotCategory, main_location: str, spots: List[str]
    ) -> None:
        """새로운 장소들을 Hash의 field에 Set으로 추가"""
        try:
            # 전달 받은 데이터 확인
            logger.info(f"🟣 Received spots data: {spots}")
            logger.info(f"🟣 Location: {main_location}")
            logger.info(f"🟣 Category: {category}")

            key = self._generate_key(category)

            # Redis 연결 확인
            await self.redis.ping()
            logger.info("Redis connection successful")

            # 현재 field(main_location)에 저장된 데이터 가져오기
            current_data = await self.redis.hget(key, main_location)
            current_spots = set(json.loads(current_data)) if current_data else set()

            # 새로운 spots 추가 (자동 중복 제거)
            updated_spots = current_spots.union(set(spots))

            # Hash에 저장
            await self.redis.hset(key, main_location, json.dumps(list(updated_spots)))

            # 만료 시간 설정
            await self.redis.expire(key, timedelta(hours=self.EXPIRATION_HOURS).seconds)

            # redis 저장 완료 확인
            logger.info(
                f"🟣 Redis에 저장된 장소 수: {len(updated_spots)}, Key: {key}, Field: {main_location}"
            )
            logger.info(f"🟣 Redis에 저장된 장소들: {updated_spots}")

        except Exception as e:
            logger.error(
                f"Redis 저장 중 오류 발생 - Key: {key}, Field: {main_location}, Error: {e}"
            )
            raise

    async def get_spots(self, category: SpotCategory, main_location: str) -> List[str]:
        """Redis Hash에서 특정 field의 장소 목록 조회"""
        try:
            key = self._generate_key(category)

            # Hash에서 특정 field 데이터 조회
            data = await self.redis.hget(key, main_location)
            spots_list = json.loads(data) if data else []

            # 조회된 데이터 확인
            logger.info(
                f"🟣 Redis에서 조회된 장소 수: {len(spots_list)}, "
                f"Key: {key}, Field: {main_location}"
            )
            return spots_list

        except Exception as e:
            logger.error(
                f"Redis 조회 중 오류 발생 - Key: {key}, Field: {main_location}, Error: {e}"
            )
            return []

    async def clear_spots(self, category: SpotCategory, main_location: str) -> None:
        """특정 카테고리의 특정 field 삭제"""
        try:
            key = self._generate_key(category)

            # Hash에서 특정 field 삭제
            await self.redis.hdel(key, main_location)
            logger.info(
                f"🟣 Redis 데이터 삭제 완료 - Key: {key}, Field: {main_location}"
            )

        except Exception as e:
            logger.error(
                f"Redis 데이터 삭제 중 오류 발생 - Key: {key}, Field: {main_location}, "
                f"Error: {e}"
            )
            raise


# 사용 예시:
"""
redis_service = SpotRedisService(redis_client)

# 식당 추가
await redis_service.add_spots(
    category=SpotCategory.RESTAURANT,
    mian_location="부산광역시 - 해운대구",
    spots=["맛있는 식당", "좋은 식당"]
)

# 식당 조회
restaurants = await redis_service.get_spots(
    category=SpotCategory.RESTAURANT,
    main_location="부산광역시 - 해운대구"
)

# 식당 목록 삭제
await redis_service.clear_spots(
    category=SpotCategory.RESTAURANT,
    main_location="부산광역시 - 해운대구"
)
"""
