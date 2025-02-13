from typing import List
from crewai import Agent, Task, Crew, LLM, Process
from app.dtos.spot_models import spots_pydantic,calculate_trip_days
from app.services.agents.tools.cafe_tool import NaverWebSearchTool,NaverBlogCralwerTool,NaverReviewCralwerTool
from app.services.agents.tools.restaurant_tool import NaverImageSearchTool
from typing import List, Dict, Optional
import os
from dotenv import load_dotenv
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        
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
        self.get_cafe_list_tool = NaverWebSearchTool()
        self.get_cafe_info_tool = NaverBlogCralwerTool()
        self.get_cafe_review_tool = NaverReviewCralwerTool()
        self.get_cafe_image_tool = NaverImageSearchTool()
        self.agents = self._create_agents()
        self.tasks = self._create_tasks()
        
        if "researcher_task" in self.tasks and "reviewr_task" in self.tasks:
            self.tasks["reviewr_task"].context = [self.tasks["researcher_task"]]
    
        if "researcher_task" in self.tasks and "reviewr_task" in self.tasks and "Decider_task" in self.tasks:
            self.tasks["Decider_task"].context = [self.tasks["researcher_task"], self.tasks["reviewr_task"]]
        
        self.crew = Crew(agents=list(self.agents.values()), tasks=list(self.tasks.values()),verbose=True)  

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
                goal="카페의 기본 정보를 수집하고 고객의 여행지역에 없는 카페들은 삭제합니다",
                backstory="""
                블로그에서 카페의 기본 정보를 수집하고, 고객의 여행 지역에 없는 카페의 정보는 리스트에서 삭제해주세요. 
                """,
                tools=[self.get_cafe_info_tool],
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True
            ),
            "reviewr" : Agent(
                role="카페의 리뷰를 분석하고, 카페의 특징을 추출합니다.",
                goal="카페의 리뷰를 분석하고, 카페의 주요 특징과 분위기, 시그니처 메뉴를 추출합니다.",
                backstory="""
                카페의 최신 후기를 읽고, 카페의 주요 특징을 분석합니다.               
                """,
                tools=[self.get_cafe_review_tool],
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True
            ),
            "Decider" : Agent(
                role="카페의 특징을 사용",
                goal="고객의 여행지에서 인기있고, 고객의 선호도를 반영한 카페를 선정합니다.",
                backstory="""
                고객에게 가장 적합한 카페를 선별하고 추천해줍니다.
                """,
                tools=[self.get_cafe_image_tool],
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
                1. tool 사용시 "{main_location} 카페"로 검색하세요
                2. 중복된 카페는 삭제해주세요
                3. "비추' 등의 부정적인 의견이 있는 글은 삭제해주세요
                4. 카페 추천 또는 카페 후기가 아닌 글은 삭제해주세요 
                """,
                expected_output="""
                - 카페이름
                - 네이버 블로그 url
                """,        
                agent=self.agents["collector"],
            ),
            "researcher_task" : Task(
                description="""
                1. collector가 조사한 블로그들의 url만 리스트로 묶어 tool의 input으로 사용하세요. url은 None값이나 null이면 안됩니다. 
                2. tool의 output을 보고 address가 {main_location}에 위치하지 않은 카페는 삭제해주세요.
                """,
                expected_output="""
                tool의 output에서 {main_location}에 위치하지 않은 카페만 삭제하고 그대로 반환해주세요.
                """,        
                agent=self.agents["researcher"],
            ),
            "reviewr_task" : Task(
                description="""
                1. researcher가 반환한 카페들의 placeId를 리스트로 묶어 tool의 input값으로 사용하세요.
                2. researcher가 반환한 값에 tool_output의 정보를 합쳐 반환해주세요. 
                """,
                expected_output="""
                중복되지 않는 카페 리스트를 반환해주세요.
                - 이름
                - 특징(분위기, 시그니처 메뉴, 사람들이 공통 적으로 좋아했던 특징, 리뷰 요약)
                - 주소
                - 위도
                - 경도
                - 홈페이지
                """,        
                agent=self.agents["reviewr"],
                context=[]
            ),
            "Decider_task" : Task(
                description="""
                1. 고객의 요구사항({prompt_text}), 여행 컨셉({concepts}), 주 연령대({ages})를 반영해 카페를 선택해주세요.
                2. reviewr가 반환한 특징을 참고해 부정적인 의견이 있는 카페는 삭제해주세요.
                                
                모르는 정보는 지어내지 말고 "정보 없음"으로 작성하세요.
                """,
                expected_output="""
                서로 다른 {n}개의 카페 정보를 반환하세요.
                다음 4가지 필드는 항상 해당 값으로 고정해주세요
                spot_category: 3
                order: 0
                day_x: 0
                spot_time: "00:00" 
                """,
                context=[],        
                agent=self.agents["Decider"],
                output_json=spots_pydantic
            )
        }     
        
    async def create_recommendation(self, input_data: dict, prompt_text: Optional[str] = None) -> dict:
        """
        사용자 맞춤 카페를 추천하는 에이전트
        """
        if input_data is None:
            raise ValueError("[CafeAgent] 에러 - input_data이 없습니다. 잘못된 요청을 보냈는지 확인해주세요")
        
        input_data["concepts"] = ', '.join(input_data.get('concepts',''))
        input_data["prompt_text"] = prompt_text
        input_data["n"] = calculate_trip_days(input_data.get('start_date',''),input_data.get('end_date',''))*2
        
        # 실행
        try:
            result = await self.crew.kickoff_async(inputs=input_data)
            print(result)
            return result.json_dict.get("spots",[])
        except Exception as e:
            print(f"Error during execution: {e}")

            # 오류가 발생한 경우 Observation을 직접 확인
            if hasattr(e, 'Observation'):
                print(f"[CafeAgent] 에러 - Tool Output (Observation): {e.Observation}")
                
                
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