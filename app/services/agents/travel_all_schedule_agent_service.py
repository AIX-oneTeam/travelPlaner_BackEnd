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
import logging

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
        사용자 입력인 {start_date}, {end_date}를 기준으로 전체 여행 기간을 계산합니다.
        각 날짜마다 일정을 동적으로 생성하며, 각 날짜는 day_x (1부터 순차적 증가)로 표시합니다.
        
        각 장소 기록은 아래와 같이 할당됩니다:
        - day_x: 해당 날짜 (1부터 순차적 증가)
        - order: 해당 날짜 내 방문 순서 (존재하는 시간 슬롯 기준 1부터 순차적 할당)
        - spot_time: 미리 정의된 고정된 시간 슬롯 (08:00, 12:00, 18:00)으로 할당 (절대 변경되지 않음)
        
        {external_data}: 선택된 에이전트로부터 받은 장소 데이터 목록.
        사용 가능한 카테고리: restaurant, cafe, site, accommodation (제공된 카테고리만 사용)
        
        [TIME SLOT CONSTRUCTION] - **고정된 시간 슬롯 사용: 08:00, 12:00, 18:00**
        반드시 아래의 규칙에 따라 장소를 할당하며, 시간 값은 변경되지 않아야 합니다.
        
        1. 아침 (08:00)
        - 조건: site 카테고리와 cafe 카테고리가 모두 존재할 때만 생성
            IF 조건 만족 시:
            - site에서 1곳 선택
            - cafe에서 1곳 선택
        
        2. 점심 (12:00)
        - 조건: restaurant 카테고리와 site 카테고리가 모두 존재할 때만 생성
            IF 조건 만족 시:
            - restaurant에서 1곳 선택
            - site에서 2곳 선택
        
        3. 저녁 (18:00)
        - 조건:
            IF restaurant 카테고리와 accommodation 카테고리가 모두 존재하면:
            - restaurant에서 1곳 선택
            - accommodation에서 1곳 선택 (마지막 날 제외)
            ELSE IF restaurant 카테고리만 존재하면:
            - restaurant에서 1곳만 선택
        
        [OPTIMIZATION REQUIREMENTS]
        1. 위치 기반 최적화: 
        - 제공된 장소들의 위도/경도 정보를 사용하여 이동 거리를 최소화합니다.
        2. 순서 할당:
        - day_x: 각 날짜별로 1부터 순차적으로 할당
        - order: 해당 날짜 내 시간 슬롯(존재하는 슬롯만) 순서대로 1부터 할당
        - spot_time: 반드시 고정된 시간 슬롯 (08:00, 12:00, 18:00)을 사용하며, 절대로 변경되지 않습니다.
        
        [CONSTRAINTS]
        1. 모든 장소는 한 번만 사용
        2. 필요한 카테고리가 없는 시간 슬롯은 생략
        3. 선택되지 않은 카테고리는 고려하지 않음
        4. 마지막 날에는 숙소(accommodation)를 포함하지 않음
        
        [OUTPUT]
        최종 일정은 spots_pydantic 형식의 데이터로 출력되며, 각 장소에 day_x, order, spot_time 값이 올바르게 부여됩니다.
        
        [PROCESS]
        1. {external_data}에서 사용 가능한 카테고리 확인
        2. 가능한 시간 슬롯 조합 결정
        3. 각 시간 슬롯별로 장소 할당 (08:00, 12:00, 18:00은 고정)
        4. 위치 기반 최적 경로 계산
        5. day_x, order, spot_time 값 할당
        6. 최종 일정 생성
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
            logging.info(f"받은 데이터: {input_dict}")

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