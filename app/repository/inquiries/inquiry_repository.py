from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from app.data_models.data_model import Inquiry
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

# KST = UTC+9
kst = timezone(timedelta(hours=9))


# 문의 조회 (단일)
async def get_inquiry(inquiry_id: int, session: AsyncSession):
    query = select(Inquiry).where(Inquiry.inquiry_id == inquiry_id)
    result = await session.scalars(query)
    inquiry = result.one_or_none()

    if inquiry:
        return {
            "inquiry_id": inquiry.inquiry_id,
            "member_id": inquiry.member_id,
            "title": inquiry.title,
            "content": inquiry.content,
            "answer": inquiry.answer,
            "status": inquiry.status,
            "created_at": inquiry.created_at.isoformat(),
            "updated_at": inquiry.updated_at.isoformat(),
            "answered_at": (
                inquiry.answered_at.isoformat() if inquiry.answered_at else None
            ),
        }
    return None


# 문의 조회 (전체 조회 - 관리자용)
async def get_all_inquiries(session: AsyncSession):
    query = select(Inquiry).order_by(Inquiry.inquiry_id.desc())
    result = await session.scalars(query)
    inquiries = result.all()

    return [
        {
            "inquiry_id": inq.inquiry_id,
            "member_id": inq.member_id,
            "title": inq.title,
            "content": inq.content,
            "answer": inq.answer,
            "status": inq.status,
            "created_at": inq.created_at.isoformat(),
            "updated_at": inq.updated_at.isoformat(),
            "answered_at": inq.answered_at.isoformat() if inq.answered_at else None,
        }
        for inq in inquiries
    ]


# 관리자 답변 저장
async def save_answer(inquiry: Inquiry, answer: str, session: AsyncSession):
    # 'answer' 필드와 상태 업데이트
    inquiry.answer = answer
    inquiry.status = "answered"
    inquiry.answered_at = datetime.now(kst)

    # DB에 변경사항 반영
    await session.commit()

    # 변경된 inquiry 객체를 refresh하여 최신 데이터 반영
    await session.refresh(inquiry)

    return {
        "inquiry_id": inquiry.inquiry_id,
        "member_id": inquiry.member_id,
        "title": inquiry.title,
        "content": inquiry.content,
        "answer": inquiry.answer,
        "status": inquiry.status,
        "created_at": inquiry.created_at.isoformat(),
        "updated_at": inquiry.updated_at.isoformat(),
        "answered_at": inquiry.answered_at.isoformat() if inquiry.answered_at else None,
    }
