# app/services/chat_service.py

from fastapi import UploadFile
import openai
from pathlib import Path
import os
import asyncio
import edge_tts  # edge-tts 라이브러리 임포트

class ChatService:
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        openai.api_key = self.openai_api_key

    async def process_chat(self, audio: UploadFile) -> dict:
        try:
            # 임시 파일로 저장
            temp_audio_path = f"temp_{audio.filename}"
            with open(temp_audio_path, "wb") as buffer:
                content = await audio.read()
                buffer.write(content)

            # STT 처리 (백엔드에서 여행 도메인 프롬프트 적용)
            user_text = self._perform_stt(temp_audio_path)
            print(f"STT 결과: {user_text}")  # 디버깅용 로그

            # LLM 처리: 여행 일정 추천 응답 생성
            ai_text = self._perform_llm(user_text)
            print(f"LLM 결과: {ai_text}")  # 디버깅용 로그

            # TTS 처리: 응답 텍스트를 음성으로 변환 (edge-tts 사용)
            audio_bytes = await self._perform_tts(ai_text)

            # 임시 파일 삭제
            os.remove(temp_audio_path)

            return {
                "success": True,
                "user_text": user_text,
                "ai_text": ai_text,
                "audio_base64": audio_bytes.hex()
            }

        except Exception as e:
            print(f"에러 발생: {str(e)}")  # 디버깅용 로그
            return {"success": False, "error": str(e)}

    def _perform_stt(self, audio_path: str) -> str:
        """음성을 텍스트로 변환하는 함수 (여행 일정 전문 도메인 적용)"""
        try:
            # 여행 일정 전문 도메인 프롬프트 (백엔드에서 처리)
            context_prompt = (
                "여행 일정: 사용자의 요청은 여행 일정 추천과 관련된 것입니다. "
                "추천 여행 코스, 관광 명소, 숙소, 맛집, 비용, 교통 정보 등을 포함하여 "
                "정확한 한국어로 전사해 주세요."
            )
            with open(audio_path, "rb") as audio_file:
                transcription = openai.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="ko",
                    prompt=context_prompt,
                    temperature=0.0,           # 정확도 우선
                    response_format="verbose_json"  # 상세 결과 요청
                )
            # 원본 인식 텍스트 로깅
            print(f"원본 인식 텍스트: {transcription.text}")
            # 후처리: 텍스트 정규화 및 키워드 교정
            transcribed_text = self._post_process_stt(transcription.text)
            print(f"후처리 텍스트: {transcribed_text}")
            return transcribed_text
        except Exception as e:
            print(f"STT 에러: {str(e)}")
            raise

    def _post_process_stt(self, text: str) -> str:
        """STT 결과 후처리: 여행 관련 키워드 교정 및 문장 끝 보정"""
        keyword_mappings = {
            "여형": "여행",
            "여정": "여행",
            "일성": "일정",
            "계희": "계획",
            "관광디": "관광지",
            # 추가 키워드 필요 시 여기에 더 추가하세요.
        }
        processed_text = text.strip()
        for wrong, correct in keyword_mappings.items():
            processed_text = processed_text.replace(wrong, correct)
        if not processed_text.endswith(("입니다", "니다", "요", ".", "?")):
            processed_text += "입니다"
        return processed_text

    def _validate_stt_result(self, text: str) -> bool:
        """STT 결과 유효성 검증"""
        if len(text.strip()) < 2:
            return False
        travel_keywords = ["여행", "일정", "계획", "관광", "숙소", "맛집"]
        return any(keyword in text for keyword in travel_keywords)

    def _perform_llm(self, input_text: str) -> str:
        """텍스트를 분석하고 여행 일정 추천 응답 생성"""
        try:
            system_prompt = (
                "당신은 여행 전문 AI 어시스턴트입니다. "
                "사용자의 여행 관련 질문이나 요청에 대해 구체적이고 실용적인 정보를 제공해야 합니다. "
                "추천 여행 코스, 관광 명소, 숙소, 맛집, 등 필요한 정보를 포함하여 답변해 주세요."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": input_text}
            ]
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0,
                max_tokens=1000
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"LLM 에러: {str(e)}")
            raise

    async def _perform_tts(self, text: str) -> bytes:
        """텍스트를 음성으로 변환하는 함수 (edge-tts 사용)
        이 함수는 edge-tts 라이브러리를 사용하여 입력 텍스트를 음성으로 변환하고,
        결과를 MP3 파일로 저장한 후 바이트로 반환합니다.
        """
        try:
            output_path = "response.mp3"

            async def run_edge_tts(text: str, output_path: str):
                # 기본적으로 한국어 목소리 "ko-KR-SunHiNeural" 사용 (필요 시 다른 음성으로 변경 가능)
                communicate = edge_tts.Communicate(text, "ko-KR-SunHiNeural")
                await communicate.save(output_path)

            await run_edge_tts(text, output_path)

            with open(output_path, "rb") as audio_file:
                audio_bytes = audio_file.read()
            os.remove(output_path)
            return audio_bytes
        except Exception as e:
            print(f"TTS 에러: {str(e)}")
            raise

    def _validate_input(self, text: str) -> bool:
        """입력 텍스트 유효성 검사"""
        return bool(text and text.strip())

    def _format_response(self, text: str) -> str:
        """응답 텍스트 포맷팅: 불필요한 공백 제거"""
        return ' '.join(text.split())
