import os
import traceback
from datetime import datetime
from crewai import Agent, Task, Crew, LLM
from dotenv import load_dotenv
from typing import List, Dict
from fastapi import HTTPException
from app.dtos.spot_models import spots_pydantic
from app.utils.time_check import time_check
from app.services.agents.tools.all_schedule_agent_tool import HaversineRouteOptimizer

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
llm = LLM(model="gpt-4o-mini", temperature=0, api_key=OPENAI_API_KEY)

class TravelScheduleAgentService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TravelScheduleAgentService, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
        print("TravelScheduleAgentService 초기화 중...")
        self.llm = llm
        self.route_tool = HaversineRouteOptimizer()
        self.agents = self._create_agents()

    def _create_agents(self) -> Dict[str, Agent]:
        """Agent들을 생성하는 메서드"""
        return {
            "planner": Agent(
                role="여행 일정 최적화 플래너",
                goal="restaurant(맛집), cafe(카페), site(관광지) 세 카테고리의 장소들을 시간대별로 적절히 조합하여 최적의 여행 일정을 구성한다.",
                backstory="""다양한 카테고리(맛집, 카페, 관광지)의 장소들을 시간대별 규칙에 맞게 조합하여 효율적인 여행 일정을 만드는 전문가입니다.
                각 카테고리별 데이터를 분석하고, 시간대별로 적절한 장소를 선택하여 최적의 동선을 구성합니다.""",
                tools=[self.route_tool],
                llm=self.llm,
                verbose=True,
            )
        }

    def _create_tasks(self) -> List[Task]:
        """Task들을 생성하는 메서드"""
        task_description = """
        [최종 여행 일정 생성]
        - 여행 기간: {start_date} ~ {end_date}
        - external_data에는 다음 세 가지 카테고리의 장소들이 포함되어 있습니다:
        1. restaurant: 맛집 목록
        2. cafe: 카페 목록
        3. site: 관광지 목록
        
        - day_x: 방문 날짜
        - order: 해당 날짜의 방문 순서
        -spot_time: 해당 스팟의 방문 추천 시간.

        일정 구성 필수 규칙:
        1. 아침 일정 (08:00)
        - site(관광지) 목록에서 1곳 선택
        - cafe(카페) 목록에서 1곳 선택

        2. 점심 일정 (12:00)
        - restaurant(맛집) 목록에서 1곳 선택
        - site(관광지) 목록에서 2곳 선택

        3. 저녁 일정 (18:00)
        - restaurant(맛집) 목록에서 1곳 선택
        - 숙소가 있다면 포함
        중요 제약사항:
        - 각 카테고리(restaurant, cafe, site)별로 제공된 데이터만 사용할 것
        - 새로운 장소를 임의로 생성하지 말 것
        - 필요한 카테고리의 데이터가 부족하면 해당 시간대는 비워둘 것
        - 이동 거리와 시간을 고려하여 효율적인 동선으로 구성할 것
        - 각 장소는 중복 사용하지 않을 것

        External Data: {external_data}
        """
        return [Task(
            description=task_description,
            agent=self.agents["planner"],
            expected_output="pydantic 형식의 여행 일정 데이터",
            output_pydantic=spots_pydantic,
            async_execution=True,
        )]

    def _process_result(self, result, input_dict: dict) -> dict:
        """결과를 처리하는 메서드"""
        return {
            "message": "요청이 성공적으로 처리되었습니다.",
            "plan": {
                "name": input_dict.get("name", "여행 일정"),
                "start_date": input_dict["start_date"],
                "end_date": input_dict["end_date"],
                "main_location": input_dict.get("main_location", "Unknown Location"),
                "created_at": datetime.now().strftime("%Y-%m-%d"),
            },
            "spots": result.pydantic.model_dump()
        }
    @time_check
    async def create_plan(self, input_dict: dict) -> dict:
        """여행 일정 생성 워크플로우 실행"""
        try:
            # Task 생성
            tasks = self._create_tasks()
            
            # Crew 실행
            crew = Crew(tasks=tasks, agents=list(self.agents.values()), verbose=True)
            result = await crew.kickoff_async(inputs=input_dict)
            
            # 결과 처리
            return self._process_result(result, input_dict)

        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))