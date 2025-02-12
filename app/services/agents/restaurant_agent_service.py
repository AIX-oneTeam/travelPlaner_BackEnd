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
        self.agents = self._create_agents()

    def _process_input(
        self, input_data: dict, prompt: Optional[str] = None
    ) -> tuple[dict, str]:
        """입력 데이터 전처리"""
        print(f"[입력 데이터] input_data: {input_data}")
        print(f"[프롬프트 입력] prompt: {prompt}")

        # 맛집 관련 유효 컨셉 필터링
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
        prompt_text = (
            f'추가 참고: "{prompt}" 도 참고하여 추천해주세요.\n' if prompt else ""
        )

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
            "web_search": Agent(
                role="네이버 웹 검색 에이전트",
                goal="네이버 웹 검색 API를 사용해 식당의 텍스트 기반 세부 정보를 조회한다.",
                backstory="나는 네이버 웹 검색 전문가로, 식당의 상세 텍스트 정보를 제공합니다.",
                tools=[self.web_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            "final_recommendation": Agent(
                role="최종 추천 에이전트",
                goal="필터링된 맛집 후보와 네이버 텍스트 기반 세부 정보를, 여행 계획을 고려하여 최종 맛집 추천 리스트를 생성한다.",
                backstory="나는 데이터 구조화 전문가로, 후보 식당의 기본 정보, 네이버에서 수집한 텍스트 세부 정보와 여행 계획 정보를 종합하여 최종 추천 리스트를 구성한다.",
                tools=[self.web_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            "image_search": Agent(
                role="네이버 이미지 검색 에이전트",
                goal="네이버 이미지 검색 API를 사용해 식당의 이미지 URL을 조회한다.",
                backstory="나는 네이버 이미지 검색 전문가로, 식당의 정확한 이미지를 제공합니다.",
                tools=[self.image_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
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
                description=f"""이전 단계에서 평점 4.0 이상, 리뷰 수 500개 이상으로 필터링된 {input_data['main_location']} 지역의 맛집 후보 리스트를 바탕으로,
                각 식당의 세부 정보를 최신 검색 결과를 활용하여 가져오라.
                검색 시 반드시 아래 JSON 스키마에 맞추어 정확하고 누락 없이 정보를 반환할 것.
                특히, 아래 항목들은 최신 정보에 기반하여 모두 포함되어야 한다.

                JSON 스키마:
                {{
                    "kor_name": "string (가게 한글이름, 최대 255자)",
                    "eng_name": "string 또는 null (가게 영어이름, 최대 255자)",
                    "description": "string (가게 설명, 최대 255자)",
                    "address": "string (주소, 최대 255자)",
                    "url": "string 또는 null (웹사이트 URL, 최대 2083자)",
                    "map_url": "string (map_url, 최대 2083자)",
                    "latitude": "number (위도)",
                    "longitude": "number (경도)",
                    "phone_number": "string 또는 null (전화번호, 최대 300자)",
                    "business_status": "string 또는 null (영업 상태)",
                    "business_hours": "string 또는 null (영업시간, 최대 255자)"
                }}

                추가 지시사항:
                - **eng_name**: kor_name을 영어로 번역하여 입력하세요.
                    - 예시: "미포집" -> "Mipojip"
                    - 식당 이름의 의미를 살려서 적절히 번역하세요.
                - **description**: 수집한 description 데이터를 바탕으로, 식당에서 제공하는 **대표 메뉴**를 중심으로 **간결하고 명확하게 100자 이내로** 요약하여 설명하세요.  
                - 설명은 반드시 **한글**로 작성하세요.
                - **주요 메뉴가 확인되지 않는 경우, 가게의 특징이나 분위기를 반영하여 적절한 설명을 작성하세요.**

                위 JSON 스키마에 맞추어 모든 필드를 채워서 결과를 반환하라.
                    """,
                agent=self.agents["web_search"],
                expected_output="각 후보 식당의 세부 정보(details_map)",
            ),
            Task(
                description=f"""
               이전 단계에서 수집한 {input_data['main_location']} 지역의 맛집 데이터를 바탕으로, 
               {input_data['start_date']}부터 {input_data['end_date']}까지 여행하는 {input_data['ages']} 연령대의 고객과 
               동반자({', '.join([f"{c['label']} {c['count']}명" for c in input_data['companion_count']])})의 
               {', '.join(input_data.get('concepts', ['맛집']))} 컨셉에 맞는 최종 맛집 리스트를 중복 없이 추천하라.
               {prompt_text}
               
               필수:
               - 만약, 추천된 식당 리스트의 개수가 위 조건에 맞는 최종 개수보다 적을 경우, 전체 후보 리스트(해산물 관련 여부와 무관하게)에서 중복 없이 부족한 항목을 보충하여 최종 리스트가 반드시 정해진 개수(하루 3끼 기준)가 되도록 하라.
               - spot_category는 2로 고정한다.
               - day_x는 가게가 추천되는 날(예: 1일차, 2일차 등)을 의미한다.
               - order는 해당 day_x 내에서의 추천 순서(아침: 1, 점심: 2, 저녁: 3)를 의미한다.
               - spot_time은 아침, 점심, 저녁 시간대를 hh:mm:ss 형식으로 표시해야 한다.
               - order와 day_x는 사용자의 여행 일정 일수에 맞게 조정되어야 한다.
               - 최종 맛집 리스트의 개수는 하루 3끼 기준으로 결정된다. (예: 1박 2일이면 총 6개 이상, 2박 3일이면 총 9개 이상)
               - 위도, 경도, 이미지 데이터는 이전 태스크들에서 얻은 정보를 활용한다.
               """,
                agent=self.agents["final_recommendation"],
                expected_output="최종 추천 맛집 리스트",
                output_pydantic=spots_pydantic,
            ),
            Task(
                description=f"""최종 추천된 맛집 리스트에 포함된 식당들에 대해서만 이미지를 검색하고,
                이전 태스크의 spots_pydantic 형식을 유지하면서 image_url 필드만 업데이트하라.
                다음 우선순위와 조건으로 이미지를 검색할 것:

                1순위: 음식 사진
                - 해당 식당의 대표 메뉴나 실제 음식 사진을 최우선으로 검색
                - 고화질의 실제 음식 사진만 선택

                2순위: (음식 사진이 없는 경우)
                - 식당 내부 사진
                - 식당 외관 사진

                공통 필수 조건:
                - 이미지 해상도는 최소 300x300 이상
                - 최신 1년 이내의 고화질 이미지 우선
                - 로고, 지도, 텍스트가 포함된 이미지, 메뉴판 등은 제외

                모든 식당에 대해 위 우선순위와 조건을 적용하여 이미지 URL을 찾아 반환하라.
                """,
                agent=self.agents["image_search"],
                expected_output="최종 맛집 리스트",
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
            crew = Crew(tasks=tasks, agents=list(self.agents.values()), verbose=True)

            # 4. 결과 처리
            result = await crew.kickoff_async()
            return self._process_result(result, processed_input)

        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
