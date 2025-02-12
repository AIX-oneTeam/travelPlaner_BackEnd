from fastapi import Depends
from app.repository.regions.region_repository import (
    get_all_divisions,
)
from sqlmodel.ext.asyncio.session import AsyncSession

# 모든 행정구역 데이터 가져오기
async def get_all_divisions_service(session: AsyncSession):
    return await get_all_divisions(session)
