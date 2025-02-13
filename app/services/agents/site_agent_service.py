import traceback
import json
from datetime import datetime
from typing import List, Dict, Optional
from crewai import Agent, Task, Crew, LLM
from fastapi import HTTPException
from app.dtos.spot_models import spots_pydantic
from dotenv import load_dotenv
import os

# 도구 임포트 (site_tool.py에 구현된 네이버 도구들)
from app.services.agents.tools.site_tool import (
    NaverTouristWebSearchTool,
    NaverTouristImageSearchTool,
)

# 환경 변수 로드
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class TouristAgentService:
    """관광지 추천을 위한 Agent 서비스 (CrewAI 활용)"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TouristAgentService, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
        """서비스 초기화"""
        self.llm = LLM(model="gpt-4o-mini", temperature=0, api_key=OPENAI_API_KEY)
        # 네이버 웹/이미지 검색 도구 초기화
        self.web_search_tool = NaverTouristWebSearchTool()
        self.image_search_tool = NaverTouristImageSearchTool()
        self.agents = self._create_agents()

    def _process_input(
        self, input_data: dict, prompt: Optional[str] = None
    ) -> tuple[dict, str]:
        """입력 데이터 전처리"""
        print(f"[입력 데이터] {input_data}")
        print(f"[프롬프트] {prompt}")
        # concepts가 리스트가 아니면 빈 리스트로 초기화
        if "concepts" not in input_data or not isinstance(input_data["concepts"], list):
            input_data["concepts"] = []
        prompt_text = f'추가 요청: "{prompt}"\n' if prompt else ""
        return input_data, prompt_text

    def _create_agents(self) -> Dict[str, Agent]:
        """Agent들을 생성하는 메서드"""
        return {
            "tourist_search": Agent(
                role="관광지 추천 전문가",
                goal=(
                    "사용자가 제공한 여행 정보(지역, 일정, 연령, 동반자 수, 컨셉 등)를 바탕으로 "
                    "해당 지역의 관광지를 추천하라. 결과는 반드시 JSON 배열 형식으로 반환할 것."
                ),
                backstory="나는 최신 관광 정보를 알고 있는 전문가이다.",
                tools=[self.web_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            "image_update": Agent(
                role="관광지 이미지 검색 전문가",
                goal=(
                    "추천된 관광지 리스트의 각 항목에 대해 'kor_name'을 사용하여 최신 이미지를 검색하고 "
                    "각 항목의 image_url을 업데이트하라."
                ),
                backstory="나는 네이버 이미지 검색 API를 통해 관광지의 대표 이미지를 제공하는 전문가이다.",
                tools=[self.image_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
        }

    def _create_tasks(self, input_data: dict, prompt_text: str) -> List[Task]:
        """Task들을 생성하는 메서드"""
        task1 = Task(
            description=(
                f"'{input_data['main_location']}' 지역에서 {input_data['start_date']}부터 {input_data['end_date']}까지 여행하는 "
                f"여행객(연령대: {input_data['ages']}, 동반자: {input_data['companion_count']}, 컨셉: {', '.join(input_data['concepts'])})에 맞는 "
                "관광지를 추천하라.\n"
                f"{prompt_text}"
                "반드시 추천 결과는 JSON 배열 형식으로 반환할 것."
            ),
            agent=self.agents["tourist_search"],
            expected_output="관광지 추천 결과 (JSON 배열)",
        )

        task2 = Task(
            description=(
                "추천된 관광지 리스트의 각 항목에 대해 'kor_name'을 사용하여 최신 이미지를 검색하고, "
                "각 항목의 image_url 필드를 업데이트하라."
            ),
            agent=self.agents["image_update"],
            expected_output="관광지 이미지 업데이트 결과 (JSON 배열)",
            output_pydantic=spots_pydantic,  # pydantic 스키마를 통한 검증
        )
        return [task1, task2]

    async def create_tourist_plan(
        self, input_data: dict, prompt: Optional[str] = None
    ) -> dict:
        """관광지 추천 워크플로우 실행"""
        try:
            processed_input, prompt_text = self._process_input(input_data, prompt)
            tasks = self._create_tasks(processed_input, prompt_text)
            crew = Crew(tasks=tasks, agents=list(self.agents.values()), verbose=True)
            result = await crew.kickoff_async()
            return self._process_result(result, processed_input)
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))

    def _process_result(self, result, input_data: dict) -> dict:
        """결과 후처리: Crew의 마지막 태스크 결과를 pydantic 모델로 변환"""
        try:
            if hasattr(result, "tasks_output") and result.tasks_output:
                final_task_output = result.tasks_output[-1]
                if (
                    hasattr(final_task_output, "pydantic")
                    and final_task_output.pydantic
                ):
                    spots_data = final_task_output.pydantic.model_dump()
                elif hasattr(final_task_output, "raw") and final_task_output.raw:
                    spots_data = json.loads(final_task_output.raw)
                else:
                    spots_data = {"spots": []}
            else:
                spots_data = {"spots": []}
        except Exception as e:
            print("Error processing result:", e)
            spots_data = {"spots": []}

        plan_info = {
            "main_location": input_data.get("main_location", ""),
            "start_date": input_data.get("start_date", ""),
            "end_date": input_data.get("end_date", ""),
            "ages": input_data.get("ages", ""),
            "companion_count": (
                sum(
                    companion.get("count", 0)
                    for companion in input_data.get("companion_count", [])
                )
                if isinstance(input_data.get("companion_count"), list)
                else 0
            ),
            "concepts": ", ".join(input_data.get("concepts", [])),
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "updated_at": datetime.now().strftime("%Y-%m-%d"),
        }
        return {
            "message": "관광지 추천이 성공적으로 처리되었습니다.",
            "plan": plan_info,
            "spots": spots_data.get("spots", []),
        }
