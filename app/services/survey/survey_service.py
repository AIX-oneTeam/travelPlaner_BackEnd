from typing import Optional, List
from sqlmodel.ext.asyncio.session import AsyncSession
from app.data_models.data_model import SurveyResponse
from app.repository.survey.survey_repository import (
    create_survey_response,
    get_survey_response_by_id,
    get_all_survey_responses,
)


async def create_survey_response_service(
    survey_data: dict, session: AsyncSession
) -> SurveyResponse:
    """
    설문 응답 데이터를 기반으로 새 설문 응답을 생성하고 DB에 저장합니다.
    추가적인 비즈니스 로직이 필요한 경우 이 함수에서 처리할 수 있습니다.
    """
    survey = await create_survey_response(session, survey_data)
    return survey


async def get_survey_response_service(
    survey_id: int, session: AsyncSession
) -> Optional[SurveyResponse]:
    """
    주어진 ID에 해당하는 설문 응답을 조회합니다.
    """
    survey = await get_survey_response_by_id(session, survey_id)
    return survey


async def get_all_survey_responses_service(
    session: AsyncSession,
) -> List[SurveyResponse]:
    """
    전체 설문 응답 목록을 조회합니다.
    """
    surveys = await get_all_survey_responses(session)
    return surveys
