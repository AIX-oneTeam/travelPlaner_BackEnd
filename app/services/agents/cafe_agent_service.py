import traceback
from crewai import Agent, Task, Crew, LLM, Process
from app.dtos.spot_models import spots_pydantic
from app.utils.calculate_trip_days import calculate_trip_days
from app.services.agents.tools.cafe_tool import NaverBlogSearchTool,NaverReviewCralwerTool, NaverBusinessInfoTool
from typing import Dict
import os
from dotenv import load_dotenv
from app.utils.time_check import time_token_check
from redis.asyncio import Redis
import logging
from sqlmodel.ext.asyncio.session import AsyncSession
from app.repository.agents.plan_spots_repository import (
    get_member_plan_spots,
    get_latest_plan,
)
from app.repository.members.mebmer_repository import get_memberId_by_email
from app.services.agents.redis.caching_spots import SpotCachingService
from app.services.agents.redis.spot_redis import SpotRedisService, SpotCategory
from app.dtos.cafe_models import CafeList

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler('logs/cafe_agent.log', encoding="utf-8")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# 에러 전용 로그 파일 생성
file_handler_error = logging.FileHandler('logs/cafe_agent_error.log', encoding="utf-8")
file_handler_error.setLevel(logging.ERROR)
formatter_error = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler_error.setFormatter(formatter_error)
logger.addHandler(file_handler_error)

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# logging 아이콘
# 🔵: 전달받은 데이터 유무 확인
# 🟢: 새로 생성된 일정이거나 plan_id 없는 경우(redis)
# 🟡: 기존 일정 수정(DB)
# 🟣: redis
            
