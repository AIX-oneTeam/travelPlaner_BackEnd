import os
from crewai import Agent, Task, Crew, LLM
from dotenv import load_dotenv
from app.dtos.spot_models import spots_pydantic, calculate_trip_days
from datetime import datetime
from app.utils.time_check import time_check
from app.services.agents.tools.all_schedule_agent_tool import HaversineRouteOptimizer

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
llm = LLM(model="gpt-4o-mini", temperature=0, api_key=OPENAI_API_KEY)

class TravelScheduleAgentService:
    """
    여행 일정 에이전트 인스턴스를 싱글톤 패턴으로 관리하는 클래스
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TravelScheduleAgentService, cls).__new__(cls)
            cls._instance.initialize()  # 최초 한 번만 초기화
        return cls._instance

    def initialize(self):
        print("TravelScheduleAgentService 초기화 중...")
        self.llm = llm
        self.route_tool = HaversineRouteOptimizer()
        
        self.planner = Agent(
            role="여행 일정 최적화 플래너",
            goal="제공된 외부 데이터를 사용하여 여행 일정을 구성한다. 새로운 장소는 생성하지 않는다.",
            backstory="외부 데이터를 재배열하여 최종 여행 일정을 생성합니다.",
            tools=[self.route_tool],
            llm=self.llm,
            verbose=True,
        )
        self.crew = None

    @time_check
    async def create_plan(self, user_input: dict):
        try:
            main_location = user_input.get("main_location", "Unknown Location")
            trip_days = calculate_trip_days(user_input["start_date"], user_input["end_date"])
            user_input["trip_days"] = trip_days

            external_data = user_input.get("external_data", {})
            print("create_plan 내부에서 받은 external_data:", external_data)

            planning_task = Task(
                description="""
            [최종 여행 일정 생성]
            - 여행 기간: {start_date} ~ {end_date} ({trip_days}일)
            - 위의 JSON 데이터를 그대로 활용하여, 날짜별로 최적의 순서로 재배열하고,
              각 장소의 방문 순서를 지정하세요.
            - 이동 거리와 시간을 고려하여 효율적인 동선을 구성하세요.
            - 외부 데이터 : {external_data} <-- 반드시 사용 
            - {external_data} 안에 restaurant, site, cafe 키가 있고, 각각이 장소 목록을 담고 있다.
            - 아침 08:00 site(관광지)에서 1개, cafe에서 1개를 넣는다.
            - 점심 12:00 restaurant(맛집)에서 1개, site(관광지)에서 2개를 넣는다.
            - 저녁 18:00 restaurant(맛집)에서 1개, 그리고 숙소()는 external_data에 있다면 사용하고, 없으면 생략하고 넣는다.
            - 만약 필요한 카테고리(restaurant, site, cafe)에 장소가 부족하면, 그 slot은 비워둔다(새로운 장소를 임의로 만들지 않는다).
            - 여기서 외부 데이터만 가지고 도구를 사용하여 위도 경도를 계산 후 최적의 동선을 위에 일정 조율.
            - day_x: 방문 날짜
            - order: 해당 날짜의 방문 순서
            - 나머지 필드는 그대로 유지
                """,
                agent=self.planner,
                expected_output="pydantic 형식의 여행 일정 데이터",
                output_pydantic=spots_pydantic,
            )

            crew = Crew(agents=[self.planner], tasks=[planning_task], verbose=True)
            result = crew.kickoff(inputs=user_input)
                    
            response_json = {
                "message": "요청이 성공적으로 처리되었습니다.",
                "plan": {
                    "name": user_input.get("name", "여행 일정"),
                    "start_date": user_input["start_date"],
                    "end_date": user_input["end_date"],
                    "main_location": main_location,
                    "created_at": datetime.now().strftime("%Y-%m-%d"),
                },
                "spots": result.pydantic.model_dump()
            }
            return response_json

        except Exception as e:
            return {"message": "요청 처리 중 오류가 발생했습니다.", "error": str(e)}
