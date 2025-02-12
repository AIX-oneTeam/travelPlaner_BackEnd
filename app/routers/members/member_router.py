from fastapi import APIRouter, Depends, Response
from app.dtos.common.response import ErrorResponse, SuccessResponse
from app.services.plans.plan_service import find_member_plans

router = APIRouter()

@router.get("/logout")
async def logout(response: Response):
    """
    로그아웃 처리: 쿠키 삭제
    """
    response.delete_cookie(key="access_token", secure=False, samesite="None", httponly=True)
    response.delete_cookie(key="refresh_token", secure=False, samesite="None", httponly=True)
    print("로그아웃 되었습니다.")
    return {"message": "로그아웃 되었습니다."}




