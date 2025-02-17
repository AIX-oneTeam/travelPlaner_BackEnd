import asyncio
import logging
import time

logger = logging.getLogger(__name__)

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

            # 분 단위로 변환
            execution_time_minute = execution_time / 60
            # 초 측정
            execution_time_second = execution_time % 60

            # 포매팅
            execution_time_minute = round(execution_time_minute, 2)
            execution_time_second = round(execution_time_second, 2)

            logger.info(f"💡[ time_check ] 비동기 함수입니다 : {func.__name__} 함수 실행시간 : {execution_time_minute}분 {execution_time_second}초")
            return result
        return wrapper
    else:
        # 동기 함수일 때
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)

            end_time = time.time()
            execution_time = end_time - start_time

            # 분 단위로 변환
            execution_time_minute = execution_time / 60
            # 초 측정
            execution_time_second = execution_time % 60

            # 포매팅
            execution_time_minute = round(execution_time_minute, 2)
            execution_time_second = round(execution_time_second, 2)

            logger.info(f"💡[ time_check ] 동기 함수입니다 : {func.__name__} 함수 실행시간 : {execution_time_minute}분 {execution_time_second}초")
            return result

        return wrapper

