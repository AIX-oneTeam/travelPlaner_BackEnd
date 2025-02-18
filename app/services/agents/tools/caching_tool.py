from crewai.tools import BaseTool
import os
from dotenv import load_dotenv
from redis import Redis

load_dotenv()


class RedisCachingTool(BaseTool):
    name: str = "RedisCachingTool"
    description: str = "Redis에 데이터를 캐싱하는 도구"
    
    def cache_data(self, key: str, value: str, redis_client: Redis) -> str:
        try:
            redis_client.set(key, value)
            return f"Redis에 데이터를 캐싱했습니다. {key}: {value}"
        except Exception as e:
            return f"Redis에 데이터를 캐싱하는 중 오류가 발생했습니다. {e}"
    
    def find_data(self, key: str, redis_client: Redis) -> str:
        try:
            value = redis_client.get(key)
            return f"Redis에서 데이터를 찾았습니다. {key}: {value}"
        except Exception as e:
            return f"Redis에서 데이터를 찾는 중 오류가 발생했습니다. {e}"
    
    
    