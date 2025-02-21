import traceback
import json
from datetime import datetime
from crewai import Agent, Task, Crew, LLM, Process
from typing import List, Dict, Optional
from fastapi import HTTPException
from app.dtos.spot_models import spots_pydantic
from dotenv import load_dotenv
import os
import gc
from app.repository.agents.restaurant_plan_spots_repository import (
    get_member_plan_spots,
    get_latest_plan,
)
from app.repository.members.mebmer_repository import get_memberId_by_email
from sqlmodel.ext.asyncio.session import AsyncSession
from app.services.agents.tools.restaurant_tool import (
    GeocodingTool,
    RestaurantBasicSearchTool,
    NaverWebSearchTool,
    NaverImageSearchTool,
    KakaoLocalSearchTool,
)
from redis.asyncio import Redis
from app.services.agents.redis.spot_redis import SpotRedisService, SpotCategory
from app.utils.time_check import time_check
import logging

logger = logging.getLogger(__name__)

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# logging 아이콘
# 🔵: 전달받은 데이터 유무 확인
# 🟢: 새로 생성된 일정이거나 plan_id 없는 경우(redis)
# 🟡: 기존 일정 수정(DB)
# 🟣: redis


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
        self.llm = LLM(model="gpt-4o-mini", temperature=0, api_key=OPENAI_API_KEY)
        # Tools 초기화
        self.geocoding_tool = GeocodingTool()
        self.restaurant_search_tool = RestaurantBasicSearchTool()
        self.web_search_tool = NaverWebSearchTool()
        self.image_search_tool = NaverImageSearchTool()
        self.kakao_local_search_tool = KakaoLocalSearchTool()
        self.agents = self._create_agents()
        self.tasks = self._create_tasks()

        self.tasks["keyword_task"].context = [self.tasks["geocoding_task"]]
        self.tasks["search_task"].context = [self.tasks["keyword_task"]]
        self.tasks["recommendation_task"].context = [self.tasks["search_task"]]
        self.tasks["image_task"].context = [self.tasks["recommendation_task"]]
        self.tasks["detail_task"].context = [self.tasks["image_task"]]

    def _process_input(
        self, input_data: dict, prompt: Optional[str] = None
    ) -> tuple[dict, str]:
        """입력 데이터 전처리"""
        logger.info(f"[입력 데이터] input_data: {input_data}")
        logger.info(f"[프롬프트 입력] prompt: {prompt}")

        if prompt:
            # prompt가 있으면 concepts 무시
            input_data["concepts"] = []
            prompt_text = f"다음 조건에 맞춰서 추천해주세요: {prompt}"
        else:
            # prompt가 없을 때만 concepts 처리
            valid_concepts = [
                "낮술",
                "해산물",
                "고기",
                "채식",
                "브런치",
            ]
            filtered_concepts = [
                concept
                for concept in input_data.get("concepts", [])
                if concept in valid_concepts
            ]
            if not filtered_concepts:
                filtered_concepts = ["맛집"]
            logger.info(f"[컨셉 필터링] filtered_concepts: {filtered_concepts}")
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
            "keyword_extraction": Agent(
                role="키워드 추출 전문가",
                goal="여행 정보와 프롬프트에서 맛집 검색에 필요한 정확히 3개의 핵심 키워드를 추출합니다.",
                backstory="""나는 자연어 처리 전문가로, 사용자의 요구사항에서 핵심 키워드를 추출하여 맛집 검색의 정확도를 높입니다.
                각 키워드는 '지역명 + 목적' 형식으로 구성하며, 실제 검색에 효과적인 구체적인 키워드만을 사용합니다.""",
                tools=[],
                llm=self.llm,
                verbose=True,
                async_execution=True,
                memory=True,
            ),
            "restaurant_search": Agent(
                role="맛집 기본 조회 전문가",
                goal="좌표 정보를 활용하여 식당의 기본 정보를 조회한다.",
                backstory="나는 맛집 데이터 분석 전문가로, Google Maps API를 사용하여 특정 위치의 식당 정보를 조회한다.",
                tools=[self.restaurant_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
                memory=True,
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

    def _create_tasks(self) -> Dict[str, Task]:
        """Task들을 생성하는 메서드"""
        return {
            "geocoding_task": Task(
                description="{main_location}의 좌표 조회",
                agent=self.agents["geocoding"],
                expected_output="위치 좌표",
            ),
            "keyword_task": Task(
                description="""이전 Task에서 얻은 좌표와 여행 정보를 바탕으로 맛집 검색에 사용할 가장 효과적인 검색 키워드 3개를 생성해주세요:
                # 입력 정보
                지역: {main_location}
                좌표: 이전 태스크에서 생성된 좌표 결과
                여행 기간: {start_date} ~ {end_date}
                연령대: {ages}
                동반자: {companion_count}
                {prompt_text}

                # 규칙
                1. 정확히 3개의 검색 키워드를 생성할 것
                2. 각 키워드는 "{main_location} + 목적" 형식으로 구성할 것
                3. 실제 검색에 효과적인 구체적인 키워드로 구성할 것
                4. 반드시 음식점(식당)과 관련된 키워드만 생성할 것. 카페, 숙소 등 음식점과 직접 연관되지 않은 업종의 키워드는 포함되지 않는 것
                5. 반환 형식은 다음과 같이 할 것:
                {{
                    "coordinates": "이전 Task의 coordinates 값을 그대로 전달",
                    "keywords": ["키워드1", "키워드2", "키워드3"]
                }}
                """,
                agent=self.agents["keyword_extraction"],
                expected_output="좌표와 3개의 맛집 검색 키워드",
            ),
            "search_task": Task(
                description="""{start_date}부터 {end_date}까지의 여행 일정에 맞춰서 맛집을 조회해주세요.
                기존에 추천되었던 {existing_spot_names} 식당들은 제외하고 정보를 조회해주세요.""",
                agent=self.agents["restaurant_search"],
                expected_output="맛집 기본 정보 리스트",
            ),
            "recommendation_task": Task(
                description="""{main_location} 지역의 맛집 데이터를 최신 검색 결과를 활용하여 수집하고,
                {start_date}부터 {end_date}까지 여행하는 {ages} 연령대의 고객과 
                동반자({companion_count})를 위한
                {prompt_text}

                제공된 맛집 목록 중에서, 검색된 전체 맛집 수보다 2개 적게 추천해야 합니다.
                예를 들어, 13개의 맛집이 검색되었다면 최종 추천은 11개가 되어야 합니다.

                ### 맛집 선별 및 추천 규칙:
                1. **여행 일정에 따른 추천 개수 계산 방법**  
                - 추천 개수 = (검색된 맛집 수) - 2  
                - 예시:
                    * 1일 여행 (7개 검색): 5개 추천  
                    * 2일 여행 (10개 검색): 8개 추천  
                    * 3일 여행 (13개 검색): 11개 추천  
                    * 4일 여행 (16개 검색): 14개 추천  

                2. **선별 기준**  
                - 하루 3끼 기준으로 일정에 맞게 구성할 것  
                - 동반자의 연령대 및 특성을 고려한 적합성 평가  
                - 방문 시간대와 위치를 고려하여 효율적인 동선 구성  
                - 동일 식당 또는 동일 프랜차이즈 지점은 중복해서 추천하지 말 것  

                3. **필수 검토사항**  
                - 영업 상태가 확인된 식당을 우선 추천할 것  
                - 접근성과 예상 대기시간을 고려할 것  
                - 동반자 구성에 따른 메뉴의 다양성을 확인할 것  

                4. **출력 형식**  
                반드시 아래 JSON 스키마에 맞춰, 누락 없이 정확하게 정보를 작성할 것:

                {{
                    "kor_name": "string (가게 한글이름, 최대 255자)",
                    "eng_name": "string 또는 null (가게 영어이름, 최대 255자)",
                    "description": "string (가게 설명, 최소 150자 이상 180자 이하)",
                    "business_status": "boolean (영업 상태, true: 영업 중, false: 영업 종료)",
                    "business_hours": "string 또는 null (영업 시간 정보)",
                    "url": "string 또는 null (가게 URL, 공식 정보 우선)"
                }}

                ### 상세 정보 수집 지시사항:
                - **eng_name**: kor_name을 영어로 번역하여 입력할 것.
                    - 예시: "미포집" → "Mipojip"
                    - 식당 이름의 의미를 살려서 적절하게 번역할 것.
                - **description**: 수집한 데이터를 바탕으로 가게의 주요 메뉴, 분위기, 위치적 특징을 포함하여 **최소 150자 이상 180자 이하**로 작성할 것.
                    - **절대 식당 이름을 문장 앞에 사용하지 말 것.**
                    - 식당 이름이 포함된 문장이 생성되었을 경우, 반드시 제거하고 자연스럽게 다시 작성할 것.
                    - 대표 메뉴, 맛의 특징, 분위기 등을 반영할 것.
                - **url**: 가게의 공식 웹사이트 또는 신뢰할 수 있는 URL을 우선 포함할 것.
                    - 공식 웹사이트가 없으면 null을 입력할 것.
                    - 우선순위: 공식 웹사이트 > 네이버/카카오 지도 링크 > 공식 SNS 페이지 > 맛집 리뷰 사이트 URL.
                """,
                agent=self.agents["final_recommendation"],
                expected_output="최종 추천 맛집 리스트",
            ),
            "image_task": Task(
                description="""최종 추천된 맛집 리스트에 포함된 식당들의 이미지를 검색하고,  
                기존 JSON 형식을 유지하면서 **image_url 필드만 업데이트**하라.  
                반드시 아래 JSON 스키마를 따르며, 정확하고 누락 없이 정보를 반환할 것.  

                ### JSON 스키마:
                {{
                    "kor_name": "string (가게 한글이름, 최대 255자)",
                    "eng_name": "string 또는 null (가게 영어이름, 최대 255자)",
                    "description": "string (가게 설명, 최소 150자 이상 180자 이하)",
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
                    - HTTPS 프로토콜을 사용하는 이미지 URL만 허용 (http:// URL은 제외)
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
            "detail_task": Task(
                description="""최종 추천된 맛집 리스트에 포함된 식당들에 대해 {main_location} 지역을 포함하여 **카카오 로컬 API**를 사용하여 상세 정보를 수집하라.  
                기존 데이터를 유지하면서 다음 필드들을 업데이트해야 한다.  

                ### **필수 수집 정보**:
                - **address**: 식당의 도로명 주소를 수집하며, 도로명 주소가 없는 경우 지번 주소를 반환할 것.  
                - **latitude, longitude**: 검색된 식당의 정확한 위도 및 경도 좌표를 반환할 것.  
                - **map_url**: 해당 식당의 카카오맵 URL을 제공할 것.  
                - **phone_number**: 식당의 전화번호를 수집할 것.

                ## 여행 일정 기반 필수 규칙
                - `spot_category`는 항상 `2`로 설정해야 한다.
                - `day_x`, `order`는 0으로 항상  `0`로 설정해야 한다.  
                - `latitude, longitude`를 활용하여 **사용자의 이동 동선을 고려**해 추천할 것.  
                - 같은 지역에서 **불필요한 장거리 이동이 발생하지 않도록 조정**할 것.  

                ## 반환 데이터 형식 및 예외 처리
                - 기존 JSON 형식을 유지하면서, 위에서 지정한 필드를 업데이트해야 한다.  
                - `business_status`는 반드시 `true`, `false` 값으로 반환할 것.  
                - 정보가 없는 경우 해당 필드는 `null`로 설정할 것.

                ### **검색 주의사항**:
                - 모든 식당 검색 시 "{main_location}"을 포함하여 검색할 것.  
                - 정확한 검색을 위해 지역명을 검색어 앞에 추가할 것 (예: "{main_location} 식당이름").

                위 기준을 적용하여 **카카오 로컬 API를 활용한 상세 정보를 반환**하라.
                """,
                agent=self.agents["kakao_local_search"],
                expected_output="카카오 로컬 API로 업데이트된 맛집 리스트",
                output_pydantic=spots_pydantic,
            ),
        }

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
                    for companion in input_data.get("original_companion_count", [])
                ),
                "concepts": ", ".join(input_data.get("concepts", [])),
                "member_id": input_data.get("member_id", 0),
                "created_at": datetime.now().strftime("%Y-%m-%d"),
                "updated_at": datetime.now().strftime("%Y-%m-%d"),
            },
            "spots": spots_data.get("spots", []),
        }

    @time_check
    async def create_recommendation_restaurant(
        self,
        input_data: dict,
        session: AsyncSession = None,
        redis_client: Redis = None,
        prompt: Optional[str] = None,
    ) -> dict:
        try:
            existing_spot_names = []
            member_id = None

            # 데이터 유무 확인
            print(f"🔵 email 존재: {bool(input_data.get('email'))}")
            print(f"🔵 session 존재: {bool(session)}")
            print(f"🔵 redis 존재: {bool(redis_client)}")
            print(f"🔵 plan_id 없음: {not input_data.get('plan_id')}")

            # member_id 조회 및 Redis/DB 로직 실행
            if input_data.get("email") and session:
                member_id = await get_memberId_by_email(input_data["email"], session)
                print(f"💥💥 member_id 조회됨: {bool(member_id)}")

                if not input_data.get("plan_id"):
                    # 새로 생성된 일정이거나 plan_id 없는 경우 - Redis 사용
                    logger.info("🟢 새로 생성된 일정: Redis 사용 로직 실행 시작")
                    try:
                        redis_service = SpotRedisService(redis_client)
                        redis_excluded_spots = await redis_service.get_spots(
                            member_id=member_id,
                            main_location=input_data["main_location"],
                            category=SpotCategory.RESTAURANT,
                        )
                        if redis_excluded_spots:
                            existing_spot_names = redis_excluded_spots
                            logger.info(
                                f"🟢 Redis에서 가져온 제외 식당 목록: {redis_excluded_spots}"
                            )
                    except Exception as e:
                        logger.error(f"Redis 조회 중 오류 발생: {e}")
                else:
                    # 기존 일정 수정의 경우 - DB 사용
                    current_plan_id = input_data.get("plan_id")
                    print(f"🟡 current_plan_id: {current_plan_id}")

                    try:
                        # 현재 plan이 해당 member의 것인지 확인
                        plan_spots_with_spot_info = await get_member_plan_spots(
                            current_plan_id, member_id, session
                        )

                        if not plan_spots_with_spot_info:
                            latest_plan = await get_latest_plan(member_id, session)
                            if latest_plan:
                                plan_spots_with_spot_info = await get_member_plan_spots(
                                    latest_plan.id, member_id, session
                                )
                                logger.info(f"🟡 최신 plan_id 사용: {latest_plan.id}")
                        else:
                            logger.info(f"🟡 전달받은 plan_id 사용: {current_plan_id}")

                        if (
                            plan_spots_with_spot_info
                            and "detail" in plan_spots_with_spot_info
                        ):
                            existing_spot_names = [
                                item["spot"].kor_name
                                for item in plan_spots_with_spot_info["detail"]
                            ]
                            logger.info(
                                f"🟡 DB에서 가져온 기존 장소들: {existing_spot_names}"
                            )
                    except Exception as e:
                        logger.error(f"🟡 DB 장소 조회 중 오류 발생: {e}")
                        traceback.print_exc()

            # 1. 입력 데이터 전처리
            processed_input, prompt_text = self._process_input(input_data, prompt)
            processed_input["existing_spot_names"] = existing_spot_names
            processed_input["prompt_text"] = prompt_text

            # 원본 데이터 보관 및 문자열 변환 분리
            processed_input["original_companion_count"] = input_data.get("companion_count", [])  # 원본 보관
            processed_input["companion_count"] = ", ".join(
                [f"{c['label']} {c['count']}명" for c in input_data["companion_count"]]
            )

            # 3. Crew 실행
            crew = Crew(
                agents=list(self.agents.values()),
                tasks=list(self.tasks.values()),
                process=Process.sequential,
                verbose=True,
                memory=True,
            )

            # 4. 결과 실행 및 처리
            result = await crew.kickoff_async(inputs=processed_input)
            processed_result = self._process_result(result, processed_input)
            print(f"⭐️ processed_result: {processed_result}")

            # 모든 작업이 끝난 후 메모리 정리
            gc.collect()

            # 5. plan_id가 없는 경우, 결과를 Redis에 저장
            if not input_data.get("plan_id") and redis_client:
                try:
                    redis_service = SpotRedisService(redis_client)
                    restaurants_to_save = [
                        spot["kor_name"] for spot in processed_result.get("spots", [])
                    ]
                    print(f"🟢 spots to save: {restaurants_to_save}")

                    await redis_service.add_spots(
                        member_id=member_id,
                        main_location=input_data["main_location"],
                        category=SpotCategory.RESTAURANT,
                        spots=restaurants_to_save,
                    )
                except Exception as e:
                    logger.error(f"Redis 저장 중 오류 발생: {e}")
                    traceback.print_exc()

            return processed_result

        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
