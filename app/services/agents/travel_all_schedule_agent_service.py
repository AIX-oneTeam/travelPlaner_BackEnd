import os
import traceback
from datetime import datetime
from crewai import Agent, Task, Crew, LLM
from dotenv import load_dotenv
from typing import List, Dict
from fastapi import HTTPException
from app.dtos.spot_models import spots_pydantic
from app.utils.time_check import time_check
from app.repository.members.mebmer_repository import get_memberId_by_email
from sqlmodel.ext.asyncio.session import AsyncSession
from redis.asyncio import Redis 
from app.services.agents.tools.all_schedule_agent_tool import HaversineRouteOptimizer
import logging
import json

logger = logging.getLogger("all_schedule_agent_service")
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler('logs/all_schedule_agent_service.log')
file_handler.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)

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
        """최종 여행 일정 생성을 위한 Task 생성: 여행 기간 내 각 날짜마다 08:00, 12:00, 18:00의 고정 시간 슬롯을 순차적으로 적용"""
        task_description = """
        [최종 여행 일정 생성]

        입력:
        - 여행 기간: {start_date} ~ {end_date} (사용자가 선택한 여행 날짜 범위)
        - 여행 지역: {main_location}
        - 외부 데이터: {external_data}
        - 사용 가능한 카테고리: restaurant, cafe, site, accommodation (제공된 카테고리만 사용)

        규칙 및 조건:
        1. 일정은 각 날짜별로 생성되며, 전체 여행 기간은 {start_date}부터 {end_date}까지이다.
        2. 각 날짜별로 생성되는 시간 슬롯은 다음과 같다:
        - 일반 날짜 (마지막 날짜가 아닌 경우):
            - spot_time: 13:00 → restaurant (점심 식사)
            - spot_time: 14:30 → site (첫 번째 관광지 방문)
            - spot_time: 16:00 → cafe (카페 방문)
            - spot_time: 17:30 → site (두 번째 관광지 방문)
            - spot_time: 19:00 → restaurant (저녁 식사)
            - spot_time: 20:30 → accommodation (숙소; 해당 데이터가 없으면 빈 슬롯)
            (spot_time은 고정되어 있으며 직접 변경 불가능)
        - 마지막 날짜 ({end_date}와 동일한 날):
            - 오직 spot_time: 13:00 → restaurant (점심 식사 후 일정 종료)만 생성
        3. 각 날짜의 일정이 모두 생성되면, 다음 날짜(day_x 값은 1씩 증가)로 넘어간다.
        4. 사용 가능한 데이터(restaurant, cafe, site, accommodation) 중에서 조건에 맞게 장소를 선택하며, 한 번 선택된 장소는 재사용하지 않는다.
        5. 필요한 카테고리가 없는 경우 해당 시간 슬롯은 생략한다.
        6. 최적의 이동 경로를 위해 제공된 위도/경도 정보를 기반으로 장소들을 재배치한다.

        [PROCESS]
        1. 여행 기간을 날짜별로 순회하며 각 날짜에 대해 일정 생성.
        2. 만약 현재 날짜가 {end_date}와 동일하면, 오직 13:00 슬롯(restaurant)만 생성.
        3. 그렇지 않으면 13:00, 14:30, 16:00, 17:30, 19:00, 20:30 슬롯을 순차적으로 생성.
        4. 최종적으로 각 날짜별로 day_x, order, spot_time이 할당된 여행 일정을 생성한다.
        """
        return [Task(
            description=task_description,
            agent=self.agents["planner"],
            expected_output="pydantic 형식의 여행 일정 데이터",
            output_pydantic=spots_pydantic,
            async_execution=True,
        )]

    def _process_result(self, result, input_dict: dict) -> dict:
        """에이전트 결과를 최종 응답 형태로 가공"""
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
    async def create_plan(
        self,
        input_dict: dict, 
        session: AsyncSession = None,
        redis_client: Redis = None
    ) -> dict:
        """
        여행 일정 생성 워크플로우:
        1) 이메일 -> member_id 조회(옵션)
        2) Crew(에이전트) 실행 -> 일정 생성
        3) Redis에 저장(옵션) -> 디버깅 로그
        4) 결과 반환
        """
        try:
            logging.info(f"[DEBUG] 받은 데이터: {input_dict}")
            member_id = None

            # (1) 이메일로 member_id 조회
            if input_dict.get("email") and session:
                member_id = await get_memberId_by_email(input_dict["email"], session)
                logging.info(f"[DEBUG] 💥 이메일 -> member_id 매핑 결과: {member_id}")

            # (2) Crew 실행
            tasks = self._create_tasks()
            crew = Crew(tasks=tasks, agents=list(self.agents.values()), verbose=True)
            result = await crew.kickoff_async(inputs=input_dict)
            processed_result = self._process_result(result, input_dict)

            # (3) Redis 저장 (디버깅 로그)
            # if redis_client and member_id is not None:
            #     redis_key = str(member_id)  # 키로 member_id 사용
            #     # 저장 직전에 어떤 데이터인지 확인
            #     logging.info("[DEBUG] Redis에 저장할 데이터:\n" +
            #                  json.dumps(processed_result, indent=2, ensure_ascii=False))

            #     # 실제 저장
            #     await redis_client.set(redis_key, json.dumps(processed_result), ex=86400)
            #     logging.info(f"[DEBUG] Redis에 key='{redis_key}'로 일정 데이터 저장 완료.")

            #     # 저장 후, 다시 GET 해보기 (간단 검증)
            #     saved_value = await redis_client.get(redis_key)
            #     logging.info(f"[DEBUG] Redis에 실제로 저장된 값:\n {saved_value}")

            # (4) 최종 결과 반환
            return processed_result

        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
