import os
import traceback
from datetime import datetime
from crewai import Agent, Task, Crew, LLM
from dotenv import load_dotenv
from typing import List, Dict
from fastapi import HTTPException
from app.dtos.spot_models import spots_pydantic
from app.utils.time_check import time_token_check
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
            )
        }

    def _create_tasks(self) -> List[Task]:
        """최종 여행 일정 생성을 위한 Task 생성: 여행 기간 내 각 날짜마다 08:00, 12:00, 18:00의 고정 시간 슬롯을 순차적으로 적용"""
        task_description = """
        [최종 여행 일정 생성]

        입력:
        - 여행 기간: {start_date} ~ {end_date} (사용자가 선택한 여행 날짜 범위)
        - 여행 지역: {main_location}
        - "외부 데이터": {external_data}
        - 사용 가능한 카테고리: restaurant, cafe, site, accommodation (제공된 카테고리만 사용)

        규칙 및 조건:
         ** tool 사용시 input은 "외부 데이터"의 spots에 담긴 spot 정보들을 list로 묶어 사용하세요.**
        1. 일정은 각 날짜별로 생성되며, 전체 여행 기간은 {start_date} ~ {end_date}까지이다.
        2. 각 날짜별로 생성되는 시간 슬롯은 다음과 같다.
        - **중요** 만일 {end_date}뺴기{start_date}의 값이 '2' 이상일 경우, 중간일 일정을 만든다.
        예를 들어 {end_date}뺴기{start_date}=2(즉, 2박 3일의 경우): 시작일-중간일-마지막일
        {end_date}뺴기{start_date}=2(즉, 3박 4일의 경우) : 시작인-중간일-중간일-마지막일
            
        - 시작일 ({start_date}) 형식:
        - 반드시 식당 - 관광지 - 카페 - 관광지 - 식당 - 숙소의 순서를 지키도록 한다. 
        - 반드시 식당 2개 관광지 2개 카페 1개 숙소 1개의 데이터가 포함되도록 한다.
            - spot_time: 13:00 고정 : 첫 번째 restaurant 데이터
            - spot_time: 14:30 고정 : 첫 번째 site 데이터
            - spot_time: 16:00 고정 : 첫 번째 cafe 데이터
            - spot_time: 17:30 고정 : 두 번째 site 데이터
            - spot_time: 19:00 고정 : 두 번째 restaurant 데이터
            - spot_time: 20:30 고정 : accommodation 데이터 
            (spot_time은 고정되어 있으며 절대 직접 변경 불가능)
            
        - 시작일 ({start_date}) 반복 형식 = 중간일 :
        - 반드시 식당 - 관광지 - 카페 - 관광지 - 식당 - 숙소의 순서를 지키도록 한다. 
        - 반드시 식당 2개 관광지 2개 카페 1개 숙소 1개의 데이터가 포함되도록 한다.
            - spot_time: 13:00 고정 : 세 번째 restaurant 데이터
            - spot_time: 14:30 고정 : 세 번째 site 데이터
            - spot_time: 16:00 고정 : 두 번째 cafe 데이터
            - spot_time: 17:30 고정 : 네 번째 site 데이터
            - spot_time: 19:00 고정 : 네 번째 restaurant 데이터
            - spot_time: 20:30 고정 : accommodation 데이터 (반드시 시작일 accommodation 데이터와 동일한 장소)
            (spot_time은 고정되어 있으며 절대 직접 변경 불가능)
            
        - 마지막일({end_date}와 동일한 날) 형식:
        - end_date와 동일한 마지막 날짜에는 반드시 하나의 식당 데이터만 가질 수 있도록 한다. 
            - 오직 spot_time: 13:00 고정 : restaurant 데이터 (점심 식사 후 일정 종료)만 생성

        3. 각 날짜의 일정이 모두 생성되면 기본day_x의 값은 1이다 day_x: 1 부터 시작, 다음 날짜(day_x 값은 1씩 증가)로 넘어간다.
        4. restaurant, cafe, site ,accommodation의중에서 조건에 맞게 장소를 선택하며, **각 장소는 반드시 위도(latitude)와 경도(longitude) 정보를 포함해야 한다.**
        5. accommodation의 경우 시작일 accommodation 데이터를 반드시 반복한다.
        6. 필요한 카테고리가 없는 경우 해당 시간 슬롯은 생략한다.
        7. **모든 장소에 대해 위도(latitude)와 경도(longitude) 정보가 반드시 포함되어야 하며, 만약 누락된 경우 해당 장소를 일정에서 제외한다.**
        8. **최적의 이동 경로를 위해 제공된 위도/경도 정보를 기반으로 장소들을 재배치한다.**
        9. **출력되는 최종 데이터 형식:**
            - `kor_name`: 장소의 한글 이름 (필수)
            - `eng_name`: 장소의 영어 이름 (필수)
            - `latitude`: 위도 (필수)
            - `longitude`: 경도 (필수)
            - `spot_category`: 장소 카테고리 (필수)
            - `***spot_time`: 방문 시간 (위에 고정되어있는 시간을 넣어라.)
            - `address`: 장소의 주소 (선택)
            - `description`: 장소 설명 (필수)
            - `phone_number`: 연락처 (선택)
        10. 각각의 장소는 중복된 장소를 추천하지 않는다.
        11. 20:30분은 accommodation 숙소를 꼭 넣어야한다.
        12. 일차가 변경되어도 중복된 장소는 사용하지 않는다

        [PROCESS]
        1. 여행 기간을 날짜별로 순회하며 각 날짜에 대해 일정 생성.
        2. 만약 현재 날짜가 {end_date}와 동일하면, 오직 13:00 슬롯(restaurant)만 생성.
        3. 그렇지 않으면 13:00, 14:30, 16:00, 17:30, 19:00, 20:30 슬롯을 순차적으로 생성.
        4. 최종적으로 각 날짜별로 day_x, order, spot_time이 할당된 여행 일정을 생성한다.
        5. ***day_x 는 1부터 시작 기본값이 day_x: 1
        6. 외부 데이터 내부에  spot_category는 1번이 관광지 2번이 맛집 3번이 카페 4번이 숙소이다. **중요
        7.   - 마지막일({end_date}와 동일한 날) 형식: **** 제일 중요
            - end_date와 동일한 마지막 날짜에는 반드시 하나의 식당 데이터만 가질 수 있도록 한다. 
            - 오직 spot_time: 13:00 고정 : restaurant 데이터 (점심 식사 후 일정 종료)만 생성
        8. 기존 일정이 완료 되었을때 다음날 일정에 중복 데이터 포함 x -** 한번 사용했던 장소는 중복추천 x
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

    @time_token_check
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
            logger.info(f"----------result.token_usage.__dict__: {result.token_usage.__dict__}")      
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
            processed_result["token_usage"] = result.token_usage.__dict__
            return processed_result

        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))