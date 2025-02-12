from sqlmodel import select
from app.data_models.data_model import Spot
from sqlmodel.ext.asyncio.session import AsyncSession

async def save_spot(spot: Spot, session: AsyncSession):
    try:
        session.add(spot)
        await session.flush()
        return spot.id
    except Exception as e:
        print("[ spotRepository ] save_spot() 에러 : ", e)
        raise e  # 예외 다시 던지기

async def get_spot(spot_id: int, session: AsyncSession) -> Spot:
    try:
        query = select(Spot).where(Spot.id == spot_id)
        result = await session.exec(query)
        spot = result.first()
        return spot if spot is not None else None
    except Exception as e:
        print("[ spotRepository ] get_spot() 에러 : ", e)
        raise e
    
async def delete_spot(spot_id: int, session: AsyncSession):
    try:
        query = select(Spot).where(Spot.id == spot_id)
        result = await session.exec(query)
        spot = result.first()
        await session.delete(spot)
        return spot.id
    except Exception as e:
        print("[ spotRepository ] delete_spot() 에러 : ", e)
        raise e

# 샘플 Spot 데이터
# {
#   "kor_name": "Test Spot",
#   "description": "A beautiful spot for testing",
#   "address": "123 Test Street",
#   "zip": "12345",
#   "url": "http://example.com",
#   "image_url": "http://example.com/image.jpg",
#   "map_url": "http://example.com/map",
#   "spot_category": 1,
#   "phone_number": "010-3333-9999",
#   "business_status": true,
#   "business_hours": "9:00-18:00"
# }    
  