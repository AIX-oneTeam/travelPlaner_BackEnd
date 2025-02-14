from pydantic import BaseModel
from typing import List

# 체크리스트 항목 단일 모델
class Checklist(BaseModel):
    plan_id: int
    item: str
    checked: int

# 여러 체크리스트 항목을 받을 때 사용
class ChecklistListCreate(BaseModel):
    items: List[Checklist]


class PlanId(BaseModel):
    plan_id : int

