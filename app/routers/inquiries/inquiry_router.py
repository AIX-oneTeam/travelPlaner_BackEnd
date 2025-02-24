from fastapi import APIRouter, HTTPException, Depends, Request, Body
from app.dtos.common.response import ErrorResponse, SuccessResponse
from sqlmodel.ext.asyncio.session import AsyncSession
from app.repository.db import get_async_session
from app.services.inquiries.inquiry_service import (
    create_inquiry,
    get_inquiry_service,
    get_all_inquiries_service,
    answer_inquiry,
    send_email,
)
from app.repository.members.mebmer_repository import get_memberId_by_email
from app.data_models.data_model import Inquiry
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter()


# 문의 등록 (사용자)
@router.post("")
async def create_inquiry_route(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    try:
        request_data = await request.json()
        title = request_data.get("title")
        content = request_data.get("content")

        if not title or not content:
            return ErrorResponse(
                message="제목과 내용을 모두 입력해야 합니다.", status_code=400
            )

        # 회원 ID 가져오기
        if request.state.user is not None:
            logger.info(f"request.state.user : {request.state.user}")
            member_email = request.state.user.get("email")
            provider = request.state.user.get("provider")
            member_id = await get_memberId_by_email(
                email=member_email, session=session, provider=provider
            )
        else:
            logger.info(
                f"[ inquiry_router ] request_data.email: {request_data.get('email')}"
            )
            member_id = await get_memberId_by_email(
                email=request_data.get("email"), session=session
            )
            logger.info(f"[ inquiry_router ] member_id: {member_id}")

        if member_id is None:
            return ErrorResponse(
                message="회원 정보를 찾을 수 없습니다.", status_code=404
            )

        # 문의 등록
        inquiry_id = await create_inquiry(
            inquiry_data={
                "title": title,
                "content": content,
            },
            member_id=member_id,
            session=session,
        )

        return SuccessResponse(
            data={"inquiry_id": inquiry_id}, message="문의가 성공적으로 등록되었습니다."
        )

    except Exception as e:
        logger.error(f"문의 등록 실패: {e}")
        return ErrorResponse(message="문의 등록에 실패했습니다.", error_detail=str(e))


# 관리자: 전체 문의 조회
@router.get("/admin/all")
async def read_all_inquiries(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    try:
        inquiries = await get_all_inquiries_service(session)

        if not inquiries:
            return SuccessResponse(
                data={"inquiries": []}, message="등록된 문의가 없습니다."
            )

        return SuccessResponse(
            data={"inquiries": inquiries}, message="문의 전체 조회 성공"
        )

    except Exception as e:
        logger.error(f"문의 전체 조회 실패: {e}")
        return ErrorResponse(
            message="문의 전체 조회에 실패했습니다.", error_detail=str(e)
        )


# 문의 조회 (단일)
@router.get("/{inquiry_id}")
async def read_inquiry(
    inquiry_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    try:
        print(f"💥💥 inquiry_id: {inquiry_id}")
        inquiry = await get_inquiry_service(inquiry_id, session)
        print(f"✅✅inquiry: {inquiry}")

        if not inquiry:
            return ErrorResponse(message="문의가 존재하지 않습니다.", status_code=404)

        return SuccessResponse(data={"inquiry": inquiry}, message="문의 조회 성공")

    except Exception as e:
        logger.error(f"문의 조회 실패: {e}")
        return ErrorResponse(message="문의 조회에 실패했습니다.", error_detail=str(e))


# 관리자: 문의에 답변 등록 + 사용자 이메일 발송
@router.put("/admin/answer/{inquiry_id}")
async def answer_inquiry_route(
    request: Request,  # non-default 파라미터를 앞으로
    inquiry_id: int,
    session: AsyncSession = Depends(get_async_session),
    answer: str = Body(..., embed=True),  # default 파라미터를 뒤로
):
    try:
        if request.state.user:
            member_email = request.state.user.get("email")
            provider = request.state.user.get("provider")
            member_id = await get_memberId_by_email(
                email=member_email, session=session, provider=provider
            )
        else:
            member_id = None

        updated_inquiry = await answer_inquiry(
            inquiry_id=inquiry_id, answer=answer, session=session
        )

        if not updated_inquiry:
            return ErrorResponse(message="문의가 존재하지 않습니다.", status_code=404)

        if member_id is not None:
            updated_inquiry["member_id"] = member_id

        return SuccessResponse(
            data={"inquiry_id": inquiry_id}, message="답변이 성공적으로 등록되었습니다."
        )

    except Exception as e:
        logger.error(f"문의 답변 등록 실패: {e}")
        return ErrorResponse(
            message="문의 답변 등록에 실패했습니다.", error_detail=str(e)
        )
