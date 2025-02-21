from crewai import Agent, Crew, Process, Task
from dotenv import load_dotenv
import os
from langchain_openai import ChatOpenAI
from app.services.agents.tools.accommodation_tool import GeoCoordinateTool, GoogleReviewTool, GoogleHotelSearchTool,GooglePlaceTool
from app.dtos.spot_models import spots_pydantic
import logging
from app.utils.time_check import time_check

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SERP_API_KEY = os.getenv("SERP_API_KEY")

logger = logging.getLogger(__name__)

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
        self.google_hotel_search_tool = GoogleHotelSearchTool()
        self.google_place_tool = GooglePlaceTool()
        self.google_review_tool = GoogleReviewTool()
        self.agents = self.create_accommodation_agnets()
        
    def prepare_crew_inputs(self, user_input: dict):
        """크루에 전달될 데이터 전처리"""
        companion_group = user_input.get('companion_count', [])

        # 동반자 정보를 label을 기준으로 합산하기 위한 dictionary 생성
        age_groups = {
            "성인": 0,
            "청소년": 0,
            "어린이": 0,
            "영유아": 0,
            "반려견": 0,
        }

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
        prompt = user_input.get('prompt', '') 
        
        #컨셉 혹은 프롬프트만 키워드로 제공
        if prompt:
            keywords = [prompt]
        elif concepts:
            keywords = concepts
        else:
            keywords = []

        keywords = list(filter(None, keywords))
        
        # age 추출 및 키워드에 추가
        age = user_input.get('ages')
        if age:
            keywords.append(age)
        
        # 반려견 동반 여부 키워드 추가
        if pets > 0:
            keywords.append("반려견 동반")
            
                     
        prepared_user_data = {
            'main_location' : user_input.get('main_location'),
            'ages': user_input.get('ages'),
            'start_date': user_input.get('start_date'),
            'end_date': user_input.get('end_date'),
            'adults': adults,
            'children': children,
            'pets': pets,
            'keywords': ', '.join(keywords),
            'keyword_list' : keywords
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
            "accommodation_pre_list_expert": Agent(
                role="숙소 정보 조회 전문가",
                goal="사용자 입력 데이터를 사용하여 각 숙소에 대한 정보를 추출한다. 반드시 정보를 검색 결과를 전달한다.",
                backstory="나는 숙소 정보 검색 전문가로, self.google_hotel_search_tool을 사용하여 각 숙소의 title, address, latitude, longtitude, thumbnail, description를 반환한다.",
                tools=[self.google_hotel_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True, 
            ),          
            "accommodation_place_expert": Agent(
                role="숙소 cid 정보 조회 전문가",
                goal="숙소 title를 이용하여 각 숙소의 cid를 조회한다.",
                backstory="나는 숙소 검색 전문가로, self.google_place_tool를 사용하여 각 숙소에 대한 cid를 조회한다.",
                tools=[self.google_place_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),  
            "accommodation_review_expert": Agent(
                role="숙소 리뷰 검색 및 키워드 추출 전문가",
                goal="예약 가능한 숙소의 리뷰를 검색하고, 각 리뷰에서 키워드를 추출한다.",
                backstory="나는 숙소 리뷰 검색 및 키워드 추출 전문가로, self.google_review_tool을 사용하여 예약 가능한 각 호텔에 대한 리뷰를 검색하고, 리뷰에서 숙소를 잘 나타낼 수 있는 키워드를 추출합니다.",
                tools=[self.google_review_tool],
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
            "accommodation_list_expert": Agent(
                role="숙소 리스트 정리 전문가",
                goal="사용자가 입력한 키워드 값과 숙소에서 추출한 키워드를 비교하여 더 많은 키워드가 일치하는 숙소의 정보가 상위에 위치하는 추천 리스트를 만든다. **이때, 반드시 이전 Task에서 제공된 예약 가능한 숙소 리스트의 정보를 활용해야 한다.**",
                backstory="나는 숙소 정보 정리 전문가이며,사용자가 입력한 키워드 값과 숙소에서 추출한 키워드를 비교하여 숙소에 대한 정보를 검색 결과를 사용하여 제공한다. 나는 절대로 제공된 데이터 외의 데이터를 생성하여 제공하지 않는다. ",
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
        }
    def create_accommodation_tasks(self, input_data : dict):
        """테스크 생성 메서드"""
        return[
            Task( #좌표 task
                description=f"{input_data['main_location']}의 위도, 경도를 추출한다.",
                agent=self.agents["geocoding_expert"],
                expected_output="위도 경도",
            ),
            Task(  #  hotel serper task
                description=f"""
                - {input_data['keyword_list']}, {input_data['main_location']}, {input_data['start_date']}, {input_data['end_date']},{input_data['adults']},{input_data['children']} 을 사용하여 예약 가능한 숙소 리스트를 추출한다.
                - **[중요]** 결과는 반드시 중복되지 않는 7개의 숙소의 정보를 가져야한다. 
                -**중요:** 이 Task의 결과를 바탕으로 다음 Task들이 진행되므로, 예약 가능한 숙소 목록을 정확하게 추출하는 것이 중요합니다.
                - 예시:
                title : 숙소 이름,
                address : 주소,
                latitude : 위도,
                longitude : 경도,
                thumbnail : thumbnail 반드시 검색 결과에서 추출한 url, 절대로 임의로 제공하지 않습니다. 
                description : description
                """,
                agent=self.agents["accommodation_pre_list_expert"],
                expected_output="""
                title, address, latitude, longtitude, thumbnail, description를 포함한 숙소 리스트. 반드시 검색 결과에서 데이터를 가져온다.""",
            ),
            Task(  #cid 검색 task
                description=f"""
                -{input_data['main_location']}, 숙소 title 사용하여 각 숙소의 cid 를 추출한다.
                -결과는 반드시 7개의 각 숙소에 대한 cid을 포함해야한다.
                -**중요:** 이 Task의 결과를 바탕으로 다음 Task들이 진행되므로, 예약 가능한 숙소 목록을 정확하게 추출하는 것이 중요합니다.
                title : 숙소 이름,
                address : adrress,
                latitude :latitude,
                longitude :longitude,
                thumbnail : 반드시 self.google_hotel_search_tool의 검색 결과의 thumbnail, 절대로 임의로 제공하지 않습니다. 
                description : description
                cid: cid
                """,
                agent=self.agents["accommodation_place_expert"],
                expected_output="""
                - 10개의 중복되지 않는 title, address, latitude, longitude,thumbnail,description, cid가 모두 있는 숙소 정보 리스트
                """,
            ),
            Task( #리뷰 검색 task
                description=f"""
                - {self.google_place_tool}의 검색 결과인 예약 가능한 각 숙소들에 대한 cid를 변수로 전달하고 툴은 {self.google_review_tool}을 사용하여 각 숙소에 대한 리뷰를 검색한다.
                - **[중요]** 반드시 예약 가능한 숙소 리스트에 있는 7개의 숙소의 리뷰만 검색해야 합니다.
                -리뷰에서는 각 숙소의 특징을 잘 나타낼 수 있는 키워드를 추출하여 숙소 리뷰 기반 추출 키워드를 만듭니다.
                -반드시 숙소 리뷰 기반 추출 키워드는 각 개별 숙소에 대해서 10개씩 입니다. 숙소 리뷰 기반 추출 키워드는 각 숙소에 대한 키워드입니다.
                -1번 키워드는 반드시 해당 숙소의 타입을 나타내는 키워드를 추출합니다. 예) 호텔, 리조트, 빌라, 게스트하우스, 에어비엔비
                -2번 키워드는 반드시 해당 숙소의 추천 연령대를 포함합니다 예)10대, 20대, 30대, 40대, 50대, 60대,70대,80대
                -3번 키워드는 반드시 추천 단체를 포함합니다 예)가족, 친구, 연인, 혼자, 출장
                -4번 키워드는 반드시 해당 숙소의 친절도를 나타냅니다 예)친절 상, 친절 중, 친절 하
                -5번 키워드는 반드시 해당 숙소의 접근성에 대해 나타냅니다. 예) 접근성 상, 접근성 중, 접근성 하
                -6번 키워드는 반드시 해당 숙소의 청결성에 대해 나타냅니다. 예)매우 청결, 약간 청결, 보통, 약간 불청결, 매우 불청결
                -7번 키워드는 반드시 리뷰에서 숙소에서 가깝다고 언급한 장소에 대해 나타냅니다.
                -**중요:** 반드시 예약 가능한 숙소 리스트에 있는 숙소만 리뷰를 검색해야 합니다.
                title : 숙소 이름,
                address : adrress,
                latitude :latitude,
                longitude :longitude,
                thumbnail : 반드시 self.google_hotel_search_tool의 검색 결과의 thumnail, 절대로 임의로 제공하지 않습니다. 
                description : description
                cid: cid
                키워드 : 숙소 키워드 7개 
                """,
                agent=self.agents["accommodation_review_expert"],
                expected_output="""
                - 7개의 중복되지 않는 숙소에 대한 정보,title, address, latitude, longitude, imageurl,thumbnail,description, cid, 키워드가 모두 포함되어 있어야함 
                """,
            ),                  
            Task( #프롬프트 키워드 추출 task
                description=f"""
                - 사용자가 입력한 {input_data['keywords']}에서 키워드를 추출합니다.
                - 단 수영장이 있는 호텔, 역이 가까운 숙소 이런 형식의 경우, 분리하지 않고 수영장이 있는 호텔을 하나의 키워드, 역이 가까운 숙소를 하나의 키워드로 구분합니다.""",
                agent=self.agents["accommodation_user_prompt_keyword_expert"],
                expected_output="키워드",
            ),
            Task( #사용자 키워드와 리뷰 키워드 비교 task
                description=f"""
                - 사용자가 입력에서 추출한 키워드와 숙소 리뷰 기반 추출 키워드를 비교하여 더 많은 키워드가 일치하는 숙소의 정보를 나열합니다.
                - 숙소의 정보는 self.google_map_tool과  google_hotel_search_tool의 검색 결과를 사용합니다. 절대 데이터를 생성하지 않습니다.
                - 사용자 입력에서 추출한 키워드와 일치하지 않는 숙소 정보는 생략하지 말고, 키워드가 일치하는 숙소를 우선으로 위치하게 한 뒤 나열합니다.
                - 숙소 리스트는 반드시 5개가 되도록 합니다.
                - **[[중요]]:** 숙소 정보는 반드시 **이전  self.google_map_tool과 google_hotel_search_tool에서 제공된 데이터**를 활용해야 하며, 새로운 정보를 생성하거나 가상의 데이터를 만들지 마세요.
                title : 숙소 이름,
                address : adrress,
                latitude :latitude,
                longitude :longitude,
                cid: cid
                thumbnail : thumbnail은 반드시 self.google_hotel_search_tool의 검색 결과의 thumbnail, 절대로 임의로 데이터를 반환하지 않습니다. 
                description : description
                키워드 : 숙소 키워드 7개 
                link :  https://www.google.com/travel/search?q=title title은 각 숙소의 이름이다. 절대 'https://www.example.com/title' 사용금지 .
                spot_category: 0 으로 항상 고정
                spot_time : 22:00:00 으로 항상 고정 
                """,
                agent=self.agents["accommodation_list_expert"],
                expected_output="""
                - title, address, latitude, longtitude, cid, thunbnail, 키워드, description, link,spot_category,spot_time, phone_number를 포함한 숙소 리스트
                """,
                output_json=spots_pydantic,
            ),                                               
        ]
    @time_check
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
            print(f"[accommodation agent error] --- accommodation agent error {str(e)}")
            logger.error(f"[accommodation agent error] --- accommodation agent error {str(e)}")
