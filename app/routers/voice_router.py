from fastapi import APIRouter, UploadFile, File
from app.services.voice.voice_plan import ChatService

router = APIRouter()
chat_service = ChatService()

@router.post("/chat")

async def chat(audio: UploadFile = File(...)):

    return await chat_service.process_chat(audio)