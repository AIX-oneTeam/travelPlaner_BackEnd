import traceback
import json
from datetime import datetime, timedelta
from typing import Dict, Optional

from crewai import Agent, Task, Crew, LLM, Process
from sqlmodel.ext.asyncio.session import AsyncSession
from redis.asyncio import Redis
import logging
import os
from dotenv import load_dotenv

from app.dtos.spot_models import spots_pydantic
from app.utils.calculate_trip_days import calculate_trip_days
from app.utils.time_check import time_check

# DB 관련 함수 (DB 조회 관련)
from app.repository.agents.site_plan_spots_repository import (
    get_member_plan_spots,
    get_latest_plan,
)

# Redis 서비스
from app.services.agents.redis.spot_redis import SpotRedisService, SpotCategory

# 실제 구현된 Tool 클래스들
from app.services.agents.tools.site_tool import (
    NaverTouristWebSearchTool,
    NaverTouristImageSearchTool,
    NaverTouristReviewTool,
    NaverTouristBusinessInfoTool,
)

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
logger = logging.getLogger(__name__)


def parse_first_json(s: str):
    """문자열에서 첫 번째 JSON 객체만 파싱하여 반환"""
    decoder = json.JSONDecoder()
    obj, idx = decoder.raw_decode(s)
    return obj


