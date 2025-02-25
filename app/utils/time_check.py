import asyncio
from datetime import datetime
import logging
import time
from app.repository.db import async_session_maker  # 비동기 세션 팩토리
from app.repository.agents.agent_metrics_repository import save_execution_time_token

# 기존 파일 핸들러 설정
file_handler = logging.FileHandler(f"logs/time_check_{datetime.now().strftime('%Y-%m-%d')}.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)

def time_token_check(func):
    """함수의 실행시간,사용 토큰을 측정하고 DB에 저장하는 데코레이터 함수"""

    # 비동기 함수일 때
    if asyncio.iscoroutinefunction(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            result = await func(*args, **kwargs)
            end_time = time.time()
            execution_time = end_time - start_time
            minutes, seconds = divmod(execution_time, 60)
            logger.info(f"[ time_check ] 비동기 함수입니다 : {func.__name__} 함수 실행시간 : {int(minutes)}분 {seconds:.2f}초")

            token_usage = {}
            if isinstance(result, dict) and "token_usage" in result:
                token_usage = result["token_usage"]

            # 자동으로 DB에 실행시간 저장
            async with async_session_maker() as session:
                await save_execution_time_token(func.__name__, execution_time, token_usage, session)

            return result
        return wrapper
    else:
        # 동기 함수일 때
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)

            end_time = time.time()
            execution_time = end_time - start_time

            minutes, seconds = divmod(execution_time, 60)

            logger.info(f"[ time_check ] 동기 함수입니다 : {func.__name__} 함수 실행시간 : {int(minutes)}분 {seconds:.2f}초")
            return result

        return wrapper

