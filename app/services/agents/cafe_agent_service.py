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


def save_cafe_info(cafe_data_list:CafeList, redis_client:Redis):
    try:
        for cafe_data in cafe_data_list:
            cafe_id = cafe_data["placeId"]
            redis_client.set(f"cafe:{cafe_id}", json.dumps(cafe_data))
            tags = [cafe_data["main_location"]] + cafe_data["keywords"]
            for tag in tags:
                redis_client.sadd(f"tag:{tag}", cafe_id)
        return "[CafeAgentService] : 성공적으로 저장되었습니다."
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"[CafeAgentService] - save_cafe_info : 저장 중 오류 발생: {error_details}")
        return f"[CafeAgentService] - save_cafe_info :저장 중 오류 발생: {str(e)}"

    
async def search_cafes(main_location:str, redis_client:Redis):
    """ 특정 지역의 모든 카페 조회 """
    # 해당 지역의 카페 ID들 조회
    cafe_ids = await redis_client.smembers(f"tag:{main_location}")
    
    # 카페 상세 정보 조회
    results = [json.loads(await redis_client.get(f"cafe:{cafe_id}")) for cafe_id in cafe_ids]
    return results
            
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
        self.tasks["reviewer_task"].context = [self.tasks["researcher_task"]]
        self.tasks["Decider_task"].context = [self.tasks["reviewer_task"]]
        self.draft_crew = Crew(agents=[self.agents['collector']], tasks=[self.tasks['collector_task']], verbose=True)  
        self.crew = Crew(agents=list(self.agents.values()), tasks=list(self.tasks.values()),process=Process.sequential, verbose=True)  

    def _create_agents(self) -> Dict[str, Agent]:
        return {
            "collector" : Agent(
                role="카페 선별 및 리스트 생성 전문가",
                goal="고객의 여행지역에 있는 카페들을 찾고 고객의 조건에 부합하는 카페들의 후보 리스트를 작성합니다. 카페의 중복은 없어야 합니다.",
                backstory="""
                사용자의 여행 지역에 있는 카페를 찾고 고객이 좋아할 것 같은 카페들을 중복되지 않게 정리해주세요.
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
                tools=[self.get_cafe_business_info_tool],
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
                - keywords : 고객의 요구사항({prompt}), 여행 컨셉({concepts}을 반영한 키워드 리스트
                2. 카페별로 포스팅 된 url을 모아 정리하고, 설명을 요약해주세요.
                3. 포스팅 횟수가 많은 카페 순으로 내림차순 정렬해주세요
                4. 포스팅 횟수가 동일한 카페들은 "비추' 등의 부정적인 의견이 적은 포스팅부터 먼저 나열해주세요. 
                5. 카페 추천 또는 카페 후기가 아닌 글은 삭제해주세요 
                """,
                expected_output="""
                - 카페 이름
                - 포스팅 횟수
                - 카페 설명
                - 블로그 url (포스팅 횟수 만큼)
                """,        
                agent=self.agents["collector"],
            ),
            "researcher_task" : Task(
                description="""
                1. collector가 조사한 블로그들의 url만 리스트로 묶어 tool의 input으로 사용하세요. url은 None값이나 null이면 안됩니다. 
                2. tool의 output을 보고 address가 {main_location}에 위치하지 않은 카페는 삭제해주세요.
                3. 카페가 아닌 호텔, 리조트 등의 숙소나 미용실 등 다른 업종인 경우 삭제해주세요.
                4. 포스팅 횟수가 많은 카페 순으로 내림차순 정렬해주세요
                5. 포스팅 횟수가 동일한 카페들은 "비추' 등의 부정적인 의견이 적은 포스팅부터 먼저 나열해주세요. 
                """,
                expected_output="""             
                - 이름
                - 포스팅 횟수
                - 카페 설명
                - placeId
                - 주소
                - 이미지url
                - 위도
                - 경도
                - 전화번호
                - 홈페이지url
                - 운영 시간(모르는 경우 "정보 없음")
                """,        
                agent=self.agents["researcher"],
                context=[]
            ),
            "reviewer_task" : Task(
                description="""
                1. researcher가 반환한 카페들의 placeId를 리스트로 묶어 tool의 input값으로 사용하세요.
                2. researcher가 반환한 값에 tool_output의 정보를 합쳐 반환해주세요. 
                3. 카페 특징은 Decider가 고객 요구사항에 맞는 카페인지 점검할 수 있도록 구체적으로 써주세요.
                4. 포스팅 횟수가 많고, 긍정적인 리뷰가 많은 카페부터 나열해주세요.
                5. 리뷰를 보고, 카페가 아닌 식당, 미용실, 호텔, 리조트 등의 경우 삭제해주세요.
                """,
                expected_output="""
                중복되지 않는 카페 리스트를 반환해주세요.
                """,        
                agent=self.agents["reviewer"],
                output_json=CafeList,
                context=[],
                callback=save_cafe_info
            ),
            "decider_task" : Task(
                description="""
                1. 고객의 요구사항({prompt}), 여행 컨셉({concepts}), 주 연령대({ages})가 반영된 카페를 가장 우선적으로 선택하세요.
                2. 포스팅 횟수가 많고, 긍정적인 리뷰가 많은 카페부터 나열해주세요.
                3. placeId를 리스트로 묶어 tool의 input값으로 사용해 각 카페의 운영 시간과 웹사이트 정보를 수집하세요.
                4. description에는 카페의 주요 특징과 시그니처메뉴, 사람들이 공통적으로 좋아했던 부분을 요약해주세요.
                5. 모르는 정보는 지어내지 말고 "정보 없음"으로 작성하세요.
                6. {main_location}에 위치한 카페만 선택하세요.
                7. 호텔, 리조트 등의 숙소나 미용실 등 다른 업종인 경우 선택하지 마세요.
                참고 카페 리스트 : {cached_cafe_lists}
                """,
                expected_output="""
                prompt({prompt})가 유효한 값(빈 문자열(""), None, 또는 null이 아닌 경우)이면 5개의 카페를, 그렇지 않으면 {n}*2개의 카페를 반환하세요.
                spot_time 예상 방문 시간을 `hh:00` 형식으로 반환하고, 모두 다른 값으로 해주세요.
                order는 방문할 순서입니다. spot_time을 기준으로 빠른 시간부터 오름차순 정렬해주세요. 순서는 1부터 시작합니다.
                spot_category는 항상 3으로 고정해주세요
                day_x는 {n}일의 여행 일정 중 몇일차인지 입니다.(만약, day_x:1 이라면 1일차에 방문한다는 의미)  
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
        input_data["n"] = calculate_trip_days(input_data.get('start_date',''),input_data.get('end_date',''))

        if redis_client is None:
            raise ValueError("[CafeAgent] 에러 - Redis 연결을 확인해주세요")
  
        try:
            cached_cafe_lists = await search_cafes(input_data["main_location"], redis_client)
            print(f"cached_cafe_lists: {cached_cafe_lists}")
            if len(cached_cafe_lists) < (input_data["n"])*2:
                try:
                    result = await self.crew.kickoff_async(inputs=input_data)
                    save_cafe_info()
                    return result.pydantic.model_dump()
                except Exception as e:
                    print(f"[CafeAgent] 에러: {e}")
                    error_details = traceback.format_exc()
                    print(f"[CafeAgent] 상세 에러: {error_details}")
                    raise e  # 또는 적절한 에러 메시지를 담아 반환                   
            else:
                input_data["cached_cafe_lists"] = cached_cafe_lists
                try:
                    result = await self.draft_crew.kickoff_async(inputs=input_data)
                    print(f"result:{result}")
                    return result.pydantic.model_dump()
                except Exception as e:
                    print(f"[CafeAgent] 에러: {e}")
                    error_details = traceback.format_exc()
                    print(f"[CafeAgent] 상세 에러: {error_details}")
                    raise e  # 또는 적절한 에러 메시지를 담아 반환   
                
        except Exception as e:
            print(f"[CafeAgent] 에러 - redis에서 정보 불러오기 실패: {e}")    
        
        if cached_cafe_lists:
            return None
        try:
            result = await self.crew.kickoff_async(inputs=input_data)
            print(f"result:{result}")
            return result.pydantic.model_dump()
        except Exception as e:
            print(f"[CafeAgent] 에러: {e}")
            error_details = traceback.format_exc()
            print(f"[CafeAgent] 상세 에러: {error_details}")
            raise e  # 또는 적절한 에러 메시지를 담아 반환               
                
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