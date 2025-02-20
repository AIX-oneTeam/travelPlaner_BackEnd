import traceback
from crewai import Agent, Task, Crew, LLM, Process
from app.dtos.spot_models import spots_pydantic
from app.utils.calculate_trip_days import calculate_trip_days
from app.services.agents.tools.cafe_tool import NaverBlogSearchTool,NaverBlogCralwerTool,NaverReviewCralwerTool, NaverBusinessInfoTool
from typing import Dict, Optional
import os
from dotenv import load_dotenv
from app.utils.time_check import time_check
from app.dtos.cafe_models import CafeList
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
from redis.asyncio import Redis
import json
import logging
from sqlmodel.ext.asyncio.session import AsyncSession
from app.repository.agents.plan_spots_repository import (
    get_member_plan_spots,
    get_latest_plan,
)
from app.repository.members.mebmer_repository import get_memberId_by_email
from app.services.agents.redis.spot_redis import SpotRedisService, SpotCategory

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
        self.get_cafe_list_tool = NaverBlogSearchTool()
        self.get_cafe_info_tool = NaverBlogCralwerTool()
        self.get_cafe_review_tool = NaverReviewCralwerTool()
        self.get_cafe_business_info_tool = NaverBusinessInfoTool()
        self.agents = self._create_agents()
        self.tasks = self._create_tasks()
        
        self.tasks["researcher_task"].context = [self.tasks["collector_task"]]
        self.tasks["researcher_detail_task"].context = [self.tasks["researcher_task"]]
        self.tasks["reviewer_task"].context = [self.tasks["researcher_detail_task"]]
        self.tasks["decider_task"].context = [self.tasks["reviewer_task"]]
        self.draft_crew = Crew(agents=[self.agents['decider']], tasks=[self.tasks['decider_task']], verbose=True)  
        self.crew = Crew(agents=list(self.agents.values()), tasks=list(self.tasks.values()),process=Process.sequential, verbose=True)  

    def _create_agents(self) -> Dict[str, Agent]:
        return {
            "collector" : Agent(
                role="카페 리스트 생성 전문가",
                goal="포스팅된 횟수가 많은 카페부터 내림차순으로 정렬해주세요",
                backstory="""
                포스팅된 횟수가 많은 카페부터 내림차순으로 정렬해주세요
                """,
                tools=[self.get_cafe_list_tool],
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True
            ),
            "researcher" : Agent(
                role="카페 기본 정보 수집 및 위치 검증가",
                goal="카페의 기본 정보를 수집하고 고객의 여행 지역에 위치하지 않은 카페는 삭제합니다.",
                backstory="""
                블로그에서 카페의 기본 정보를 수집하고, 고객의 여행 지역에 위치하지 않은 카페는 리스트에서 삭제해주세요. 
                """,
                tools=[self.get_cafe_info_tool],
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True
            ),
            "researcher_detail" : Agent(
                role="카페 상세 정보 수집 및 업종 검증가",
                goal="카페의 상세 정보를 수집하고 업종에 카페 또는 베이커리가 포함되지 않은 장소는 삭제합니다.",
                backstory="""
                카페의 상세 정보를 수집하고, 업종에 카페 또는 베이커리가 포함되지 않은 장소는 리스트에서 삭제해주세요. 
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
                카페의 최신 후기를 읽고, 카페의 주요 특징을 분석합니다. 반드시 researcher_detail가 반환한 카페의 수만큼 카페를 반환해주세요.          
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
                1. tool 사용시 "{main_location}"과 "keywords"를 순서대로 입력하세요.
                - keywords : 고객의 요구사항({prompt}), 여행 컨셉({concepts})을 반영한 키워드 리스트
                - 각각의 키워드는 하나의 형용사 또는 명사여야 하고, "카페"와 "지역명" "추천"은 제외해주세요.
                - 키워드는 최대 3개까지만 입력 가능합니다. 여러개의 키워드가 같은 의미라면 1가지 키워드만 사용하세요.
                2. 카페별로 포스팅 된 url을 모아 정리하고, 설명을 요약해주세요. 
                3. 포스팅 횟수가 많은 카페 순으로 내림차순 정렬해주세요
                tool output이 반환한 모든 url을 빠짐없이 정리해주세요.
                """,
                expected_output="""
                1. "keywords" : 사용한 키워드 리스트
                2. "n_cafe":"총 찾은 카페 갯수"
                3. 카페별 리스트
                - "name": "카페 이름"
                - "n_posting": "포스팅 url 갯수"
                - "blog_urls" : "블로그 url 리스트"
                """,        
                agent=self.agents["collector"],
            ),
            "researcher_task" : Task(
                description="""
                1. 카페 이름별로 url 리스트를 만들어 딕셔너리 타입으로 tool의 input으로 사용하세요. url은 None값이나 null이면 안됩니다. 
                tool input 예시: 
                - "카페A": ["url1", "url2", "url3"],
                - "카페B": ["url4", "url5"],
                2. tool의 output을 보고 address가 {main_location}에 위치하지 않은 카페는 삭제해주세요.
                """,
                expected_output="""
                중복되지 않는 카페 리스트를 반환해주세요.
                1. "keywords" : 사용한 키워드 리스트
                2. "n_cafe":"총 찾은 카페 갯수"             
                3. 카페 리스트
                - "name": "카페이름"
                - "n_posting": "포스팅 url 갯수"
                - "placeId": "placeId"
                - "address": "카페주소"
                - "img_url": "img_url"
                - "latitude": "latitude"
                - "longitude": "longitude"
                - "phone_number": "전화번호"
                """,        
                agent=self.agents["researcher"],
                context=[]
            ),
            "researcher_detail_task" : Task(
                description="""
                1. researcher가 반환한 카페들의 placeId를 리스트로 묶어 tool의 input값으로 사용하세요.
                2. tool의 output을 보고 카페의 세부 정보를 수집하고, category에 "카페" 또는 "베이커리"가 포함 되지 않은 장소는 삭제해주세요.
                """,
                expected_output="""
                중복되지 않는 카페 리스트를 반환해주세요.
                1. "keywords" : 사용한 키워드 리스트
                2. "n_cafe":"총 찾은 카페 갯수"             
                3. 카페 리스트             
                - "name": "카페이름"
                - "n_posting": "포스팅 횟수"
                - "placeId": "placeId"
                - "address": "카페주소"
                - "img_url": "img_url"
                - "latitude": "latitude"
                - "longitude": "longitude"
                - "phone_number": "전화번호"
                - "url": "홈페이지url",
                - "business_hour": "운영시간",
                - "category": "업종"
                """,        
                agent=self.agents["researcher_detail"],
                context=[]
            ),
            "reviewer_task" : Task(
                description="""
                1. researcher_detail이 반환한 카페들의 placeId를 리스트로 묶어 tool의 input값으로 사용하세요.
                2. 반드시 researcher_detail이 반환한 카페들의 placeId 갯수 만큼 카페를 반환해주세요.
                3. researcher_detail이 반환한 값에 tool_output의 정보를 합쳐 반환해주세요. 
                4. 카페 특징은 고객 요구사항에 맞는 카페인지 점검할 수 있도록 구체적으로 써주세요.
                5. 포스팅 횟수가 많고, 긍정적인 리뷰가 많은 카페부터 나열해주세요.
                """,
                expected_output="""
                중복되지 않는 카페 리스트를 반환해주세요.
                반드시 researcher_detail이 반환한 카페들의 placeId 갯수 만큼 카페를 반환해주세요.
                main_location: {main_location}
                map_url: "https://map.kakao.com/link/map/"위도","경도"
                """,        
                agent=self.agents["reviewer"],
                output_pydantic=CafeList,
                context=[]
            ),
            "decider_task" : Task(
                description="""
                1. 고객의 요구사항({prompt}), 여행 컨셉({concepts}), 주 연령대({ages})가 반영된 카페를 가장 우선적으로 선택하세요.
                2. 포스팅 횟수가 많고, 긍정적인 리뷰가 많은 카페부터 나열해주세요.
                3. description에는 카페의 주요 특징과 시그니처메뉴, 사람들이 공통적으로 좋아했던 부분을 요약해주세요.
                4. 모르는 정보는 지어내지 말고 "정보 없음"으로 작성하세요.
                5. 중복되지 않은 서로 다른 카페 리스트를 반환해주세요.
                참고 카페 리스트 : {cached_cafe_lists}
                반드시 서로 다른 {n}개의 카페를 반환하세요.
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
    @time_check   
    async def create_recommendation_cafe(
        self, input_data: dict, session: AsyncSession = None, redis_client: Redis = None) -> dict:
        """
        사용자 맞춤 카페를 추천하는 에이전트
        """  
        try:
            existing_spot_names = []
            member_id = None

            # 데이터 유무 확인
            logger.info(f"🔵 email 존재: {bool(input_data.get('email'))}")
            logger.info(f"🔵 session 존재: {bool(session)}")
            logger.info(f"🔵 redis 존재: {bool(redis_client)}")
            logger.info(f"🔵 plan_id 없음: {not input_data.get('plan_id')}")
            
            # member_id 조회 Redis/DB 로직 실행(중복확인)
            if input_data.get("email") and session:
                member_id = await get_memberId_by_email(input_data["email"], session)
                logger.info(f"🔵 member_id 조회됨: {bool(member_id)}")

                if not input_data.get("plan_id"):
                    # 새로 생성된 일정이거나 plan_id 없는 경우 - Redis 사용
                    logger.info("🟢 새로 생성된 일정: Redis 사용 로직 실행 시작")
                    try:
                        redis_service = SpotRedisService(redis_client)
                        redis_excluded_spots = await redis_service.get_spots(
                            category=SpotCategory.RESTAURANT,
                            main_location=input_data["main_location"],
                        )
                        if redis_excluded_spots:
                            existing_spot_names = redis_excluded_spots
                            logger.info(
                                f"🟢 Redis에서 가져온 제외 식당 목록: {redis_excluded_spots}"
                            )
                    except Exception as e:
                        logger.error(f"Redis 조회 중 오류 발생: {e}")
                else:
                    # 기존 일정 수정의 경우 - DB 사용
                    current_plan_id = input_data.get("plan_id")
                    print(f"🟡 current_plan_id: {current_plan_id}")

                    try:
                        # 현재 plan이 해당 member의 것인지 확인
                        plan_spots_with_spot_info = await get_member_plan_spots(
                            current_plan_id, member_id, session
                        )

                        if not plan_spots_with_spot_info:
                            latest_plan = await get_latest_plan(member_id, session)
                            if latest_plan:
                                plan_spots_with_spot_info = await get_member_plan_spots(
                                    latest_plan.id, member_id, session
                                )
                                logger.info(f"🟡 최신 plan_id 사용: {latest_plan.id}")
                        else:
                            logger.info(f"🟡 전달받은 plan_id 사용: {current_plan_id}")

                        if (
                            plan_spots_with_spot_info
                            and "detail" in plan_spots_with_spot_info
                        ):
                            existing_spot_names = [
                                item["spot"].kor_name
                                for item in plan_spots_with_spot_info["detail"]
                            ]
                            logger.info(
                                f"🟡 DB에서 가져온 기존 장소들: {existing_spot_names}"
                            )
                    except Exception as e:
                        logger.error(f"🟡 DB 장소 조회 중 오류 발생: {e}")
                        traceback.print_exc()
                        
            # 프롬프팅을 위한 input 데이터 추가
            input_data["concepts"] = ', '.join(input_data.get('concepts',[]))
            days = calculate_trip_days(input_data.get('start_date',''),input_data.get('end_date',''))
            input_data["days"] = days
            input_data["n"] = 5 if input_data["prompt"] else days*2
            input_data["existing_spot_names"] = existing_spot_names
            input_data["member_id"] = member_id
            input_data["cached_cafe_lists"] = ""
            
            # 에이전트 실행
            result = await self.crew.kickoff_async(inputs=input_data)
            
            # plan_id가 없는 경우, 결과를 Redis에 저장
            if not input_data.get("plan_id") and redis_client:
                try:
                    redis_service = SpotRedisService(redis_client)
                    restaurants_to_save = [
                        spot["kor_name"] for spot in result.get("spots", [])
                    ]
                    logger.info(f"🟢 spots to save: {restaurants_to_save}")

                    await redis_service.add_spots(
                        category=SpotCategory.RESTAURANT,
                        main_location=input_data["main_location"],
                        spots=restaurants_to_save,
                    )
                except Exception as e:
                    logger.error(f"Redis 저장 중 오류 발생: {e}")
                    traceback.print_exc()
                
                return result.pydantic.model_dump()           
        except Exception as e:
            logger.info(f"[CafeAgent] 에러 - {e}")                
                
# {
#   "ages": "20대",
#   "companion_count": [
#     {
#       "label": "성인",
#       "count": 2
#     }
#   ],
#   "start_date": "2025-02-12",
#   "end_date": "2025-02-12",
#   "concepts": [
#     "힐링"
#   ],
#   "main_location": "서울",
#   "prompt": ""
# }