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
from app.services.agents.tools.accommodation_tool import GeoCoordinateTool, GoogleMapTool, GoogleReviewTool, GoogleHotelSearchTool,GoogleIamgeSearchTool
from app.dtos.spot_models import spots_pydantic
import logging

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SERP_API_KEY = os.getenv("SERP_API_KEY")

logger = logging.getLogger("accommodation_agent_service")
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler('logs/accommodation_agent_service.log')
file_handler.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)
class AccommodationAgentService:
    _instance = None
    
    
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
        self.google_review_tool = GoogleReviewTool()
        self.google_image_tool =GoogleIamgeSearchTool()
        self.agents = self.create_accommodation_agnets()
        
    def prepare_crew_inputs(self, user_input: dict):
        """크루에 전달될 데이터 전처리"""
        prompt = user_input.get('prompt', '') 
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

        # keyword 추출
        concepts = user_input.get('concepts', [])
        user_prompt = prompt
        keywords = concepts + ([prompt] if user_prompt else [])
        keywords = list(filter(None, keywords))  # Ensure keywords is a list
        
        # age 추출 및 키워드에 추가
        age = user_input.get('ages')
        if age:
            keywords.append(age)
        
        # 반려견 동반 여부 키워드 추가
        if pets > 0:
            keywords.append("반려견 동반")
        else:
            keywords.append("반려견 미동반")

        prepared_user_data = {
            'main_location' : user_input.get('main_location'),
            'ages': user_input.get('ages'),
            'start_date': user_input.get('start_date'),
            'end_date': user_input.get('end_date'),
            'adults': adults,
            'children': children,
            'pets': pets,
            # Join the keywords into a string here
            'keywords': ', '.join(keywords)
        }
        
        return prepared_user_data

    def create_accommodation_agnets(self):
        """에이전트 생성 메서드"""
        return{
            "geocoding_expert": Agent(
                role="좌표 조회 전문가",
                goal="사용자가 입력한 location(예: '부산광역시')의 위도와 경도를 조회하며, location 값은 그대로 유지한다.",
                backstory="나는 위치 데이터 전문가로, 입력된 location 값을 변경하지 않고 self.geo_cording_tool을 통해 좌표를 조회한다.",
                tools=[self.geo_cording_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            "accommodation_search_expert": Agent(
                role="숙소 기본 정보 조회 전문가",
                goal="좌표 정보를 활용하여 숙소의 기본 정보를 조회한다.",
                backstory="나는 숙소 검색 전문가로, Google Maps API를 사용하여 특정 위치의 숙소 정보를 조회한다.",
                tools=[self.google_map_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            "accommodation_book_expert": Agent(
                role="숙소 예약 조회 전문가",
                goal="숙소의 기본 정보를 사용하여 예약 가능한 숙소를 조회한다.",
                backstory="나는 숙소 검색 전문가로, Google Maps API를 사용하여 예약 가능한 숙소를 조회한다.",
                tools=[self.google_hotel_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            "accommodation_compare_expert": Agent(
                role="검색 결과 비교 전문가",
                goal="self.google_map_tool의 검색 결과의 title과 self.google_hotel_search_tool의 검색 결과 title을 비교하여 공통으로 존재하는 숙소들의 기본 정보를 담은 리스트를 만든다.",
                backstory="나는 검색 결과 비교 전문가로, self.google_map_tool의 검색 결과와 self.google_hotel_search_tool의 검색 결과를 비교한다.",
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),            
            "accommodation_review_expert": Agent(
                role="숙소 리뷰 조회 전문가 ",
                goal="예약 가능한 숙소의 리뷰를 검색한다.",
                backstory="나는 숙소 리뷰 검색 전문가로, self.google_review_tool를 사용하여 예약 가능한 각 호텔에 대한 리뷰를 검색한다.",
                tools=[self.google_review_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            "accommodation_review_keyword_expert":Agent(
                role="숙소 리뷰 키워드 추출 전문가 ",
                goal="예약 가능한 숙소의 리뷰를 분석하고 각 리뷰에서 키워드를 추출한다.",
                backstory="나는 숙소 리뷰 키워드 추출 전문가로, self.google_review_tool의 결과인 리뷰에서 숙소를 잘 나타낼 수 있는 키워드를 추출합니다.",
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            "accommodation_user_prompt_keyword_expert": Agent(
                role="사용자 키워드 추출 전문가",
                goal="사용자가 입력한 input에서 키워드를 추출한다.",
                backstory="나는 키워드 추출 전문가로, llm을 사용하여 사용자가 입력한 input에서 키워드를 추출합니다.",
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),            
            "accommodation_keyword_compare_expert": Agent(
                role="사용자 입력 키워드와 추출 키워드 비교 전문가",
                goal="사용자가 입력한 키워드 값과 숙소에서 추출한 키워드를 비교하여 더 많은 키워드가 일치하는 숙소의 정보가 상위에 위치하는 추천 리스트를 만든다",
                backstory="나는 키워드 비교 전문가로, llm을 사용하여 사용자가 입력한 키워드 값과 숙소에서 추출한 키워드를 비교한다여 더 많은 키워드가 일치하는 숙소의 self.google_hotel_search_tool결과를 이용하여 추천 숙소 리스트를 만든다",
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            # "accommodation_url_expert": Agent(
            #     role="숙소 url 검색 전문가",
            #     goal="숙소 리스트에 있는 이름과 지역, self.google_url_tool이용해 숙소의 url을 추출합니다. ",
            #     backstory="나는 url 검색 전문가로, 숙소 리스트에 있는 title과 main_location을 이용해 해당 숙소의 url을 검색한다. ",
            #     tools=[self.google_image_tool],
            #     llm=self.llm,
            #     verbose=True,
            #     async_execution=True,
            #),   
        }
    def create_accommodation_tasks(self, input_data : dict):
        """테스크 생성 메서드"""
        return[
            Task( #좌표 task
                description=f"{input_data['main_location']}의 위도, 경도를 추출한다.",
                agent=self.agents["geocoding_expert"],
                expected_output="위도 경도",
            ),
           Task(  # 예약 검색 task - FIRST
                description=f"""
                -{input_data['main_location']},{input_data['start_date']},{input_data['end_date']}를 사용하여 예약 가능한 숙소 리스트를 추출한다.
                -결과는 최소 10개 이상의 다른 숙소 title을 포함해야한다.
                -**중요:** 이 Task의 결과를 바탕으로 다음 Task들이 진행되므로, 예약 가능한 숙소 목록을 정확하게 추출하는 것이 중요합니다.
                - 결과는 title과 ,latitude, longitude, phoneNumber,description, address,type, website, thumbnailUrl을 포함해야합니다.
                """,
                agent=self.agents["accommodation_book_expert"],
                expected_output="10개 이상의 중복되지 않는 예약 가능한 숙소 정보 리스트",
            ),
            Task( #기본 검색 task
                description=f"""
                - {self.google_hotel_search_tool}의 검색 결과인, 예약 가능한 숙소 리스트에 있는 title, {input_data['main_location']}을 검색어로 이용하고 툴은 {self.google_map_tool}을 사용해 숙소의 cid,fid를 추출한다.
                - **[중요]** 반드시 예약 가능한 숙소 리스트에 있는 숙소만 검색해야 합니다.
                """,
                agent=self.agents["accommodation_search_expert"],
                expected_output="예약 가능한 숙소들에 대한 title, cid,fid, address, thumbnailUrl, website를 포함한 리스트 ",
            ),
            Task( #리뷰 검색 task
                description=f"""
                - {self.google_map_tool}의 검색 결과인 예약 가능한 숙소들에 대한 cid,fid을 검색어로 사용하고 툴은 {self.google_review_tool}을 사용하여 각 숙소에 대한 리뷰를 검색한다.
                - **[중요]** 반드시 예약 가능한 숙소 리스트에 있는 숙소의 리뷰만 검색해야 합니다.
                """,
                agent=self.agents["accommodation_review_expert"],
                expected_output="예약 가능한 숙소들에 대한 리뷰",
            ),                  
            Task( #리뷰 키워드 task
                description=f"""
                -{self.google_review_tool}의 검색 결과인 각 숙소에 대한 리뷰의 키워드를 추출한다.
                -리뷰에서는 각 숙소의 특징을 잘 나타낼 수 있는 키워드를 10개 추출하여 숙소 리뷰 기반 추출 키워드를 만듭니다.
                -반드시 숙소 리뷰 기반 추출 키워드는 각 개별 숙소에 대해서 10개씩 입니다. 숙소 리뷰 기반 추출 키워드는 각 숙소에 대한 키워드입니다.
                -1번 키워드는 반드시 해당 숙소의 타입을 나타내는 키워드를 추출합니다. 예) 호텔, 리조트, 빌라, 게스트하우스, 에어비엔비
                -2번 키워드는 반드시 해당 숙소의 추천 연령대를 포함합니다 예)10대, 20대, 30대, 40대, 50대, 60대,70대,80대
                -3번 키워드는 반드시 추천 단체를 포함합니다 예)가족, 친구, 연인, 혼자
                -4번 키워드는 반드시 반려견 동반 가능 여부를 포함합니다 예)반려견 동반, 반려견 미동반
                -5번 키워드는 반드시 해당 숙소에 있는 부대 시설을 포함합니다. 예) 헬스장, 수영장, 바, 어린이 놀이 시설, 만약 이 중 제공하는 시설이 없다면 공용 와이파이로 나타냅니다.
                -6번 키워드는 반드시 해당 숙소의 친절도를 나타냅니다 예)매우 친절, 적당히 친절, 보통, 불친절, 매우 불친절
                -7번 키워드는 반드시 해당 숙소의 접근성에 대해 나타냅니다. 예) 접근성 매우 좋음, 접근성 약간 좋음, 접근성 보통, 접근성 약간 불편, 접근성 매우 불편
                -8번 키워드는 반드시 해당 숙소의 청결성에 대해 나타냅니다. 예)매우 청결, 약간 청결, 보통, 약간 불청결, 매우 불청결
                -9번 키워드는 반드시 해당 숙소의 뷰에 대해서 나타냅니다. 예)오션뷰, 산뷰, 빌딩뷰, 주차장뷰, 뷰없음 
                -10번 키워드는 반드시 가까운 장소에 대해서 언급합니다. 리뷰에서 가깝다고 언급한 장소를 키워드로 합니다.
                -**중요:** 반드시 예약 가능한 숙소 리스트에 있는 숙소만 리뷰를 검색해야 합니다.
                """,
                agent=self.agents["accommodation_review_keyword_expert"],
                expected_output="숙소 리뷰 기반 추출 키워드 10개",
            ), 
            Task( #프롬프트 키워드 추출 task
                description=f"""
                - 사용자가 입력한 {input_data['keywords']}에서 키워드를 추출합니다.""",
                agent=self.agents["accommodation_user_prompt_keyword_expert"],
                expected_output="키워드",
            ),             
            Task( #사용자 키워드와 리뷰 키워드 비교 task
                description=f"""
                - 사용자가 입력에서 추출한 키워드와 숙소 리뷰 기반 추출 키워드를 비교하여 더 많은 키워드가 일치하는 숙소의 google_hotel_search_tool의 검색 결과 정보를 상위로 위치하게 나열하여 숙소 추천 리스트를 제공합니다.
                - 사용자 입력에서 추출한 키워드와 일치하지 않는 숙소 정보는 생략하지 말고 키워드가 일치하는 숙소의 google_hotel_search_tool의 검색 결과를 우선으로 위치하게 한 뒤 나열합니다.
                - 숙소 리스트는 최소 6개 최대 8개가 되도록 합니다.
                - **[중요]:** 반드시 예약 가능한 숙소 리스트에 있는 숙소만 비교해야 합니다.
                - 반드시 숙소의 정보는 google_hotel_search_tool의 검색 결과의 정보를 사용합니다.
                - 반드시 thumbnailUrl을 google_hotel_search_tool의 검색 결과의 정보를 사용합니다.
                """,
                agent=self.agents["accommodation_keyword_compare_expert"],
                expected_output="""
                - 일치하는 키워드가 많은 숙소가 상위에 위치한 최소 6개의 숙소 리스트
                - 키워드 : 사용자 입력에서 추출한 키워드와 일치하는 숙소 리뷰 기반 추출 키워드 
                - spot_category: 0 으로 항상 고정
                - spot_time : 15:00 혹은 20:00으로 랜덤 제공
                - 반드시 google_hotel_search_tool의 검색 결과를 사용한 website, phoneNumber,description, address,type, website, thumbnailUrl을 포함한 숙소 정보 리스트
                - **[중요]:** 반드시 google_hotel_search_tool 혹은 self.google_map_tool 의 검색 결과에 있는 website, address, thumbnailUrl을 포함한 정보 리스트입니다. 새롭게 생성해서 추가하지 마세요. 
                - 반드시 google_hotel_search_tool 혹은 self.google_map_tool 의 검색 결과에 있는 website, address, thumbnailUrl을 포함한 정보 리스트. 
                """,
                output_json=spots_pydantic,
            ),  
            # Task( #숙소 정보 추가 검색 task
            #     description=f"""
            #     - 숙소 리스트에 있는 숙소의 이름과 main_location을 이용하여 각 숙소에 대한 이미지와 link를 추출합니다.
            #     - 검색 결과의 images중 "source": "Booking.com"인 thumbnailUrl을 저장합니다.
            #     - 검색 결과의 images중 "source": "Booking.com"인 link를 저장합니다.
            #     """,
            #     agent=self.agents["accommodation_url_expert"],
            #     expected_output="""
            #     -위의 thumbnailUrl과 최소 6개의 숙소 리스트
            #     -url : https://www.booking.com/hotel/kr으로 시작하는 link
            #     -address :  attributes의 주소
            #     """,
            #     output_json=spots_pydantic,
            # ),                                 
        ]

    async def create_recommendation_accommodation(self, user_input: dict):
        """
        CrewAI를 실행하여 사용자 맞춤 숙소를 추천하는 서비스
        """
        
        try:
            # 1. 입력 데이터 전처리
            processed_input= self.prepare_crew_inputs(user_input)

            # 2. Task 생성
            tasks = self.create_accommodation_tasks(processed_input)
            # 3. Crew 실행
            crew = Crew(tasks=tasks, agents=list(self.agents.values()), verbose=True, memory=True)

            # 4. 결과 처리
            result = await crew.kickoff_async()
            return result.json_dict.get("spots", [])

        except Exception as e:
            print(f"[accommodation agent error] --- accommodation agent error {e}")
            logger.error(f"[accommodation agent error] --- accommodation agent error {e}")
