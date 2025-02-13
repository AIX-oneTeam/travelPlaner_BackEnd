import traceback
import json
from datetime import datetime
from crewai import Agent, Task, Crew, LLM
from typing import List, Dict, Optional
from fastapi import HTTPException
from app.dtos.spot_models import spots_pydantic
from dotenv import load_dotenv
import os
from app.services.agents.tools.restaurant_tool import (
    GeocodingTool,
    RestaurantBasicSearchTool,
    NaverWebSearchTool,
    NaverImageSearchTool,
    KakaoLocalSearchTool,
)

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# ------------------------- 맛집 추천 에이전트 -------------------------
class RestaurantAgentService:
    """식당 추천을 위한 Agent 서비스"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RestaurantAgentService, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
        """서비스 초기화"""
        # print("RestaurantAgentService 초기화 중...")
        self.llm = LLM(model="gpt-4o", temperature=0, api_key=OPENAI_API_KEY)
        # Tools 초기화
        self.geocoding_tool = GeocodingTool()
        self.restaurant_search_tool = RestaurantBasicSearchTool()
        self.web_search_tool = NaverWebSearchTool()
        self.image_search_tool = NaverImageSearchTool()
        self.kakao_local_search_tool = KakaoLocalSearchTool()
        self.agents = self._create_agents()

    def _process_input(
        self, input_data: dict, prompt: Optional[str] = None
    ) -> tuple[dict, str]:
        """입력 데이터 전처리"""
        print(f"[입력 데이터] input_data: {input_data}")
        print(f"[프롬프트 입력] prompt: {prompt}")

        if prompt:
            # prompt가 있으면 concepts 무시
            input_data["concepts"] = []
            prompt_text = f"다음 조건에 맞춰서 추천해주세요: {prompt}"
        else:
            # prompt가 없을 때만 concepts 처리
            valid_concepts = [
                "맛집",
                "해산물 좋아",
                "고기 좋아",
                "가족 여행",
                "기념일",
                "낮술",
            ]
            filtered_concepts = [
                concept
                for concept in input_data.get("concepts", [])
                if concept in valid_concepts
            ]
            if not filtered_concepts:
                filtered_concepts = ["맛집"]
            print(f"[컨셉 필터링] filtered_concepts: {filtered_concepts}")
            input_data["concepts"] = filtered_concepts
            prompt_text = f"맛집을 다음 컨셉에 맞춰서 추천해주세요: {', '.join(filtered_concepts)}"

        return input_data, prompt_text

    def _create_agents(self) -> Dict[str, Agent]:
        """Agent들을 생성하는 메서드"""
        return {
            "geocoding": Agent(
                role="좌표 조회 전문가",
                goal="사용자가 입력한 location(예: '부산광역시')의 위도와 경도를 조회하며, location 값은 그대로 유지한다.",
                backstory="나는 위치 데이터 전문가로, 입력된 location 값을 변경하지 않고 Google Geocoding API를 통해 좌표를 조회한다.",
                tools=[self.geocoding_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            "restaurant_search": Agent(
                role="맛집 기본 조회 전문가",
                goal="좌표 정보를 활용하여 식당의 기본 정보를 조회한다.",
                backstory="나는 맛집 데이터 분석 전문가로, Google Maps API를 사용하여 특정 위치의 식당 정보를 조회한다.",
                tools=[self.restaurant_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            "final_recommendation": Agent(
                role="최종 추천 에이전트",
                goal="네이버 웹 검색으로 수집한 세부 정보를 바탕으로, 여행 계획에 맞는 최종 맛집 추천 리스트를 생성한다.",
                backstory="나는 데이터 분석 전문가로, 네이버 웹 검색으로 수집한 맛집 정보를 여행 일정과 컨셉에 맞게 분석하여 최적의 추천 리스트를 구성한다.",
                tools=[self.web_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
                memory=True,
            ),
            "image_search": Agent(
                role="네이버 이미지 검색 에이전트",
                goal="네이버 이미지 검색 API를 사용해 식당의 이미지 URL을 조회한다.",
                backstory="나는 네이버 이미지 검색 전문가로, 식당의 정확한 이미지를 제공합니다.",
                tools=[self.image_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
                memory=True,
            ),
            "kakao_local_search": Agent(
                role="카카오 로컬 검색 에이전트",
                goal="카카오 로컬 API를 사용해 식당의 상세 정보(주소, 위도/경도, 지도 URL, 전화번호, 영업시간, 영업상태)를 정확하게 조회한다.",
                backstory="나는 카카오 로컬 검색 전문가로, 식당의 위치 정보뿐만 아니라 전화번호, 영업시간, 현재 영업 상태 등 실용적인 정보를 종합적으로 제공하는 것을 전문으로 합니다.",
                tools=[self.kakao_local_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
                memory=True,
            ),
        }

    def _create_tasks(self, input_data: dict, prompt_text: str) -> List[Task]:
        """Task들을 생성하는 메서드"""
        return [
            Task(
                description=f"{input_data['main_location']}의 좌표 조회",
                agent=self.agents["geocoding"],
                expected_output="위치 좌표",
            ),
            Task(
                description="맛집 기본 정보 조회",
                agent=self.agents["restaurant_search"],
                expected_output="맛집 기본 정보 리스트",
            ),
            Task(
                description=f"""{input_data['main_location']} 지역의 맛집 데이터를 최신 검색 결과를 활용하여 수집하고,
                {input_data['start_date']}부터 {input_data['end_date']}까지 여행하는 {input_data['ages']} 연령대의 고객과 
                동반자({', '.join([f"{c['label']} {c['count']}명" for c in input_data['companion_count']])})를 위한
                {prompt_text}

                반드시 아래 JSON 스키마에 맞추어 정확하고 누락 없이 정보를 반환할 것.
                
                JSON 스키마:
                {{
                    "kor_name": "string (가게 한글이름, 최대 255자)",
                    "eng_name": "string 또는 null (가게 영어이름, 최대 255자)",
                    "description": "string (가게 설명, 최소 150자 이상 255자 이하)",
                    "business_status": "boolean (영업 상태, true: 영업 중, false: 영업 종료)",
                    "business_hours": "string 또는 null (영업 시간 정보)"
                    "url": "string 또는 null (가게 URL, 공식 정보 우선)",
                }}

                ### 상세 정보 수집 지시사항:
                - **eng_name**: kor_name을 영어로 번역하여 입력할 것.
                    - 예시: "미포집" -> "Mipojip"
                    - 식당 이름의 의미를 살려서 적절히 번역할 것.
                - **description**: 수집한 데이터를 바탕으로, **가게의 주요 메뉴, 분위기, 위치적 특징**을 포함하여 **최소 150자 이상 255자 이하**로 작성할 것.
                    - 설명 시작 시 식당 이름을 문장 앞에 붙이지 말 것 (예: "OO식당은" 과 같은 형식 사용하지 말 것)
                    - 가게의 대표적인 메뉴와 맛의 특징을 포함할 것.
                    - 식당의 분위기(예: 가족 단위 방문 적합, 캐주얼한 분위기 등)를 반영할 것.
                    - 설명은 반드시 한글로 작성하며, 간결하면서도 핵심적인 정보를 포함할 것.
                    - 주요 메뉴가 확인되지 않는 경우, 가게의 운영 스타일(예: 오마카세, 셀프바, 테이크아웃 전문)이나 위치적 특징(예: 바닷가 근처, 전통시장 내 위치 등)을 강조할 것.
                - **url**: 가게의 공식 웹사이트 또는 신뢰할 수 있는 정보가 제공되는 URL을 포함할 것.
                    - **우선순위**:
                    1. 공식 웹사이트 (예: https://example-restaurant.com)
                    2. 네이버 지도 또는 카카오 지도 링크 (예: https://map.naver.com/v5/entry/place/12345678)
                    3. 공식 SNS 페이지 (예: Instagram, Facebook)
                    4. 주요 맛집 리뷰 사이트 URL (예: https://mangoplate.com/restaurants/XXXX)
                    - 공식 URL이 없을 경우 null을 입력할 것.

                ### 최종 맛집 리스트 추천 규칙:
                - 하루 3끼 기준으로 최종 리스트를 구성해야 한다.
                - 예: 1박 2일 → 최소 6개 추천, 2박 3일 → 최소 9개 추천.
                - 동일한 식당이 중복되지 않도록 구성할 것.
                - 동일한 브랜드(예: 스타벅스, 맥도날드 등)의 프랜차이즈 지점이 중복되지 않도록 할 것.
                - 만약 추천된 식당이 부족할 경우, 전체 후보 리스트에서 추가하여 반드시 정해진 개수를 채울 것.
                """,
                agent=self.agents["final_recommendation"],
                expected_output="최종 추천 맛집 리스트",
            ),
            Task(
                description=f"""최종 추천된 맛집 리스트에 포함된 식당들의 이미지를 검색하고,  
                기존 JSON 형식을 유지하면서 **image_url 필드만 업데이트**하라.  
                반드시 아래 JSON 스키마를 따르며, 정확하고 누락 없이 정보를 반환할 것.  

                ### JSON 스키마:
                {{
                    "kor_name": "string (가게 한글이름, 최대 255자)",
                    "eng_name": "string 또는 null (가게 영어이름, 최대 255자)",
                    "description": "string (가게 설명, 최소 150자 이상 255자 이하)",
                    "business_status": "boolean (영업 상태, true: 영업 중, false: 영업 종료)",
                    "business_hours": "string 또는 null (영업 시간 정보)"
                    "url": "string 또는 null (가게 URL, 공식 정보 우선)",
                    "image_url": "string 또는 null (가게 이미지 URL)"
                }}

                ### 이미지 검색 및 선택 기준:
                1. **최우선 조건**: 가게의 대표 메뉴나 실제 음식 사진을 우선적으로 선택할 것.
                    - 해당 식당에서 제공하는 대표적인 음식 이미지가 최우선.
                    - 가능한 경우 고화질의 실제 음식 사진을 반환할 것.

                2. **음식 사진이 없을 경우 대체 기준**:
                    - 식당 내부 사진 (실제 매장 분위기를 확인할 수 있는 이미지)
                    - 식당 외관 사진 (가게의 위치와 특성을 나타내는 이미지)

                3. **반드시 지켜야 할 공통 조건**:
                    - 이미지 해상도는 최소 300x300 이상일 것.
                    - 최신 1년 이내의 고화질 이미지를 우선 선택할 것.
                    - 로고, 지도 캡처, 텍스트가 포함된 이미지, 메뉴판 등의 이미지는 제외할 것.
                    - 노출도가 낮거나 신뢰할 수 없는 출처의 이미지는 사용하지 말 것.

                ### 반환 방식:
                - 기존 JSON 데이터를 유지하면서, `image_url` 필드만 추가 또는 업데이트할 것.
                - 검색된 이미지가 없을 경우 `image_url`은 `null`로 설정할 것.

                위의 기준을 적용하여 **각 식당에 대한 최적의 이미지 URL을 반환**하라.
                """,
                agent=self.agents["image_search"],
                expected_output="네이버 이미지 검색 API 또는 기타 신뢰할 수 있는 출처를 활용하여 업데이트된 맛집 리스트",
            ),
            Task(
                description=f"""최종 추천된 맛집 리스트에 포함된 식당들에 대해 {input_data['main_location']} 지역을 포함하여 **카카오 로컬 API**를 사용하여 상세 정보를 수집하라.  
                기존 데이터를 유지하면서 다음 필드들을 업데이트해야 한다.  

                ### **필수 수집 정보**:
                - **address**: 식당의 도로명 주소를 수집하며, 도로명 주소가 없는 경우 지번 주소를 반환할 것.  
                - **latitude, longitude**: 검색된 식당의 정확한 위도 및 경도 좌표를 반환할 것.  
                - **map_url**: 해당 식당의 카카오맵 URL을 제공할 것.  
                - **phone_number**: 식당의 전화번호를 수집할 것.  

                ### **여행 일정 기반 필수 규칙**:
                - **spot_category**는 항상 `2`로 설정해야 한다.  
                - **day_x**는 사용자의 여행 일정에서 **해당 식당이 추천된 날짜**를 의미한다.  
                - **order**는 `day_x` 내에서의 추천 순서 (아침: 1, 점심: 2, 저녁: 3)를 의미한다.  
                - **spot_time**은 아침, 점심, 저녁의 예상 방문 시간을 `hh:mm:ss` 형식으로 반환해야 한다.  
                - **order 및 day_x 값은 사용자의 여행 일정에 맞게 자동 조정해야 한다.**  

                ### **반환 데이터 형식 및 예외 처리**:
                - 기존 JSON 형식을 유지하면서, 위에서 지정한 필드를 업데이트해야 한다.  
                - `business_status`는 반드시 `true`, `false` 값으로 반환할 것.  
                - 정보가 없는 경우 해당 필드는 `null`로 설정할 것.  

                ### **검색 주의사항**:
                - 모든 식당 검색 시 "{input_data['main_location']}"을 포함하여 검색할 것
                - 정확한 검색을 위해 지역명을 검색어 앞에 추가할 것 (예: "{input_data['main_location']} 식당이름")

                위 기준을 적용하여 **카카오 로컬 API를 활용한 상세 정보를 반환**하라.
                """,
                agent=self.agents["kakao_local_search"],
                expected_output="카카오 로컬 API로 업데이트된 맛집 리스트",
                output_pydantic=spots_pydantic,
            ),
        ]

    def _process_result(self, result, input_data: dict) -> dict:
        """결과를 처리하는 메서드"""
        if hasattr(result, "tasks_output") and result.tasks_output:
            final_task_output = result.tasks_output[-1]
            if hasattr(final_task_output, "pydantic"):
                spots_data = final_task_output.pydantic.model_dump()
            else:
                spots_data = json.loads(final_task_output.raw)
        else:
            spots_data = {"spots": []}

        return {
            "message": "요청이 성공적으로 처리되었습니다.",
            "plan": {
                "name": input_data.get("name", "여행 일정"),
                "start_date": input_data["start_date"],
                "end_date": input_data["end_date"],
                "main_location": input_data["main_location"],
                "ages": input_data.get("ages", 0),
                "companion_count": sum(
                    companion.get("count", 0)
                    for companion in input_data.get("companion_count", [])
                ),
                "concepts": ", ".join(input_data.get("concepts", [])),
                "member_id": input_data.get("member_id", 0),
                "created_at": datetime.now().strftime("%Y-%m-%d"),
                "updated_at": datetime.now().strftime("%Y-%m-%d"),
            },
            "spots": spots_data.get("spots", []),
        }

    async def create_recommendation(
        self, input_data: dict, prompt: Optional[str] = None
    ) -> dict:
        """추천 워크플로우를 실행하는 메서드"""
        try:
            # 1. 입력 데이터 전처리
            processed_input, prompt_text = self._process_input(input_data, prompt)

            # 2. Task 생성
            tasks = self._create_tasks(processed_input, prompt_text)

            # 3. Crew 실행
            crew = Crew(tasks=tasks, agents=list(self.agents.values()), verbose=True, memory=True)

            # 4. 결과 처리
            result = await crew.kickoff_async()
            return self._process_result(result, processed_input)

        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
