
from typing import List
from sqlmodel import Session
from app.data_models.data_model import Spot
from app.repository.spots.spot_repository import delete_spot, save_spot, get_spot
from datetime import datetime
from app.utils.serialize_time import serialize_time
from sqlmodel.ext.asyncio.session import AsyncSession

async def reg_spot(spot: Spot, session: AsyncSession):
    spot_id = await save_spot(spot, session)
    return spot_id

async def find_spot(spot_id: int, session: AsyncSession):
    spot = await get_spot(spot_id, session)
    serialized_spot = serialize_time(spot,  ["created_at", "updated_at"])
    return serialized_spot

# # 이미 존재하는 장소인지 확인
# # 이미 존재하면서 요청 데이터에도 존재하면 내버려둠.
# # 이미 존재하면서 요청 데이터에는 없으면 삭제
# # 이미 존재하지 않으면서 요청 데이터에도 없으면 추가
# def edit_spot(plan_id: int, spots: List[spot_request], session: AsyncSession) -> List[int]:
#     plan_spots = find_plan_spots(plan_id, session)
#     spots_from_db = plan_spots["detail"]

#     # 반환될 id 리스트
#     spots_ids: List[int] = [spot["spot"].id for spot in spots_from_db]

#     # db에서 가져온 장소 이름 뽑아내기
#     spot_names_from_db: List[str] = [spot["spot"].kor_name for spot in spots_from_db]
#     print("[spot_service] spot_names: ", spot_names_from_db)

#     # 요청 데이터에서 장소 이름 뽑아내기
#     spot_names_from_request: List[str] = [spot.kor_name for spot in spots]
#     print("[spot_service] spot_names_from_request: ", spot_names_from_request)

#     # db 데이터에서 삭제될 장소 이름 추출
#     spots_to_delete: List[str] = [spot_name for spot_name in spot_names_from_db if spot_name not in spot_names_from_request]
#     print("[spot_service] spots_to_delete: ", spots_to_delete)

#     # 요청 데이터에서 추가될 장소 이름 추출
#     spots_to_add: List[str] = [spot_name for spot_name in spot_names_from_request if spot_name not in spot_names_from_db]
#     print("[spot_service] spots_to_add: ", spots_to_add)


#     # 삭제될 장소 삭제
#     # TODO: 한번에 삭제 가능한지 알아보기 
#     for spot_name in spots_to_delete:
#         spot_for_delete = [spot for spot in spots_from_db if spot["spot"].kor_name == spot_name]
#         deleted_spot_id = delete_spot(spot_for_delete[0]["spot"].id, session)
#         spots_ids.remove(deleted_spot_id)

#     # 추가될 장소 추가
#     for spot_name in spots_to_add:
#         spot_for_add_preprocess = [spot for spot in spots if spot.kor_name == spot_name]
#         spot_for_add_postprocess = Spot(**spot_for_add_preprocess[0].model_dump(exclude={"order", "day_x", "spot_time"}))
#         save_spot(spot_for_add_postprocess, session)
#         spots_ids.append(spot_for_add_postprocess.id)
    
#     # 남아있는 장소 아이디 반환
#     return spots_ids






    

