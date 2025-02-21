
from typing import List
from sqlmodel import Session
from app.data_models.data_model import Spot
from app.repository.spots.spot_repository import delete_spot, save_spot, get_spot
from datetime import datetime
from app.utils.serialize_time import serialize_time
from sqlmodel.ext.asyncio.session import AsyncSession

import logging
logger = logging.getLogger(__name__)

async def reg_spot(spot: Spot, session: AsyncSession):
    logger.info(f"💡[ spot_service ] reg_spot() 호출 : {spot}")
    spot_id = await save_spot(spot, session)
    return spot_id

async def find_spot(spot_id: int, session: AsyncSession):
    spot = await get_spot(spot_id, session)
    serialized_spot = serialize_time(spot,  ["created_at", "updated_at"])
    return serialized_spot