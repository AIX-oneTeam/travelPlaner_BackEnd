from crewai import Agent, Crew, Process, Task
from crewai.project import agent, task, CrewBase, crew
from pydantic import BaseModel
from dotenv import load_dotenv
import os
from langchain_openai import ChatOpenAI
from crewai.tools import BaseTool
from urllib.parse import quote
from serpapi import GoogleSearch
from geopy.geocoders import Nominatim
from typing import List, Optional
import json
import http.client
from app.services.agents.accommodation_tools import GeoCoordinateTool, GoogleMapTool, GoogleReviewTool, GoogleHotelSearchTool
from app.dtos.spot_models import spots_pydantic

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SERP_API_KEY = os.getenv("SERP_API_KEY")

class AccommodationAgentService:
    _instance = None

    @classmethod
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AccommodationAgentService, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
        """CrewAI 관련 객체들을 한 번만 생성"""
        print("CrewAISingleton 초기화 중...")

        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=OPENAI_API_KEY,
            temperature=0,
            max_tokens=4000
        )
        self.geo_cording_tool = GeoCoordinateTool()
        self.google_map_tool = GoogleMapTool()
        self.google_hotel_search_tool = GoogleHotelSearchTool()
        self.gooloe_review_tool = GoogleReviewTool()

        # 에이전트 정의(재사용)
        self.accommodation_recommendation_expert = Agent(
            role="{main_location} 지역 숙소 검색",
            goal="검색 결과를 이용하여 숙소 리스트를 만들어준다.",
            backstory="""
            숙소 추천에 대한 풍부한 경험을 가진 전문가로, 사용자가 제공한 정보에 맞는
            최적의 숙소를 찾아 추천하는 능력이 뛰어나며, 검색을 통해 확인된 숙소들의 정보를 리스트로 전달합니다.
            """,
            tools=[self.geo_cording_tool, self.google_map_tool, self.google_hotel_search_tool, self.gooloe_review_tool],
            allow_delegation=False,
            max_iter=2,
            llm=self.llm,
            verbose=True,
            stop_on_failure=True
        )

        self.accommodation_recommendation_task = Task(
            description="""
                - GeoCoordinateTool()을 사용하여 {main_location}의 위도 계산 후 GoogleMapTool()로 전달.
                - {main_location} 지역의 다양한 숙소를 GoogleMapTool()을 통해 검색.
                - GoogleMapTool() 결과에서 최소 10개 이상의 다른 title과 cid, fid, latitude, longitude, website, phoneNumber,description, address,type, website, thumbnailUrl를 추출합니다.
                - {main_location}, {start_date}와 {end_date}을 사용하여 GoogleHotelSearchTool()으로 예약 가능한 숙소의 이름을 추출합니다.
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
                - 1. {user_prompt}가 있을 경우, {user_prompt}에서 concepts를 추출, 숙소 키워드와 비교하여 일치하는 concepts 가 많은 숙소를 상위에 우선 정렬합니다. prompt가 없을 경우, 사용자 입력 {concepts}와 일치하는 키워드가 많은 숙소를 상위에 우선 정렬합니다.
                - 2. {user_prompt}에서 추출한 concepts 혹은 사용자 입력 {concepts}에 숙소 type이 있다면 반드시 일치하는 숙소 type을 가진 숙소를 상위에 위치하도록 합니다.
                - 3. 사용자 입력 {ages}과 숙소 추천 연령대가 일치하는 숙소를 상위에 위치합니다.
                - 최종 결과는 7개의 다양한 숙소 정보를 포함해야 합니다.
            """,
            expected_output="""
                다양한 유형의 숙소 정보가 포함된 텍스트 (7개의 숙소),
                spot_category: 0 으로 항상 고정
            """,
            output_json=spots_pydantic,
            agent=self.accommodation_recommendation_expert
        )

        self.crew = None

    async def accommodation_agent(self, user_input: dict):
        """
        CrewAI를 실행하여 사용자 맞춤 숙소를 추천하는 서비스
        """
        if user_input is None:
            raise ValueError("user_input이 없습니다. 잘못된 요청을 보냈는지 확인해주세요")

        ages = user_input.get('ages')
        start_date = user_input.get('start_date')
        end_date = user_input.get('end_date')
        companion_group = user_input.get('companion_count', [])

        # 동반자 정보를 label을 기준으로 합산하기 위한 dictionary 생성
        age_groups = {
            "성인": 0,
            "청소년": 0,
            "어린이": 0,
            "영유아": 0,
            "반려견": 0,
        }

        # companion_group 리스트를 순회하며 각 label에 해당하는 count 값을 합산
        for companion in companion_group:
            label = companion.get("label")
            count = companion.get("count", 0)
            if label in age_groups:
                age_groups[label] += count

        # 성인과 청소년을 합쳐서 adults로, 어린이와 영유아를 합쳐서 children으로 계산
        adults = age_groups["성인"] + age_groups["청소년"]
        children = age_groups["어린이"] + age_groups["영유아"]
        pets = age_groups["반려견"]

        user_input["concepts"] = ', '.join(user_input.get('concepts', ''))
        user_input["user_prompt"] = user_input.get("prompt")  # 오타 수정

        # 멀티 에이전트 시스템 설정
        crew = Crew(
            agents=[self.accommodation_recommendation_expert],
            tasks=[self.accommodation_recommendation_task],
            process=Process.sequential,
            verbose=True,
        )

        # 실행
        try:
            result = await crew.kickoff_async(inputs=user_input)
            print(result)
            return result.json_dict.get("spots", [])
        except Exception as e:
            print(f"Error during execution: {e}")

            # 오류가 발생한 경우 Observation을 직접 확인
            if hasattr(e, 'Observation'):
                print(f"Tool Output (Observation): {e.Observation}")
