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
                goal="restaurant(맛집), cafe(카페), site(관광지), accommodation(숙소) 네 카테고리의 장소들을 시간대별로 적절히 조합하여 최적의 여행 일정을 구성한다.",
                backstory="""다양한 카테고리(맛집, 카페, 관광지, 숙소)의 장소들을 시간대별 규칙에 맞게 조합하여 효율적인 여행 일정을 만드는 전문가입니다.
                각 카테고리별 데이터를 분석하고, 시간대별로 적절한 장소를 선택하여 최적의 동선을 구성합니다.""",
                tools=[self.route_tool],
                llm=self.llm,
                verbose=True,
                max_iter=1,
            )
        }

    def _create_tasks(self) -> List[Task]:
        """최종 여행 일정 생성을 위한 Task 생성"""
        task_description = """
        목표:
        - 각 장소들의 데이터의 위도, 경도를 참고하여 최적의 동선을 생성할 수 있는 장소들을 선택하고, 최적의 동선을 고려한 여행 일정을 반환해주세요.
            
        규칙 및 조건:
        1. spot_category 정보
        - accommodation:0, site:1, restaurant:2, cafe:3
        2. tool 사용시 input은 "외부 데이터"로 제공 받은 길이가 {n_agent_results}인 list를 사용하세요.
        3. tool의 output의 리스트 순서(리스트에 적힌 order, day_x, spot_time와 상관 없이, 리스트 반환된 장소 순서)를 참고하여 order, day_x, spot_time를 다시 설정해주세요.
        4. accommodation은 반드시 1개만 선정하며, 매일 같은 숙소를 반환합니다. 숙소를 제외한 모든 장소는 반드시 중복 되지 않아야 합니다.  
        - accommodation : 총 1개
        - site : 총 {n_spots}개, day_x:{days} 제외 모두 같은 장소 반환
        - restaurant : 총 {n_spots}개
        - cafe : 총 {n_cafe}개
        5. order, day_x, spot_time 설정 시 고려할 사항
        - day_x는 {days}일의 여행 일정 중 몇일차인지 입니다.(만약, day_x:1 이라면 1일차에 방문한다는 의미)  
        - day_x가 {days}일 경우, 반드시 식당 1곳만 반환하고, spot_time은 13:00, order는 1이여야 합니다.
        - day_x가{days} 가 아니라면, day_x 별로 site 2곳, restaurant 2곳, cafe 1곳을 반환해주세요.
        - 마지막 일자인 {days}일차에는 restaurant 1곳만 반환해주세요. (day_x:{days}, spot_time: 13:00, order:1)
        - day_x별로 각 장소의 spot_time과 order는 다음과 같이 고정해주세요.
            - spot_time: 13:00 - restaurant, order:1 
            - spot_time: 14:30 - site, order:2
            - spot_time: 16:00 - cafe, order:3
            - spot_time: 17:30 - site, order:4
            - spot_time: 19:00 - restaurant, order:5 
            - spot_time: 20:30 - accommodation, order:6 ({days}일차 제외 모두 동일 숙소 반환)   
            
        "외부 데이터":{external_data}
             
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
