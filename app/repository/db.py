from contextlib import asynccontextmanager
import logging
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from typing import AsyncGenerator

# 환경 변수 로드
print("--------------------db.py---------------------")
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# 비동기 엔진 생성
engine = create_async_engine(DATABASE_URL, echo=True)

# 비동기 세션 팩토리 생성
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting application...")
    
    # 데이터베이스 연결 초기화
    app.state.engine = engine

    try:
        yield
    finally:
        print("Shutting down application...")
        await engine.dispose()
        print("Database connection closed.")

# 의존성 주입을 위한 비동기 세션 제공자
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            logging.info(f"💡[ 세션 생성 ] {session}")
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logging.error(f"Database error: {str(e)}")
            raise
        finally:
            logging.info(f"💡[ 세션 종료 ] {session}")
            await session.close()

# 동기식 연결
# SQLAlchemy 세션을 생성하고 반환하는 제너레이터 - deprecated
# def get_session_sync():
#     session = SessionLocal()
#     try:
#         frame = inspect.stack()[2]
#         filename = frame.filename
#         function_name = frame.function
#         print(f"💡[ 세션 생성 ] {filename} - {function_name}")

#         yield session
#         session.commit()
#     except Exception as e:
#         logging.debug(f"💡logger: 데이터 베이스 예외 발생: {e}")
#         session.rollback()
#         raise RuntimeError("데이터베이스 연결 실패") from e
#     finally:
#         print(f"💡[ 세션 종료 ] {filename} - {function_name}")

#         session.close()

# 테이블 초기화 함수
async def init_table_by_SQLModel():
    async with engine.begin() as conn:
        # 기존 테이블 삭제
        await conn.run_sync(SQLModel.metadata.drop_all)
        print("테이블을 삭제했습니다.")
        
        # 새 테이블 생성
        await conn.run_sync(SQLModel.metadata.create_all)
        print("테이블을 생성했습니다.")
        
        # CSV 데이터 삽입
        try:
            import pandas as pd
            data = pd.read_csv('administrative_division.csv')
            await conn.run_sync(
                lambda sync_conn: data.to_sql(
                    'administrative_division',
                    con=sync_conn,
                    if_exists='append',
                    index=False
                )
            )
            print(f"총 {len(data)}개의 행 삽입 완료.")
        except Exception as e:
            print(f"CSV 데이터 삽입 실패: {e}")

# 테이블 존재 여부 확인
async def check_tables():
    print("---------메타데이터 테이블 목록---------")
    print(SQLModel.metadata.tables)
    print("--------------------------------------")

if __name__ == "__main__":
    print("MySQL 연결 테스트를 시작합니다...")
    try:

        load_dotenv()
        DATABASE_URL = os.getenv("DATABASE_URL")
        engine = create_engine(DATABASE_URL, echo=True)
        # 엔진으로 직접 연결 테스트
        with engine.connect() as connection:
            print("MySQL 연결 성공!")

            print("테이블 목록을 출력합니다.")
            result = connection.execute(text("SHOW TABLES;"))

            for row in result:
                print(row)
    except Exception as e:
        print(f"MySQL 연결 실패: {e}")

