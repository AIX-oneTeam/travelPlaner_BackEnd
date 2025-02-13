import traceback
from fastapi import HTTPException
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import agent, task, CrewBase, crew
from app.dtos.spot_models import spots_pydantic
from dotenv import load_dotenv
import os
from typing import List, Optional, Dict
import json
from app.services.agents.tools.accommodation_tool import (
    GeoCoordinateTool,
    GoogleMapTool,
    GoogleReviewTool,
    GoogleHotelSearchTool
)


load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SERP_API_KEY = os.getenv("SERP_API_KEY")

# ------------------------- 맛집 추천 에이전트 -------------------------
class AccommodationAgentService:
    """숙소 추천을 위한 Agent 서비스"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AccommodationAgentService, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
        """서비스 초기화"""
        self.llm = LLM(model="gpt-4o", temperature=0, api_key=OPENAI_API_KEY)
        # Tools 초기화
        self.geocoordinate_tool = GeoCoordinateTool()
        self.google_map_tool = GoogleMapTool()
        self.google_review_tool = GoogleReviewTool()
        self.google_hotel_search_tool = GoogleHotelSearchTool()
        self.agents = self._create_agents()

    def _process_input(
        self, input_data: dict) -> dict:
        print(f"[입력 데이터] input_data: {input_data}")
        return input_data

    def _create_agents(self) -> Dict[str, Agent]:
        """Agent들을 생성하는 메서드"""
        return {
            "accommodation_recommendation_expert": Agent(
                role="숙소 추천 전문가",
                goal="검색 결과를 이용하여 숙소 리스트를 만들어준다.",
                backstory="""숙소 추천에 대한 풍부한 경험을 가진 전문가로, 사용자가 제공한 정보에 맞는
                                최적의 숙소를 찾아 추천하는 능력이 뛰어나며, 검색을 통해 확인된 숙소들의 정보를 리스트로 전달합니다. 
                            """,
                tools=[self.geocoordinate_tool,self.google_map_tool, self.google_review_tool, self.google_hotel_search_tool ],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
        }

    def _create_tasks(self, processed_input: dict) -> List[Task]:
        """Task들을 생성하는 메서드"""
        return [
            Task(
                description=f"""
                            - GeoCoordinateTool()을 사용하여 {processed_input['main_location']}의 위도 계산 후 GoogleMapTool()로 전달.
                            - {processed_input['main_location']} 지역의 다양한 숙소를 GoogleMapTool()을 통해 검색.
                            - GoogleMapTool() 결과에서 최소 10개 이상의 다른 title과 cid, fid, latitude, longitude, website, phoneNumber,description, address,type, website, thumbnailUrl를 추출합니다.
                            - {processed_input['main_location']}, {processed_input['start_date']}{processed_input['end_date']}을 사용하여 GoogleHotelSearchTool()으로 예약 가능한 숙소의 이름을 추출합니다. 
                            - GoogleHotelSearchTool()의 검색 결과인 이름과 GoogleMapTool() 결과 title을 비교하여 두 곳에 존재하는 속소 이름의 리스트를 만듭니다.
                            - 두 곳에 존재하는 속소 이름의 리스트의 cid, fid로 GoogleReviewTool()을 사용하여 리뷰를 검색합니다.
                            - GoogleReviewTool()로 검색한 리뷰에서 각 숙소별로 고유하고 특징적인 숙소 키워드 반드시 10개를 추출합니다. 이 키워드들은 해당 숙소의 특성을 잘 나타내야 합니다.
                            - 1번 키워드는 반드시 숙소 type을 포함합니다. 
                            - 2번 키워드는 반드시 추천 연령대(20,30,40,50,60,70,80 중 하나)를 포함합니다. 
                            - 3번 키위드는 반드시 추천 단체(친구, 여인, 가족 중 하나)를 포함합니다. 
                            - 4번 키워드는 반드시 반려견 동반 가능 여부를 확인하여 포함합니다.
                            - 5번 키워드는 반드시 해당 숙소에 있는 부대 시설을 포함합니다. 
                            - 6번 부터 10번 까지는 검색한 리뷰를 기반으로 채워넣는다.  
                            - 숙소 정렬 시 주의할점 : 
                            - 1. prompt가 있을 경우, prompt에서 키워드를 추출, 숙소 키워드와 비교하여 일치하는 키워드가 많은 숙소를 상위에 우선 정렬합니다. prompt가 없을 경우, 사용자 입력 keyword와 일치하는 키워드가 많은 숙소를 상위에 우선 정렬합니다. 
                            - 2. prompt에서 추출한 키워드 혹은 사용자 입력 keyword에 숙소 type이 있다면 반드시 일치하는 숙소 type을 가진 숙소를 상위에 위치하도록 합니다.
                            - 3. 사용자 입력 age_group과 숙소 추천 연령대가 일치하는 숙소를 상위에 위치합니다.
                            - 최종 결과는 7개의 다양한 숙소 정보를 포함해야 합니다.""",
                agent=self.agents["accommodation_recommendation_expert"],
                expected_output="7개 이상의 숙소 정보룰 담은 숙소 리스트",
                output_pydantic=spots_pydantic,
            ),
        ]

    def _process_result(self, result) -> dict:
        """결과를 처리하는 메서드"""
        print(f'결과 타입 -- {type(result)}')

        if 'raw' in result.__dict__:
            print(result.__dict__['raw'])
            return result.__dict__['raw']
    
    async def create_recommendation(
        self, input_data: dict,
    ) -> dict:
        """추천 워크플로우를 실행하는 메서드"""
        try:
            # 1. 입력 데이터 전처리
            processed_input = self._process_input(input_data)

            # 2. Task 생성
            tasks = self._create_tasks(processed_input)

            # 3. Crew 실행
            crew = Crew(tasks=tasks, agents=list(self.agents.values()), verbose=True)

            # 4. 결과 처리
            result = await crew.kickoff_async()
            return self._process_result(result)

        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))