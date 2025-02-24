from typing import Optional, List
from sqlmodel.ext.asyncio.session import AsyncSession
from app.data_models.data_model import SurveyResponse
from sqlalchemy.future import select

async def create_survey_response(session: AsyncSession, survey_data: dict) -> SurveyResponse:
    survey = SurveyResponse(**survey_data)
    session.add(survey)
    await session.commit()
    await session.refresh(survey)
    return survey

async def get_survey_response_by_id(session: AsyncSession, survey_id: int) -> Optional[SurveyResponse]:
    return await session.get(SurveyResponse, survey_id)

async def get_all_survey_responses(session: AsyncSession) -> List[SurveyResponse]:
    query = select(SurveyResponse)
    results = await session.exec(query)
    return results.all()
