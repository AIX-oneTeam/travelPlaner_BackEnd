import asyncio
from datetime import datetime
import logging
import time

file_handler = logging.FileHandler(f"logs/time_check_{datetime.now().strftime('%Y-%m-%d')}.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)

def time_check(func):
    """_summary_
    Args:
        func (_type_): 측정 하고 싶은 함수 입력
    Description:
        함수의 실행시간을 측정하는 데코레이터 함수
    """

    # 비동기 함수일 때
    if asyncio.iscoroutinefunction(func):

        async def wrapper(*args, **kwargs):
            start_time = time.time()
            result = await func(*args, **kwargs)

            end_time = time.time()
            execution_time = end_time - start_time

            minutes, seconds = divmod(execution_time, 60)

            logger.info(f"[ time_check ] 비동기 함수입니다 : {func.__name__} 함수 실행시간 : {int(minutes)}분 {seconds:.2f}초")
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

