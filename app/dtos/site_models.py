from pydantic import BaseModel
from typing import List, Optional


class TouristSite(BaseModel):
    placeId: str
    kor_name: str
    eng_name: Optional[str] = None
    address: str
    url: Optional[str] = None
    image_url: str
    map_url: str
    spot_category: int
    phone_number: Optional[str] = None
    business_status: Optional[bool] = None
    business_hours: Optional[str] = None
    latitude: float = None
    longitude: float = None


class TouristSiteList(BaseModel):
    spots: List[TouristSite]
