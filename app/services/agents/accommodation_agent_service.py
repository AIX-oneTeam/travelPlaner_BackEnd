from crewai import Agent, Crew, Process, Task
from dotenv import load_dotenv
import os
from langchain_openai import ChatOpenAI
from app.services.agents.tools.accommodation_tool import GeoCoordinateTool, GoogleReviewTool, GoogleHotelSearchTool,GooglePlaceTool
from app.dtos.spot_models import spots_pydantic
import logging
from app.utils.time_check import time_token_check

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SERP_API_KEY = os.getenv("SERP_API_KEY")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler('logs/accommodation_agent.log', encoding="utf-8")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# 에러 전용 로그 파일 생성
file_handler_error = logging.FileHandler('logs/accommodation_agent_error.log', encoding="utf-8")
file_handler_error.setLevel(logging.ERROR)
formatter_error = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler_error.setFormatter(formatter_error)
logger.addHandler(file_handler_error)

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
        
        accommodation_concept = [
                "호텔",
                "리조트",
                "캠핑",
                "글램핑",
                "한옥",
                "풀빌라",
                "게스트 하우스",
            ]

        # 컨셉 혹은 프롬프트만 키워드로 제공
        if prompt:
            keywords = [prompt]
        elif concepts:
            # concepts에 있는 값이 accommodation_concept에 있다면 keywords에 추가
            keywords = []
            for concept in concepts:
                if concept in accommodation_concept:
                    keywords.append(concept)
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
                goal="사용자가 입력한 main_location의 위도와 경도를 조회하며, main_location값은 그대로 유지한다.",
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
                goal="cid를 이용하여 각 숙소의 리뷰를 검색하고, 각 리뷰에서 키워드를 추출한다.",
                backstory="나는 숙소 리뷰 검색 및 키워드 추출 전문가로, 각 숙소의 cid와 self.google_review_tool을 사용하여 각 숙소에 대한 리뷰를 검색하고, 리뷰에서 해당 숙소를 잘 나타낼 수 있는 키워드를 추출합니다.",
                tools=[self.google_review_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            "accommodation_user_prompt_keyword_expert": Agent(
                role="사용자 키워드 추출 전문가",
                goal="사용자가 입력한 input에서 키워드를 추출한다.",
                backstory="나는 키워드 추출 전문가로, 사용자가 입력한 input에서 키워드를 추출한다. 절대로 사용자가 입력값이 아닌 곳에서 키워드를 추출하지 않는다.",
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),            
            "accommodation_list_expert": Agent(
                role="숙소 리스트 정리 전문가",
                goal="제공된 숙소 데이터를 이용하요 사용자가 입력한 데이터로 추출한 키워드과 숙소의 키워드를 비교해, 일치하는 키워드가 많은 제공된 숙소의 데이터를 상위로 정렬한다.**이때, 반드시 accommodation_review_expert 결과 데이터를 사용한다 **",
                backstory="나는 숙소 정보 정리 전문가이며,사용자가 입력한 키워드 값과 숙소에서 추출한 키워드를 비교하여 숙소에 대한 데이터를 정렬, 제공한다. 나는 반드시 반드시 accommodation_review_expert의 데이터를 정렬 후 제공한다.",
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
        }
    def create_accommodation_tasks(self, input_data : dict):
        """테스크 생성 메서드"""
        return[
            Task( #프롬프트 키워드 추출 task
                description=f"""
                - 사용자가 입력한 {input_data['keywords']}에서 키워드를 추출합니다.
                - 키워드는 사용자가 입력한 {input_data['keywords']}에서 단어를 추출합니다.""",
                agent=self.agents["accommodation_user_prompt_keyword_expert"],
                expected_output="사용자가 입력한 {input_data['keywords']}에서 추출한 키워드",
            ),
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
                thumbnail : 반드시 'thumbnail'키의 값, 절대로 임의로 제공하지 않습니다. 
                description : description
                """,
                agent=self.agents["accommodation_pre_list_expert"],
                expected_output="""
                title : 숙소 이름,
                address : 주소,
                latitude : 위도,
                longitude : 경도,
                thumbnail : 반드시 'thumbnail'키의 값, 절대로 임의로 제공하지 않습니다. 
                description : description""",
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
                thumbnail : thumbnail은 반드시 self.google_hotel_search_tool의 검색 결과의 thumbnail, 절대로 임의로 데이터를 반환하지 않습니다. 
                description : description
                cid: cid
                """,
                agent=self.agents["accommodation_place_expert"],
                expected_output="""
                title : 숙소 이름,
                address : adrress,
                latitude :latitude,
                longitude :longitude,
                thumbnail : thumbnail은 반드시 self.google_hotel_search_tool의 검색 결과의 thumbnail, 절대로 임의로 데이터를 반환하지 않습니다. 
                description : description
                cid: cid
                """,
            ),
            Task( #리뷰 검색 task
                description=f"""
                - accommodation_place_expert의 검색 결과를 이용하여 각 숙소들에 대한 cid를 변수로 전달하고 툴은 {self.google_review_tool}을 사용하여 각 숙소에 대한 리뷰를 검색한다.
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
                title : 숙소 이름,
                address : adrress,
                latitude :latitude,
                longitude :longitude,
                thumbnail : 반드시 self.google_hotel_search_tool의 검색 결과의 thumnail, 절대로 임의로 제공하지 않습니다. 
                description : description
                cid: cid
                키워드 : 숙소 키워드 7개 """,
            ),                  
            Task( #사용자 키워드와 리뷰 키워드 비교 task
                description=f"""
                - accommodation_user_prompt_keyword_expert의 결과 키워드와 accommodation_review_expert 키워드를 비교합니다.
                - 키워드 일치율이 높은 accommodation_review_expert 데이터의 숙소를 상위로 위치시킵니다.
                - 숙소 리스트는 반드시 5개가 되도록 합니다.
                - **[[중요]]:** 숙소 정보는 반드시 **accommodation_review_expert의 결과 데이터, main_location의 숙소데이터**를 활용해야 하며, 절대로 해당 지역이 아는 숙소의 데이터를 만들지 마세요.
                title : title,
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
                spot_category : 4 로 항상 고정
                """,
                agent=self.agents["accommodation_list_expert"],
                expected_output="""
                title : title,
                address : adrress,
                latitude :latitude,
                longitude :longitude,
                cid: cid
                thumbnail : thumbnail은 반드시 self.google_hotel_search_tool의 검색 결과의 thumbnail, 절대로 임의로 데이터를 반환하지 않습니다. 
                description : description
                키워드 : 숙소 키워드 7개 
                link :  https://www.google.com/travel/search?q=title title은 각 숙소의 이름이다. 절대 'https://www.example.com/title' 사용금지 .
                spot_time : 22:00:00 으로 항상 고정 
                spot_category : 4 로 항상 고정""",
                output_json=spots_pydantic,
            ),                                               
        ]
    @time_token_check
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
            
            logger.info(f"----------result.token_usage.__dict__: {result.token_usage.__dict__}")      

            return {
                "spots": result.json_dict.get("spots", []),
                "token_usage": result.token_usage.__dict__
            }
            
        except Exception as e:
            print(f"[accommodation agent error] --- accommodation agent error {str(e)}")
            logger.error(f"[accommodation agent error] --- accommodation agent error {str(e)}")
