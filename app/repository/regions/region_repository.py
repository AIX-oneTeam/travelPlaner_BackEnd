from sqlmodel import select
from app.data_models.data_model import AdministrativeDivision
from sqlmodel.ext.asyncio.session import AsyncSession

# 모든 행정구역 데이터 가져오기
async def get_all_divisions(session: AsyncSession):
    try:
        statement = select(AdministrativeDivision)
        results = await session.exec(statement)
        divisions = results.all()
        return [
            {"city_province": d.city_province, "city_county": d.city_county}
            for d in divisions
        ]
    except Exception as e:
        print("[ administrativeDivisionRepository ] get_all_divisions() 에러 : ", e)
        return []
