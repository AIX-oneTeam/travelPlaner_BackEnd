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
        [FINAL TRAVEL ITINERARY GENERATION]

        INPUT:
        - Travel Period: {start_date} ~ {end_date}
        - Travel Region: {main_location}  
        (예: "서울특별시 - 강남구" 또는 사용자가 선택한 다른 지역)
        - External Data: 외부 데이터에는 아래 네 가지 카테고리의 장소 목록이 포함되어 있습니다.
            1. restaurant (Restaurants)
            2. cafe (Cafes)
            3. site (Tourist Sites)
            4. accommodation (Accommodations)

        Each place record includes the following attributes:
        - day_x: The travel day assigned to the place, which must start at 1 and be assigned consecutively based on the travel period.
        - order: The visitation order within that day.
        - spot_time: The recommended visit time (e.g., "08:00", "12:00", "18:00", "1박", etc.)

        TASK:
        Using only the provided external data (i.e., only the categories present in the external data) and following the rules and constraints below, generate a FINAL TRAVEL ITINERARY. The final output MUST be in Korean.

        RULES FOR ITINERARY CONSTRUCTION:
        1. For each travel day, divide the day into time slots according to the available data categories:
        - If the external data includes "site" and "cafe":
            • Morning (08:00): Select 1 tourist site from "site" and 1 cafe from "cafe".
        - If the external data includes "restaurant" and "site":
            • Lunch (12:00): Select 1 restaurant from "restaurant" and 2 tourist sites from "site".
        - If the external data includes "restaurant" and "accommodation":
            • Evening (18:00): Select 1 restaurant from "restaurant" and, if it is not the final travel day (i.e., the day corresponding to {end_date}), select 1 accommodation from "accommodation".
            
        → Do not include a time slot if the required category is missing in the external data.  
            (For example, if "cafe" data is absent, omit the corresponding part of the Morning slot.)

        2. ADDITIONAL CONSTRAINTS:
        - Use only the provided data from each category; DO NOT create any new places.
        - Do NOT reuse any selected place more than once across the itinerary.
        - Do NOT fill missing categories with empty values; include only the slots for which data is provided.
        - Optimize the itinerary for efficient travel routes, taking into account distance and time.
        - For each day’s itinerary, ensure that the final element in the Evening slot (the accommodation) is assigned on every day except the final travel day.
        - All day_x values must start from 1 and be assigned consecutively for each travel day.

        CHAIN-OF-THOUGHT (Step-by-Step Reasoning):
        1. Parse the user inputs ({start_date}, {end_date}, {main_location}) to determine the total travel period and region.
        2. Check the external data to identify which categories (restaurant, cafe, site, accommodation) are available.
        3. Dynamically generate an itinerary for each day within the travel period, assigning day_x values starting at 1 and increasing consecutively.
        4. For each day:
        - Morning (08:00):  
            • If "site" data is available, choose 1 tourist site.
            • If "cafe" data is available, choose 1 cafe.
        - Lunch (12:00):
            • If "restaurant" data is available, choose 1 restaurant.
            • If "site" data is available, choose 2 tourist sites.
        - Evening (18:00):
            • If "restaurant" data is available, choose 1 restaurant.
            • If "accommodation" data is available and it is not the final travel day, choose 1 accommodation.
        5. For every selected place, assign appropriate values for:
        - day_x: The specific travel day (starting from 1 and increasing consecutively)
        - order: The visitation order within that day
        - spot_time: The scheduled time (e.g., "08:00", "12:00", "18:00", or "1박" for accommodations)
        6. Ensure that no place is selected more than once and that all selections come solely from the provided external data.
        7. If data for any required slot is missing (i.e., the corresponding category is not present in the external data), simply omit that time slot.
        8. Construct the final itinerary with an efficient travel route.

        External Data: {external_data}

        Based on the above conditions and chain-of-thought, generate the FINAL TRAVEL ITINERARY in Korean.


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