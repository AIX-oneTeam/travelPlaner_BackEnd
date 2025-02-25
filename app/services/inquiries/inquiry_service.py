from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from app.data_models.data_model import Inquiry, Member
from app.repository.inquiries.inquiry_repository import (
    get_inquiry,
    get_all_inquiries,
    save_answer,
)
from datetime import datetime, timezone, timedelta
import logging
import smtplib
from dotenv import load_dotenv
import os

load_dotenv()

# 이메일 발송을 위한 계정 정보
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "dud9902@gmail.com"  # 발신자 이메일 입력
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

logger = logging.getLogger(__name__)

# KST = UTC+9
kst = timezone(timedelta(hours=9))

# 문의 등록 (사용자가 문의 작성)
async def create_inquiry(inquiry_data: dict, member_id: int, session: AsyncSession):
    try:
        current_time = datetime.now(kst)

        new_inquiry = Inquiry(
            member_id=member_id,
            title=inquiry_data["title"],
            content=inquiry_data["content"],
            status="pending",
            created_at=current_time,
            updated_at=current_time,
        )
        session.add(new_inquiry)
        await session.commit()
        await session.refresh(new_inquiry)
        return new_inquiry.inquiry_id
    except Exception as e:
        logger.error(f"문의 등록 실패: {e}")
        raise e


# 문의 조회 (단일)
async def get_inquiry_service(inquiry_id: int, session: AsyncSession):
    return await get_inquiry(inquiry_id, session)


# 문의 조회 (전체 조회 - 관리자용)
async def get_all_inquiries_service(session: AsyncSession):
    return await get_all_inquiries(session)


# 관리자: 문의 답변 등록 및 이메일 발송
async def answer_inquiry(inquiry_id: int, answer: str, session: AsyncSession):
    # 1. 기존 get_inquiry를 사용해 문의 존재 여부 확인
    inquiry_dict = await get_inquiry(inquiry_id, session)
    if not inquiry_dict:
        return None

    # 2. 실제 수정 작업을 위해 Inquiry 모델 인스턴스를 session.get()으로 조회
    inquiry_obj = await session.get(Inquiry, inquiry_id)
    if not inquiry_obj:
        return None

    # 3. 답변 저장
    updated_inquiry_dict = await save_answer(inquiry_obj, answer, session)

    # 4. 문의 작성자의 회원 정보 조회 (Member 객체에서 직접 이메일 조회)
    member_id = updated_inquiry_dict["member_id"]
    member_obj = await session.get(
        Member, member_id
    )
    member_email = member_obj.email if member_obj else None

    # 5. 사용자에게 이메일 알림 발송
    if member_email:
        send_email(
            to_email=member_email,
            subject="EASY TRAVEL - 문의 답변 등록 안내",
            body=f"""
안녕하세요, 고객님.

EASY TRAVEL 입니다.

고객님께서 남기신 문의에 대해 아래와 같이 답변이 등록되었음을 알려드립니다.

문의 제목 : {updated_inquiry_dict["title"]}
문의 내용 : {updated_inquiry_dict["content"]}

✅ 답변 :
{answer}

추가 문의 사항이나 도움이 필요하시면 언제든지 EASY TRAVEL 고객센터로 연락 주시기 바랍니다.

감사합니다.

EASY TRAVEL 드림
    """,
        )

    return updated_inquiry_dict


# 이메일 전송 함수 (변경 없음)
def send_email(to_email: str, subject: str, body: str):
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as connection:
            connection.starttls()  # 보안 설정
            connection.login(user=SMTP_USER, password=SMTP_PASSWORD)

            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart()
            msg["From"] = SMTP_USER
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            connection.send_message(msg)

        print(f"이메일 전송 성공: {to_email}")

    except Exception as e:
        print(f"이메일 전송 실패: {e}")