class CafeAgentService:
    """
    카페 추천을 위한 Agent 서비스
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CafeAgentService, cls).__new__(cls)
            cls._instance.initialize()  # 최초 한 번만 초기화
        return cls._instance  # 동일한 인스턴스 반환

    def initialize(self):
        """서비스 초기화"""
                
        self.llm = LLM(model="gpt-4o-mini",api_key=OPENAI_API_KEY,temperature=0,max_tokens=4000)
        self.get_cafe_search_tool = NaverBlogSearchTool()
        self.get_cafe_review_tool = NaverReviewCralwerTool()
        self.get_cafe_business_info_tool = NaverBusinessInfoTool()
        self.agents = self._create_agents()
        self.tasks = self._create_tasks()
        
        self.tasks["researcher_task"].context = [self.tasks["collector_task"]]
        self.tasks["reviewer_task"].context = [self.tasks["researcher_task"]]
        self.tasks["decider_task"].context = [self.tasks["reviewer_task"]]
        self.draft_crew = Crew(agents=[self.agents['decider']], tasks=[self.tasks['decider_task']], verbose=True)  
        self.crew = Crew(agents=list(self.agents.values()), tasks=list(self.tasks.values()),process=Process.sequential, verbose=True)  

    def _create_agents(self) -> Dict[str, Agent]:
        return {
            "collector" : Agent(
                role="카페 리스트 수집 전문가",
                goal="고객의 여행 지역에 위치한 카페를 검색하고 리스트를 생성합니다.",
                backstory="""
                블로그에서 사용자의 조건에 맞는 카페를 검색하고, 리스트를 생성합니다. 
                포스팅된 횟수가 많은 카페부터 내림차순으로 정렬해주세요
                """,
                tools=[self.get_cafe_search_tool],
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True
            ),
            "researcher" : Agent(
                role="카페 상세 정보 수집 및 업종 검증가",
                goal="카페의 상세 정보를 수집하고 업종에 카페 또는 베이커리 또는 디저트가 포함되지 않은 장소는 삭제합니다.",
                backstory="""
                카페의 상세 정보를 수집하고, 업종에 카페 또는 베이커리 또는 디저트가 포함되지 않은 장소는 리스트에서 삭제해주세요. 
                """,
                tools=[self.get_cafe_business_info_tool],
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True
            ),
            "reviewer" : Agent(
                role="카페의 리뷰를 분석하고, 카페의 특징을 추출합니다.",
                goal="카페의 리뷰를 분석하고, 카페의 주요 특징과 분위기, 시그니처 메뉴를 추출합니다.",
                backstory="""
                카페의 최신 후기를 읽고, 카페의 주요 특징을 분석합니다. 반드시 researcher가 반환한 카페의 수만큼 카페를 반환해주세요.          
                """,
                tools=[self.get_cafe_review_tool],
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True
            ),
            "decider" : Agent(
                role="고객의 요구사항을 가장 많이 반영한 카페 선정",
                goal="고객의 여행지에서 인기있고, 고객의 선호도를 반영한 카페를 선정합니다.",
                backstory="""
                고객에게 가장 적합한 카페를 선별하고 추천해줍니다.
                """,
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True
            )
        }
    def _create_tasks(self) -> Dict[str, Task]:
        return {
            "collector_task" : Task(
                description="""
                1. 고객의 요구사항({prompt}), 여행 컨셉({concepts})을 반영해 keywords라는 이름의 리스트를 생성하고 키워드를 추가하세요.
                2. tool 사용시 input은 반드시 "{main_location}"과 생성한 리스트 타입의 "keywords" 2개만 순서대로 입력해 사용하세요.
                - 각 키워드는 형용사 또는 명사인 하나의 단어여야 하고, 비슷한 의미를 가진 단어는 1개만 사용하세요.
                - 1개로 충분하다면 불필요하게 2개 까지 생성하지 마세요.
                - 키워드로 "카페" 또는 "지역명" 또는 "추천"은 사용하지 마세요.
                3. 반드시 tool output의 길이와 동일한 개수의 카페를 반환하세요
                """,
                expected_output="""
                n_posting이 큰 순으로 내림차순 해주세요.
                1. 사용한 키워드 리스트
                2. 반환한 카페 수  
                3. 카페 정보 리스트
                - placeId
                - kor_name
                - address
                - latitude
                - longitude
                - phone_number          
                - n_posting
                """,        
                agent=self.agents["collector"],
            ),
            "researcher_task" : Task(
                description="""
                1. collector가 반환한 카페들의 placeId를 리스트로 묶어 tool의 input값으로 사용하세요.
                2. tool의 output을 보고 카페의 세부 정보를 수집하고, category에 "카페" 또는 "베이커리" 또는 "디저트"가 포함 되지 않은 장소는 삭제해주세요.
                3. collector가 반환한 값과 tool의 output의 정보를 합쳐 반환해주세요.
                """,
                expected_output="""
                n_posting이 큰 순으로 내림차순 해주세요.
                1. 반환한 카페 수  
                2. 카페 정보 리스트
                - placeId
                - kor_name
                - address
                - latitude
                - longitude
                - phone_number          
                - n_posting
                - url
                - business_status
                - business_hour
                - category
                """,        
                agent=self.agents["researcher"],
                context=[]
            ),
            "reviewer_task" : Task(
                description="""
                1. researcher가 반환한 카페들의 placeId를 리스트로 묶어 tool의 input값으로 사용하세요.
                2. 반드시 researcher가 반환한 카페들의 placeId 갯수 만큼 카페를 반환해주세요.
                3. researcher가 반환한 값에 tool_output의 정보를 합쳐 반환해주세요. 
                4. 카페 특징은 고객 요구사항에 맞는 카페인지 점검할 수 있도록 구체적으로 써주세요.
                5. 포스팅 횟수가 많고, 긍정적인 리뷰가 많은 카페부터 나열해주세요.
                description에는 카페 이름(kor_name), 나이대(ages), 부정적인 내용은 반드시 제외해주세요.
                preference에는 최신 리뷰를 읽고 전체 리뷰 중 긍정적인 리뷰가 얼마나 많은가에 대한 선호도를 %로 나타내주세요.
                """,
                expected_output="""
                n_posting, peference 순으로 내림차순 해주세요.
                반드시 researcher가 반환한 카페들의 placeId 갯수 만큼 카페를 반환해주세요.
                description : 카페의 주요 특징과 분위기, 시그니처메뉴, 사람들이 공통적으로 좋아했던 부분을 요약
                preference : 선호도 %
                map_url : https://map.kakao.com/link/map/"위도","경도"
                """,        
                agent=self.agents["reviewer"],
                output_pydantic=CafeList,
                context=[]
            ),
            "decider_task" : Task(
                description="""
                1. 고객의 요구사항({prompt}), 여행 컨셉({concepts}), 주 연령대({ages})가 반영된 카페를 가장 우선적으로 선택하세요.
                2. description에는 카페의 주요 특징과 분위기, 시그니처메뉴, 사람들이 공통적으로 좋아했던 부분을 요약해주세요.
                3. 모르는 정보는 지어내지 말고 "정보 없음"으로 작성하세요.
                4. 중복되지 않은 서로 다른 카페 리스트를 반환해주세요.
                참고 카페 리스트 : {cached_cafe_lists}
                반드시 기존에 추천된 카페를 제외하고, 서로 다른 {n}개의 카페를 반환하세요.
                기존에 추천된 카페: {existing_spot_names}
                """,
                expected_output="""
                spot_time 예상 방문 시간을 `hh:00` 형식으로 반환하고, 모두 다른 값으로 해주세요.
                spot_category는 **항상 3**으로 고정해주세요
                day_x는 {days}일의 여행 일정 중 몇일차인지 입니다.(만약, day_x:1 이라면 1일차에 방문한다는 의미)  
                order는 하루 중 몇번째로 방문할지에 대한 순서입니다. order_x가 바뀔때마다 1부터 새로 시작하며, spot_time을 기준으로 오름차순 정렬해주세요.
                business_status는 boolean으로 반환해주세요.
                """,
                context=[],        
                agent=self.agents["decider"],
                output_pydantic=spots_pydantic
            )
        }     
    @time_token_check
    async def create_recommendation_cafe(
        self, input_data: dict, session: AsyncSession = None, redis_client: Redis = None) -> dict:
        """
        사용자 맞춤 카페를 추천하는 에이전트
        """
        try:
            # 1. 이메일과 session이 있으면 member_id 조회
            member_id = ""
            if input_data.get("email") and session:
                member_id = await get_memberId_by_email(input_data["email"], session) or ""
                logger.info(f"member_id 존재: {bool(member_id)}")

            # 2. 필수 요소 존재 여부 로깅
            logger.info(f"email 존재: {bool(input_data.get('email'))}")
            logger.info(f"session 존재: {bool(session)}")
            logger.info(f"redis 존재: {bool(redis_client)}")
            logger.info(f"plan_id 없음: {not input_data.get('plan_id')}")

            # 3. 서비스 초기화
            redis_service = SpotRedisService(redis_client)
            caching_service = SpotCachingService(redis_client)

            # 4. Redis 캐싱에서 카페 목록 조회
            cached_cafe_lists = await caching_service.get_spots(category=SpotCategory.CAFE, main_location=input_data["main_location"]) or []
            logger.info(f"찾은 cached_cafe_lists 개수: {len(cached_cafe_lists)}")
            logger.info("----------------------------------------------------")

            # 5. 프롬프트용 입력 데이터 구성
            input_data["concepts"] = ', '.join(input_data.get('concepts', []))
            days = calculate_trip_days(input_data.get('start_date', ''), input_data.get('end_date', ''))
            input_data["days"] = days
            input_data["n"] = 5 if input_data.get("prompt") else days * 2
            input_data["existing_spot_names"] = []
            input_data["member_id"] = member_id

            # 6. 캐싱된 카페 수가 충분하면 draft 에이전트를 사용
            if (not input_data.get("prompt")) and len(cached_cafe_lists) >= days * 2:
                try:
                    logger.info("저장된 카페 수가 충분해 redis 내에서 추천합니다")
                    logger.info("----------------------------------------------------")
                    input_data["cached_cafe_lists"] = cached_cafe_lists

                    draft_result = await self.draft_crew.kickoff_async(inputs=input_data)
                    spots_dict = draft_result.pydantic.model_dump()
                    spots_dict["token_usage"] = draft_result.token_usage.__dict__
                    logger.info(f"----------draft_result.token_usage: {draft_result.token_usage.__dict__}")      
                    
                    cafes_to_save = [spot["kor_name"] for spot in spots_dict.get("spots", [])]
                    logger.info(f"spots to save: {cafes_to_save}")

                    await redis_service.add_spots(
                        member_id=member_id,
                        category=SpotCategory.CAFE,
                        main_location=input_data["main_location"],
                        spots=cafes_to_save,
                    )
                    return spots_dict
                except Exception as e:
                    logger.error(f"Redis 저장 중 오류 발생: {e}")
                    traceback.print_exc()

            # 7. 캐싱된 정보가 부족할 경우 캐싱 데이터를 비움
            logger.info("4단계의 cafe_crew를 실행합니다")
            logger.info("----------------------------------------------------")

            input_data["cached_cafe_lists"] = ""

            # 8. 신규 일정인지 기존 일정인지에 따라 기존 장소 데이터 조회
            if not input_data.get("plan_id"):
                # 신규 일정: Redis에서 제외할 장소 조회
                logger.info("새로 생성된 일정: Redis 사용 로직 실행 시작")
                try:
                    redis_excluded_spots = await redis_service.get_spots(
                        member_id=member_id,
                        category=SpotCategory.CAFE,  # 필요에 따라 SpotCategory.CAFE로 수정 가능
                        main_location=input_data["main_location"],
                    )
                    if redis_excluded_spots:
                        input_data["existing_spot_names"] = redis_excluded_spots
                        logger.info(f"Redis에서 가져온 제외 카페 목록: {redis_excluded_spots}")
                except Exception as e:
                    logger.error(f"Redis 조회 중 오류 발생: {e}")
            else:
                # 기존 일정 수정: DB에서 기존 장소 조회
                current_plan_id = input_data.get("plan_id")
                logger.info(f"current_plan_id: {current_plan_id}")
                try:
                    plan_spots_with_spot_info = await get_member_plan_spots(plan_id=current_plan_id, member_id=member_id, category_id=3, session=session)
                    if not plan_spots_with_spot_info:
                        latest_plan = await get_latest_plan(member_id, session)
                        if latest_plan:
                            plan_spots_with_spot_info = await get_member_plan_spots(plan_id=latest_plan.id, member_id=member_id, category_id=3,session=session)
                            logger.info(f"최신 plan_id 사용: {latest_plan.id}")
                    else:
                        logger.info(f"전달받은 plan_id 사용: {current_plan_id}")

                    if plan_spots_with_spot_info and "detail" in plan_spots_with_spot_info:
                        existing_spot_names = [
                            item["spot"].kor_name for item in plan_spots_with_spot_info["detail"]
                        ]
                        logger.info(f"DB에서 가져온 기존 장소들: {existing_spot_names}")
                        input_data["existing_spot_names"] = existing_spot_names
                except Exception as e:
                    logger.error(f"DB 장소 조회 중 오류 발생: {e}")
                    traceback.print_exc()

            # 9. 메인 에이전트를 실행하여 카페 추천 결과 도출
            result = await self.crew.kickoff_async(inputs=input_data)
            spots = result.pydantic.model_dump()
            spots["token_usage"] = result.token_usage.__dict__

            # logger.info(f"----------result.token_usage: {result.token_usage}")      
            logger.info(f"----------result.token_usage.__dict__: {result.token_usage.__dict__}")      
     
            # 10. 새로 찾은 카페들을 Redis 캐싱(하루 뒤 만료)
            spots_dummies = self.tasks['reviewer_task'].output.pydantic.model_dump()
            await caching_service.add_spots(
                category=SpotCategory.CAFE,
                main_location=input_data["main_location"],
                spots=spots_dummies
            )

            # 11. 신규 일정인 경우 Redis에 결과 저장
            if not input_data.get("plan_id") and redis_client:
                try:
                    cafes_to_save = [spot["kor_name"] for spot in spots.get("spots", [])]
                    logger.info(f"spots to save: {cafes_to_save}")

                    await redis_service.add_spots(
                        member_id=member_id,
                        category=SpotCategory.CAFE,
                        main_location=input_data["main_location"],
                        spots=cafes_to_save,
                    )
                except Exception as e:
                    logger.error(f"Redis 저장 중 오류 발생: {e}")
                    traceback.print_exc()

            return spots

        except Exception as e:
            logger.error(f"[cafe agent error] --- cafe agent error {str(e)}")