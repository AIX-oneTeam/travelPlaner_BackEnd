from pydantic import BaseModel, Field
from typing import Optional


class spot_pydantic(BaseModel):
    kor_name: str = Field(max_length=255)
    eng_name: str = Field(default=None, max_length=255)
    description: str = Field(max_length=255)
    address: str = Field(max_length=255)
    url: str = Field(default=None, max_length=2083)
    image_url: str = Field(max_length=2083)
    map_url: str = Field(max_length=2083)
    latitude: float = None
    longitude: float = None
    spot_category: int
    phone_number: Optional[str] = Field(default=None, max_length=300)  # Optional로 변경
    business_status: Optional[bool] = None
    business_hours: Optional[str] = Field(default=None, max_length=255)
    
    order: int
    day_x: int
    spot_time: Optional[str] = Field(default="")

class spots_pydantic(BaseModel):
    spots: list[spot_pydantic]


