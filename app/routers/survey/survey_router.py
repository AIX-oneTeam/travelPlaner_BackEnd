from fastapi import APIRouter, HTTPException, Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from app.data_models.data_model import SurveyResponse
from app.repository.db import get_async_session
from app.repository.members.mebmer_repository import get_memberId_by_email
from app.dtos.common.response import SuccessResponse, ErrorResponse
import traceback
import logging

router = APIRouter()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 설문 응답 등록 (사용자)
@router.post("")
async def create_survey_response_route(
    survey: SurveyResponse,
    request: Request,
    session: AsyncSession = Depends(get_async_session)
):
    try:
        # 사용자 인증 정보에서 이메일 추출
        if request.state.user:
            member_email = request.state.user.get("email")
            provider = request.state.user.get("provider")
            member_id = await get_memberId_by_email(
                email=member_email, session=session, provider=provider
            )
        else:
            raise HTTPException(status_code=401, detail="인증 정보가 필요합니다.")

        # 설문 응답 객체에 회원 ID 설정
        survey.member_id = member_id

        # DB에 설문 응답 저장
        session.add(survey)
        await session.commit()
        await session.refresh(survey)

        return SuccessResponse(
            data={"survey_id": survey.id},
            message="설문 응답이 성공적으로 저장되었습니다."
        )
    except Exception as e:
        traceback.print_exc()
        logger.error(f"설문 응답 등록 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# 설문 응답 단일 조회 (관리자)
@router.get("/{survey_id}")
async def read_survey_response(
    survey_id: int,
    session: AsyncSession = Depends(get_async_session)
):
    try:
        survey = await session.get(SurveyResponse, survey_id)
        if not survey:
            raise HTTPException(status_code=404, detail="설문 응답이 존재하지 않습니다.")
        return SuccessResponse(
            data={"survey": survey},
            message="설문 응답 조회 성공"
        )
    except Exception as e:
        logger.error(f"설문 응답 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# 전체 설문 응답 조회 (관리자)
@router.get("/all")
async def read_all_survey_responses(
    session: AsyncSession = Depends(get_async_session)
):
    try:
        surveys_result = await session.exec(select(SurveyResponse))
        surveys = surveys_result.all()
        return SuccessResponse(
            data={"surveys": surveys},
            message="전체 설문 응답 조회 성공"
        )
    except Exception as e:
        logger.error(f"전체 설문 응답 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