class TouristAgentService:
    """관광지 추천을 위한 Agent 서비스 (Singleton)"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TouristAgentService, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
        """서비스 초기화: LLM, Tool, Agent 등을 한 번만 설정"""
        self.llm = LLM(
            model="gpt-4o-mini",
            api_key=OPENAI_API_KEY,
            temperature=0,
            max_tokens=4000,
        )

        # Tool 초기화
        self.get_tourist_list_tool = NaverTouristWebSearchTool()
        self.get_tourist_info_tool = NaverTouristImageSearchTool()
        self.get_tourist_review_tool = NaverTouristReviewTool()
        self.get_tourist_business_info_tool = NaverTouristBusinessInfoTool()

        # 에이전트 생성
        self.agents = self._create_agents()

        # 초기 Task들은 빈 값으로 세팅
        self.tasks = self._create_tasks({})

    def _create_agents(self) -> Dict[str, Agent]:
        """에이전트들을 생성 및 반환"""
        return {
            "collector": Agent(
                role="관광지 리스트 생성 전문가",
                goal="지정된 지역의 관광지 좌표를 조회하여 제공합니다.",
                backstory="지정된 지역의 좌표를 기반으로 관광지 정보를 수집합니다.",
                tools=[self.get_tourist_list_tool],
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True,
            ),
            "keyword_extraction": Agent(
                role="키워드 추출 전문가",
                goal="여행 정보에서 관광지 검색에 사용할 정확히 3개의 핵심 키워드를 추출합니다.",
                backstory="사용자의 요구사항에서 핵심 키워드를 추출하여 관광지 검색의 정확도를 높입니다.",
                tools=[],
                llm=self.llm,
                verbose=True,
                async_execution=True,
                memory=True,
            ),
            "researcher": Agent(
                role="관광지 기본 정보 수집 및 위치 검증가",
                goal="지정된 지역의 관광지 기본 정보를 수집하고, 지역 외 관광지는 제외합니다.",
                backstory="지정된 지역 내 관광지의 기본 정보를 수집하고 검증합니다.",
                tools=[self.get_tourist_info_tool],
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True,
            ),
            "researcher_detail": Agent(
                role="관광지 상세 정보 수집 및 업종 검증가",
                goal="관광지의 상세 정보를 수집하고, 관광지로 부적합한 곳은 제외합니다.",
                backstory="관광지의 상세 정보를 수집하고 적합성을 검증합니다.",
                tools=[self.get_tourist_business_info_tool],
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True,
            ),
            "reviewer": Agent(
                role="관광지 리뷰 분석가",
                goal="관광지의 리뷰를 분석하여 주요 특징을 추출합니다.",
                backstory="최신 리뷰를 바탕으로 관광지의 특징을 분석합니다.",
                tools=[self.get_tourist_review_tool],
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True,
            ),
            "decider": Agent(
                role="고객의 요구사항을 반영한 관광지 선정",
                goal="고객의 여행 지역과 요구사항에 맞는 관광지를 최종 추천합니다.",
                backstory="고객의 선호도를 반영하여 최적의 관광지를 선정합니다.",
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True,
            ),
        }

    def _create_tasks(self, input_data: dict, prompt_text: str = "") -> Dict[str, Task]:
        """Task들을 생성"""
        companion_text = ""
        if input_data.get("companion_count"):
            try:
                companion_text = ", ".join(
                    [
                        f"{c.get('label', '미지정')} {c.get('count', 0)}명"
                        for c in input_data["companion_count"]
                    ]
                )
            except Exception:
                companion_text = "동반자 정보 없음"

        existing_spots = input_data.get("existing_spot_names", [])
        existing_spots_text = ", ".join(existing_spots) if existing_spots else "없음"
        main_location = input_data.get("main_location", "지역 미지정")

        json_schema_prompt = (
            "{{\n"
            '  "kor_name": string,\n'
            '  "eng_name": string or null,\n'
            '  "address": string,\n'
            '  "url": string or null,\n'
            '  "image_url": string,\n'
            '  "map_url": string,\n'
            '  "spot_category": number,\n'
            '  "phone_number": string or null,\n'
            '  "business_status": boolean or null,\n'
            '  "business_hours": string or null,\n'
            '  "spot_time": string or null\n'
            "}}"
        )

        return {
            "collector_task": Task(
                description=f"{main_location}의 좌표를 조회해주세요.",
                agent=self.agents["collector"],
                expected_output=f"{main_location}의 좌표",
            ),
            "researcher_task": Task(
                description=(
                    f"이전 Task에서 얻은 {main_location}의 좌표와 여행 정보를 바탕으로 관광지 검색에 사용할 "
                    "가장 효과적인 검색 키워드 3개를 생성해주세요:\n"
                    "# 입력 정보\n"
                    f"지역: {main_location}\n"
                    "좌표: 이전 태스크에서 생성된 좌표 결과\n"
                    f"여행 기간: {input_data.get('start_date', '')} ~ {input_data.get('end_date', '')}\n"
                    f"연령대: {input_data.get('ages', '연령대 미지정')}\n"
                    f"동반자: {companion_text}\n"
                    f"{prompt_text}\n"
                    "# 규칙\n"
                    "1. 정확히 3개의 검색 키워드를 생성할 것\n"
                    f'2. 각 키워드는 "{main_location} + 목적" 형식으로 구성할 것\n'
                    "3. 실제 검색에 효과적인 구체적인 키워드로 구성할 것\n"
                    "4. 반환 형식은 다음과 같이 할 것:\n"
                    "{{\n"
                    '  "coordinates": "이전 Task의 coordinates 값을 그대로 전달",\n'
                    '  "keywords": ["키워드1", "키워드2", "키워드3"]\n'
                    "}}"
                ),
                agent=self.agents["keyword_extraction"],
                expected_output=f"{main_location}의 좌표와 3개의 관광지 검색 키워드",
            ),
            "researcher_detail_task": Task(
                description=(
                    f"기존에 추천되었던 관광지({existing_spots_text})는 제외하고, {main_location}의 새로운 관광지 정보를 조회해주세요."
                ),
                agent=self.agents["researcher"],
                expected_output=f"{main_location}의 관광지 기본 정보 리스트",
            ),
            "reviewer_task": Task(
                description=(
                    f"{main_location} 지역의 관광지 데이터를 최신 검색 결과를 활용하여 수집하고,\n"
                    f"{input_data.get('start_date', '')}부터 {input_data.get('end_date', '')}까지 여행하는 "
                    f"{input_data.get('ages', '연령대 미지정')} 연령대의 고객과 동반자({companion_text})를 위한\n"
                    f"{prompt_text}\n"
                    "반드시 아래 JSON 스키마에 맞추어 정확하고 누락 없이 정보를 반환할 것.\n"
                    "JSON 스키마:\n"
                    f"{json_schema_prompt}"
                ),
                agent=self.agents["reviewer"],
                expected_output=f"{main_location}의 최종 관광지 추천 결과 (JSON array)",
            ),
            "decider_task": Task(
                description=(
                    f"{main_location}의 고객 요구에 맞는 관광지를 최종 추천합니다.\n"
                    "이전 태스크(reviewer_task)에서 제공된 관광지 데이터를 기반으로, "
                    f"{input_data.get('ages', '연령대 미지정')} 연령대와 동반자({companion_text})의 "
                    f"여행 기간 {input_data.get('start_date', '')} ~ {input_data.get('end_date', '')}에 "
                    "적합한 관광지를 선정해주세요.\n"
                    "만약 이전 태스크의 데이터가 없거나 부족한 경우, {main_location} 내에서 인기 있는 관광지를 추천해주세요.\n"
                    "반드시 아래 JSON 스키마에 맞추어 결과를 반환하세요:\n"
                    f"{json_schema_prompt}"
                ),
                agent=self.agents["decider"],
                expected_output=f"{main_location}의 최종 관광지 추천 결과 (JSON array)",
            ),
        }

    @time_check
    async def create_tourist_plan(
        self,
        input_data: dict,
        redis_client: Redis = None,
        session: Optional[AsyncSession] = None,
        prompt: Optional[str] = "",
    ) -> dict:
        """관광지 추천 실행"""
        if input_data is None:
            raise ValueError("[TouristAgent] 에러 - input_data이 없습니다.")

        # 입력 데이터 전처리 및 필요한 값 계산
        input_data["concepts"] = ", ".join(input_data.get("concepts", []))
        input_data["prompt"] = input_data.get("prompt", "") or prompt
        days = calculate_trip_days(
            input_data.get("start_date", ""), input_data.get("end_date", "")
        )
        input_data["days"] = days
        input_data["n"] = days * 2

        if redis_client is None:
            raise ValueError("[TouristAgent] 에러 - Redis 연결을 확인해주세요")

        # SpotRedisService 인스턴스 생성
        spot_redis_service = SpotRedisService(redis_client)

        try:
            # Task 업데이트 및 확인
            self.tasks = self._create_tasks(input_data, prompt)
            logger.info(
                f"[TouristAgent] Tasks updated with main_location: {input_data.get('main_location')}"
            )
            logger.info(
                f"[TouristAgent] Collector task description: {self.tasks['collector_task'].description}"
            )

            # Task 간 context 설정
            self.tasks["researcher_task"].context = [self.tasks["collector_task"]]
            self.tasks["researcher_detail_task"].context = [
                self.tasks["researcher_task"]
            ]
            self.tasks["reviewer_task"].context = [self.tasks["researcher_detail_task"]]
            self.tasks["decider_task"].context = [self.tasks["reviewer_task"]]

            # 새로운 일정 생성 (plan_id 없음)
            if not input_data.get("plan_id"):
                cached_tourist_lists = await spot_redis_service.get_spots(
                    SpotCategory.SITE, input_data["main_location"]
                )
                input_data["cached_tourist_lists"] = cached_tourist_lists or []
                logger.info(
                    f"[TouristAgent] Cached tourist lists: {cached_tourist_lists}"
                )

                if len(cached_tourist_lists) < days * 2:
                    # Crew 동적 생성
                    crew = Crew(
                        agents=list(self.agents.values()),
                        tasks=list(self.tasks.values()),
                        process=Process.sequential,
                        verbose=True,
                    )
                    result = await crew.kickoff_async(inputs=input_data)
                    logger.info(
                        f"[TouristAgent] Crew execution completed with result: {result}"
                    )
                    logger.info(f"[TouristAgent] Result type: {type(result)}")

                    if result is None:
                        raise ValueError(
                            "[TouristAgent] 에러 - Crew 실행 결과가 None입니다."
                        )

                    # CrewOutput 처리
                    if hasattr(result, "tasks_output"):
                        # 마지막 태스크 (decider_task)의 결과를 사용
                        final_output = (
                            result.tasks_output[-1].raw if result.tasks_output else None
                        )
                        if final_output:
                            final_result = json.loads(final_output)
                        else:
                            raise ValueError(
                                "[TouristAgent] 에러 - tasks_output이 비어 있음"
                            )
                    else:
                        raise ValueError(
                            f"[TouristAgent] 에러 - 예상치 못한 result 타입: {type(result)}"
                        )

                    logger.info(
                        f"[TouristAgent] Final result type: {type(final_result)}"
                    )
                    logger.info(f"[TouristAgent] Final result: {final_result}")

                    # 리스트가 맞는지 확인
                    if not isinstance(final_result, list):
                        raise ValueError(
                            f"[TouristAgent] 에러 - final_result가 리스트가 아님: {type(final_result)}"
                        )

                    # Redis에 저장
                    spot_names = [spot["kor_name"] for spot in final_result]
                    await spot_redis_service.add_spots(
                        SpotCategory.SITE, input_data["main_location"], spot_names
                    )
                    logger.info(f"[TouristAgent] Spots saved to Redis: {spot_names}")
                    return final_result

                else:
                    # Draft Crew 동적 생성
                    draft_crew = Crew(
                        agents=[self.agents["decider"]],
                        tasks=[self.tasks["decider_task"]],
                        verbose=True,
                    )
                    result = await draft_crew.kickoff_async(inputs=input_data)
                    logger.info(
                        f"[TouristAgent] Draft crew execution completed with result: {result}"
                    )
                    logger.info(f"[TouristAgent] Result type: {type(result)}")

                    if result is None:
                        raise ValueError(
                            "[TouristAgent] 에러 - Draft Crew 실행 결과가 None입니다."
                        )

                    if hasattr(result, "tasks_output"):
                        final_output = (
                            result.tasks_output[-1].raw if result.tasks_output else None
                        )
                        if final_output:
                            final_result = json.loads(final_output)
                        else:
                            raise ValueError(
                                "[TouristAgent] 에러 - tasks_output이 비어 있음"
                            )
                    else:
                        raise ValueError(
                            f"[TouristAgent] 에러 - 예상치 못한 result 타입: {type(result)}"
                        )

                    logger.info(
                        f"[TouristAgent] Final result type: {type(final_result)}"
                    )

                    if not isinstance(final_result, list):
                        raise ValueError(
                            f"[TouristAgent] 에러 - final_result가 리스트가 아님: {type(final_result)}"
                        )

                    return final_result

            # 기존 일정 수정 (plan_id 있음)
            else:
                member_id = input_data.get("member_id")
                current_plan_id = input_data.get("plan_id")
                plan_spots_with_info = await get_member_plan_spots(
                    current_plan_id, member_id, session
                )
                if plan_spots_with_info and "detail" in plan_spots_with_info:
                    existing_spot_names = [
                        item["spot"].kor_name for item in plan_spots_with_info["detail"]
                    ]
                    input_data["existing_spot_names"] = existing_spot_names
                    logger.info(
                        f"🟡 DB에서 가져온 기존 관광지들: {existing_spot_names}"
                    )
                else:
                    logger.info("🟡 기존 DB 데이터가 없으므로 Redis 캐시를 사용합니다.")
                    cached_tourist_lists = await spot_redis_service.get_spots(
                        SpotCategory.SITE, input_data["main_location"]
                    )
                    input_data["existing_spot_names"] = cached_tourist_lists or []

                # Crew 동적 생성
                crew = Crew(
                    agents=list(self.agents.values()),
                    tasks=list(self.tasks.values()),
                    process=Process.sequential,
                    verbose=True,
                )
                result = await crew.kickoff_async(inputs=input_data)
                logger.info(
                    f"[TouristAgent] Crew execution completed (existing plan) with result: {result}"
                )
                logger.info(f"[TouristAgent] Result type: {type(result)}")

                if result is None:
                    raise ValueError(
                        "[TouristAgent] 에러 - Crew 실행 결과가 None입니다."
                    )

                if hasattr(result, "tasks_output"):
                    final_output = (
                        result.tasks_output[-1].raw if result.tasks_output else None
                    )
                    if final_output:
                        final_result = json.loads(final_output)
                    else:
                        raise ValueError(
                            "[TouristAgent] 에러 - tasks_output이 비어 있음"
                        )
                else:
                    raise ValueError(
                        f"[TouristAgent] 에러 - 예상치 못한 result 타입: {type(result)}"
                    )

                logger.info(f"[TouristAgent] Final result type: {type(final_result)}")

                if not isinstance(final_result, list):
                    raise ValueError(
                        f"[TouristAgent] 에러 - final_result가 리스트가 아님: {type(final_result)}"
                    )

                return final_result

        except Exception as e:
            logger.error(f"[TouristAgent] 에러 - {e}")
            traceback.print_exc()
            raise e
