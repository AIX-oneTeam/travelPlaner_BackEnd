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
from fastapi import HTTPException, Depends
from app.repository.redis_client import get_redis
from redis.asyncio import Redis
import json
from sqlalchemy.ext.asyncio import AsyncSession


async def save_cafe_info(cafe_data_list: dict, redis_client:Redis):
    try:
        # 개별 카페 데이터 저장
        for cafe_data in cafe_data_list.get("spots", []):
            cafe_id = cafe_data["placeId"]
            await redis_client.set(f"cafe:{cafe_id}", json.dumps(cafe_data))
            
            tags = [cafe_data["main_location"]] + cafe_data["keywords"]
            for tag in tags:
                await redis_client.sadd(f"tag:{tag}", cafe_id)
        return "[CafeAgentService] : 성공적으로 저장되었습니다."

    except Exception as e:
        error_details = traceback.format_exc()
        print(f"[CafeAgentService] - save_cafe_info : 저장 중 오류 발생: {error_details}")
        return f"[CafeAgentService] - save_cafe_info : 저장 중 오류 발생: {str(e)}"
            
async def get_cafes_by_tag(tag: str, redis_client: Redis):
    """
    특정 태그(지역 또는 키워드)에 해당하는 모든 카페 조회
    """
    cafe_ids = await redis_client.smembers(f"tag:{tag}")  # 태그에 해당하는 placeId 리스트 가져오기

    if not cafe_ids:
        print(f"[CafeAgentService] - 태그 '{tag}'에 해당하는 카페를 찾을 수 없습니다.")
        return None
    cafes = []
    for cafe_id in cafe_ids:
        cafe_data = await redis_client.get(f"cafe:{cafe_id}")
        if cafe_data:
            cafes.append(json.loads(cafe_data))

    return cafes
            
            
class CafeAgentService:
    """
    카페 에이전트 인스턴스를 싱글톤 패턴으로 관리하는 클래스
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CafeAgentService, cls).__new__(cls)
            cls._instance.initialize()  # 최초 한 번만 초기화
        return cls._instance  # 동일한 인스턴스 반환

    def initialize(self):
        """CrewAI 관련 객체들을 한 번만 생성"""
        #print("cafe agent를 초기화합니다")
                
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
                goal="카페의 상세 정보를 수집하고 업종이 카페가 아닌 장소는 삭제합니다.",
                backstory="""
                카페의 상세 정보를 수집하고, 카페가 아닌 장소는 리스트에서 삭제해주세요. 
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
                카페의 최신 후기를 읽고, 카페의 주요 특징을 분석합니다. 리뷰를 읽고 카페가 아니라면 리스트에서 삭제해주세요.               
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
                - 키워드는 최대 3개까지만 입력 가능합니다.
                2. 카페별로 포스팅 된 url을 모아 정리하고, 설명을 요약해주세요. 
                3. 포스팅 횟수가 많은 카페 순으로 내림차순 정렬해주세요
                tool output이 반환한 모든 url을 빠짐없이 정리해주세요.
                """,
                expected_output="""
                1. "keywords" : 사용한 키워드 리스트
                2. n_cafe:"총 찾은 카페 갯수"
                3. 카페 리스트
                - "name": "카페 이름"
                - "n_posting": "포스팅 횟수"
                - "blog_urls" : "블로그 url 리스트"
                """,        
                agent=self.agents["collector"],
            ),
            "researcher_task" : Task(
                description="""
                1. collector가 조사한 블로그들의 url만 리스트로 묶어 tool의 input으로 사용하세요. url은 None값이나 null이면 안됩니다. 
                2. tool의 output을 보고 address가 {main_location}에 위치하지 않은 카페는 삭제해주세요.
                """,
                expected_output="""
                1. "keywords" : 사용한 키워드 리스트
                2. n_cafe:"총 찾은 카페 갯수"             
                3. 카페 리스트
                - "name": "카페이름"
                - "n_posting": "포스팅 횟수"
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
                2. tool의 output을 보고 카페의 세부 정보를 수집하고, category에 "카페"가 포함 되지 않은 장소는 삭제해주세요.
                """,
                expected_output="""
                1. "keywords" : 사용한 키워드 리스트
                2. n_cafe:"총 찾은 카페 갯수"             
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
                2. 반드시 tool_output이 반환한 카페의 수 만큼 카페를 반환해주세요.
                3. researcher_detail이 반환한 값에 tool_output의 정보를 합쳐 반환해주세요. 
                4. 카페 특징은 고객 요구사항에 맞는 카페인지 점검할 수 있도록 구체적으로 써주세요.
                5. 포스팅 횟수가 많고, 긍정적인 리뷰가 많은 카페부터 나열해주세요.
                """,
                expected_output="""
                중복되지 않는 카페 리스트를 반환해주세요.
                main_location: {main_location}
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
                고객 요구사항({prompt})이 없으면 5개 이상의 카페를, 그렇지 않으면 {n}개의 카페를 반환하세요.
                """,
                expected_output="""
                spot_time 예상 방문 시간을 `hh:00` 형식으로 반환하고, 모두 다른 값으로 해주세요.
                spot_category는 항상 3으로 고정해주세요
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
    async def create_recommendation(self, input_data: dict, 
                                    prompt: Optional[str] = None,
                                    redis_client: Redis = None) -> dict:
        """
        사용자 맞춤 카페를 추천하는 에이전트
        """
        if input_data is None:
            raise ValueError("[CafeAgent] 에러 - input_data이 없습니다. 잘못된 요청을 보냈는지 확인해주세요")
       
        input_data["concepts"] = ', '.join(input_data.get('concepts',[]))
        input_data["prompt"] = prompt
        days = calculate_trip_days(input_data.get('start_date',''),input_data.get('end_date',''))
        input_data["days"] = days
        input_data["n"] = days*2
        
        if redis_client is None:
            raise ValueError("[CafeAgent] 에러 - Redis 연결을 확인해주세요")
  
        try:
            cached_cafe_lists = await get_cafes_by_tag(input_data["main_location"], redis_client) or []
            print(f"cached_cafe_lists: {cached_cafe_lists}")
            input_data["cached_cafe_lists"] = cached_cafe_lists
            if len(cached_cafe_lists) < days*2:
                try:
                    result = await self.crew.kickoff_async(inputs=input_data)
                    reviewer_result = self.tasks['reviewer_task'].output.pydantic.model_dump()
                    print(f"reviewr_task_output_raw:{reviewer_result}")
                    await save_cafe_info(reviewer_result,redis_client)
                    print(f"result : {result}")
                    return result.pydantic.model_dump()
                except Exception as e:
                    print(f"[CafeAgent] 에러: {e}")
                    error_details = traceback.format_exc()
                    print(f"[CafeAgent] 상세 에러: {error_details}")
                    raise e  # 또는 적절한 에러 메시지를 담아 반환                   
            else:
                try:
                    result = await self.draft_crew.kickoff_async(inputs=input_data)
                    print(f"result-draft-crew:{result}")
                    return result.pydantic.model_dump()
                except Exception as e:
                    print(f"[CafeAgent] 에러: {e}")
                    error_details = traceback.format_exc()
                    print(f"[CafeAgent] 상세 에러: {error_details}")
                    raise e  # 또는 적절한 에러 메시지를 담아 반환   
                
        except Exception as e:
            print(f"[CafeAgent] 에러 - {e}")                
                
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