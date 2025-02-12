# site_agent_service.py
import traceback
import json
from datetime import datetime
from typing import List, Dict, Optional
from crewai import Agent, Task, Crew, LLM
from fastapi import HTTPException
from app.dtos.spot_models import spot_pydantic, spots_pydantic
from dotenv import load_dotenv
import os
import asyncio

# 도구 임포트 (site_tool.py에 구현된 도구들)
from app.services.agents.tools.site_tool import (
    NaverWebSearchTool,
    NaverImageSearchTool,
    check_url_openable_async,
)

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class SiteAgentService:
    """관광지 추천을 위한 Site Agent 서비스 (싱글톤)"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SiteAgentService, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
        """서비스 초기화"""
        self.llm = LLM(model="gpt-4o-mini", temperature=0, api_key=OPENAI_API_KEY)
        # 도구 초기화
        self.web_search_tool = NaverWebSearchTool()
        self.image_search_tool = NaverImageSearchTool()
        self.agents = self._create_agents()

    def _process_input(
        self, input_data: dict, prompt: Optional[str] = None
    ) -> tuple[dict, str]:
        """
        입력 데이터 전처리:
        - 사용자가 입력한 여행 정보(지역, 일정, 연령, 동반자 수, 컨셉 등)를 그대로 사용하고,
        - 추가 프롬프트가 있을 경우 텍스트로 변환함.
        """
        prompt_text = f'추가 요청: "{prompt}"' if prompt else ""
        return input_data, prompt_text

    def _create_agents(self) -> Dict[str, Agent]:
        """에이전트들을 생성"""
        return {
            "site_search": Agent(
                role="관광지 추천 전문가",
                goal=(
                    "사용자가 입력한 여행 정보(지역, 일정, 연령, 동반자 수, 컨셉 등)를 반영하여 "
                    "해당 지역의 관광지를 추천하라. 결과는 반드시 순수한 JSON 배열 형식(예: [ {"
                    '"kor_name": string, "eng_name": string or null, "address": string, "url": string or null, '
                    '"image_url": string, "map_url": string, "spot_category": number, "phone_number": string or null, '
                    '"business_status": boolean or null, "business_hours": string or null, "spot_time": string or null'
                    "} ])로 반환할 것."
                ),
                backstory=(
                    "나는 최신 관광지 정보를 기반으로 사용자에게 최적의 관광지 추천을 제공하는 전문가입니다. "
                    "추천 결과는 관광지의 상세 정보(이름, 주소, 웹사이트, 지도 링크, 이미지 URL 등)를 포함해야 한다."
                ),
                tools=[self.web_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            "image_update": Agent(
                role="관광지 이미지 검색 전문가",
                goal=(
                    "추천된 관광지 리스트의 각 항목에 대해 'kor_name'을 활용하여 최신 관광지 이미지를 검색하고, "
                    "각 항목의 image_url 필드를 업데이트하라."
                ),
                backstory=(
                    "나는 네이버 이미지 검색 API를 사용하여 관광지의 대표 이미지를 제공하는 전문가입니다."
                ),
                tools=[self.image_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
        }

    def _create_tasks(self, input_data: dict, prompt_text: str) -> List[Task]:
        """
        태스크 생성:
         1. 관광지 추천 요청
         2. 이미지 업데이트 요청
        """
        # 태스크 1: 관광지 추천 요청
        task1_description = (
            f"'{input_data['main_location']}' 지역에서 {input_data['start_date']}부터 {input_data['end_date']}까지 여행하는 "
            f"여행객 (연령대: {input_data['ages']}, 동반자: {input_data['companion_count']}, 컨셉: {', '.join(input_data['concepts'])})에 맞는 "
            "관광지를 최소 5곳 추천하라.\n"
            f"{prompt_text}\n"
            "반드시 추천 결과는 순수한 JSON 배열 형식(예: [ {"
            '"kor_name": string, "eng_name": string or null, "address": string, "url": string or null, '
            '"image_url": string, "map_url": string, "spot_category": number, "phone_number": string or null, '
            '"business_status": boolean or null, "business_hours": string or null, "spot_time": string or null'
            "} ] )로 반환할 것."
        )
        task1 = Task(
            description=task1_description,
            agent=self.agents["site_search"],
            expected_output="관광지 추천 결과 (JSON 배열)",
        )

        # 태스크 2: 이미지 업데이트 요청
        task2_description = (
            "추천된 관광지 리스트의 각 항목에 대해 'kor_name'을 활용하여 네이버 이미지 검색 API로 최신 이미지를 조회하고, "
            "기존 결과의 image_url 필드를 업데이트하라."
        )
        task2 = Task(
            description=task2_description,
            agent=self.agents["image_update"],
            expected_output="관광지 이미지 업데이트 결과 (JSON 배열)",
        )
        return [task1, task2]

    def _process_result(self, result, input_data: dict) -> dict:
        """최종 결과 후처리: Crew의 마지막 태스크 결과를 pydantic 모델로 변환"""
        try:
            if hasattr(result, "tasks_output") and result.tasks_output:
                final_task_output = result.tasks_output[-1]
                if hasattr(final_task_output, "pydantic"):
                    spots_data = final_task_output.pydantic.model_dump()
                else:
                    spots_data = json.loads(final_task_output.raw)
            else:
                spots_data = {"spots": []}
        except Exception as e:
            spots_data = {"spots": []}

        return {
            "message": "관광지 추천이 성공적으로 처리되었습니다.",
            "plan": {
                "main_location": input_data.get("main_location", ""),
                "start_date": input_data.get("start_date", ""),
                "end_date": input_data.get("end_date", ""),
                "ages": input_data.get("ages", ""),
                "companion_count": sum(input_data.get("companion_count", [])),
                "concepts": ", ".join(input_data.get("concepts", [])),
                "created_at": datetime.now().strftime("%Y-%m-%d"),
                "updated_at": datetime.now().strftime("%Y-%m-%d"),
            },
            "spots": (
                spots_data.get("spots", [])
                if isinstance(spots_data, dict)
                else spots_data
            ),
        }

    async def create_recommendation(
        self, input_data: dict, prompt: Optional[str] = None
    ) -> dict:
        """
        관광지 추천 워크플로우 실행:
         1. 입력 데이터 전처리
         2. 태스크 생성
         3. Crew 실행 (비동기)
         4. 결과 후처리 및 pydantic 모델 반환
        """
        try:
            processed_input, prompt_text = self._process_input(input_data, prompt)
            tasks = self._create_tasks(processed_input, prompt_text)
            crew = Crew(tasks=tasks, agents=list(self.agents.values()), verbose=True)
            result = await crew.kickoff_async()
            return self._process_result(result, processed_input)
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
