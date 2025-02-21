import traceback
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, List

from crewai import Agent, Task, Crew, LLM, Process
from sqlmodel.ext.asyncio.session import AsyncSession
from redis.asyncio import Redis
import logging
import os
from dotenv import load_dotenv
from app.repository.members.mebmer_repository import get_memberId_by_email
from app.dtos.spot_models import spots_pydantic
from app.utils.calculate_trip_days import calculate_trip_days
from app.utils.time_check import time_check

# DB 관련 함수
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
    decoder = json.JSONDecoder()
    obj, idx = decoder.raw_decode(s)
    return obj


class TouristAgentService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            logger.info("Creating new TouristAgentService instance")
            cls._instance = super(TouristAgentService, cls).__new__(cls)
            cls._instance.initialize()
        else:
            logger.info("Returning existing TouristAgentService instance")
        return cls._instance

    def initialize(self):
        logger.info("Initializing TouristAgentService")
        self.llm = LLM(
            model="gpt-4o-mini",
            api_key=OPENAI_API_KEY,
            temperature=0,
            max_tokens=4000,
        )
        self.get_tourist_list_tool = NaverTouristWebSearchTool()
        self.get_tourist_info_tool = NaverTouristImageSearchTool()
        self.get_tourist_review_tool = NaverTouristReviewTool()
        self.get_tourist_business_info_tool = NaverTouristBusinessInfoTool()
        self.agents = self._create_agents()
        self.tasks = self._create_tasks({})
        logger.info(
            "TouristAgentService initialized with agents: %s", list(self.agents.keys())
        )

    def _create_agents(self) -> Dict[str, Agent]:
        logger.info("Creating agents")
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
            '  "business_hours": string or null\n'
            "}}"
        )

        logger.info("Creating tasks with main_location: %s", main_location)
        return {
            "collector_task": Task(
                description=f"{main_location}의 좌표를 조회해주세요.",
                agent=self.agents["collector"],
                expected_output=f"{main_location}의 좌표",
            ),
            "researcher_task": Task(
                description=(
                    f"이전 Task에서 얻은 {main_location}의 좌표와 여행 정보를 바탕으로 관광지 검색에 사용할 "
                    f"가장 효과적인 검색 키워드 3개를 생성해주세요:\n"
                    f"# 입력 정보\n지역: {main_location}\n"
                    f"좌표: 이전 태스크에서 생성된 좌표 결과\n"
                    f"여행 기간: {input_data.get('start_date', '')} ~ {input_data.get('end_date', '')}\n"
                    f"연령대: {input_data.get('ages', '연령대 미지정')}\n"
                    f"동반자: {companion_text}\n{prompt_text}\n"
                    " # 규칙\n1. 정확히 3개의 검색 키워드를 생성할 것\n"
                    f'2. 각 키워드는 "{main_location} + 목적" 형식으로 구성할 것\n'
                    "3. 실제 검색에 효과적인 구체적인 키워드로 구성할 것\n"
                    "4. 반환 형식은 다음과 같이 할 것:\n"
                    '{{\n  "coordinates": "이전 Task의 coordinates 값을 그대로 전달",\n  '
                    '"keywords": ["키워드1", "키워드2", "키워드3"]\n}}'
                ),
                agent=self.agents["keyword_extraction"],
                expected_output=f"{main_location}의 좌표와 3개의 관광지 검색 키워드",
            ),
            "researcher_detail_task": Task(
                description=(
                    f"기존에 추천되었던 관광지({existing_spots_text})는 제외하고, "
                    f"{main_location}의 새로운 관광지 정보를 조회해주세요."
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
                    "JSON 스키마:\n" + json_schema_prompt
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
                    "만약 이전 태스크의 데이터가 없거나 부족한 경우, "
                    f"{main_location} 내에서 인기 있는 관광지를 추천해주세요.\n"
                    "반드시 아래 JSON 스키마에 맞추어 결과를 반환하세요:\n"
                    + json_schema_prompt
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
        if input_data is None:
            raise ValueError("[TouristAgent] 에러 - input_data이 없습니다.")

        logger.info("Starting create_tourist_plan with input_data: %s", input_data)

        input_data["concepts"] = ", ".join(input_data.get("concepts", []))
        input_data["prompt"] = input_data.get("prompt", "") or prompt
        days = calculate_trip_days(
            input_data.get("start_date", ""), input_data.get("end_date", "")
        )
        input_data["days"] = days
        # 하루에 관광지 3개씩 무조건 추천 (총 추천 개수는 days * 3)
        input_data["n"] = days * 3

        if redis_client is None:
            raise ValueError("[TouristAgent] 에러 - Redis 연결을 확인해주세요")

        spot_redis_service = SpotRedisService(redis_client)

        try:
            if "member_id" not in input_data or not input_data["member_id"]:
                if session is None:
                    raise ValueError(
                        "[TouristAgent] 에러 - member_id가 필요하며, 세션이 제공되지 않았습니다."
                    )
                email = input_data.get("email")
                if not email:
                    raise ValueError("[TouristAgent] 에러 - email이 필요합니다.")
                provider = "google"
                member_id = await get_memberId_by_email(email, session, provider)
                if not member_id:
                    raise ValueError(
                        "[TouristAgent] 에러 - 인증된 사용자를 찾을 수 없습니다."
                    )
                input_data["member_id"] = member_id

            member_id = input_data["member_id"]

            if not hasattr(self, "agents"):
                logger.error("self.agents is not defined, reinitializing")
                self.initialize()

            self.tasks = self._create_tasks(input_data, prompt)
            logger.info(
                "[TouristAgent] Tasks updated with main_location: %s",
                input_data.get("main_location"),
            )
            logger.info(
                "[TouristAgent] Collector task description: %s",
                self.tasks["collector_task"].description,
            )

            self.tasks["researcher_task"].context = [self.tasks["collector_task"]]
            self.tasks["researcher_detail_task"].context = [
                self.tasks["researcher_task"]
            ]
            self.tasks["reviewer_task"].context = [self.tasks["researcher_detail_task"]]
            self.tasks["decider_task"].context = [self.tasks["reviewer_task"]]

            main_location = input_data["main_location"]
            cached_tourist_lists = await spot_redis_service.get_spots(
                member_id, SpotCategory.SITE, main_location
            )
            input_data["cached_tourist_lists"] = cached_tourist_lists or []

            used_image_urls = set()

            # 새 추천 결과 생성 (저장 여부와 상관없이 동일 로직)
            if not input_data.get("plan_id"):
                if "main_location" not in input_data or not input_data["main_location"]:
                    raise ValueError(
                        "[TouristAgent] 에러 - main_location이 필요합니다."
                    )

                logger.info(
                    "[TouristAgent] Cached tourist lists: %s", cached_tourist_lists
                )

                # 새 추천 결과 생성: 하루에 3개씩 (총 days * 3 개)
                if len(cached_tourist_lists) < days * 3:
                    crew = Crew(
                        agents=list(self.agents.values()),
                        tasks=list(self.tasks.values()),
                        process=Process.sequential,
                        verbose=True,
                    )
                    result = await crew.kickoff_async(inputs=input_data)
                    logger.info(
                        "[TouristAgent] Crew execution completed with result: %s",
                        result,
                    )
                    if result is None:
                        raise ValueError(
                            "[TouristAgent] 에러 - Crew 실행 결과가 None입니다."
                        )
                    if hasattr(result, "tasks_output") and result.tasks_output:
                        final_output = result.tasks_output[-1].raw
                        final_result = json.loads(final_output)
                    else:
                        raise ValueError(
                            "[TouristAgent] 에러 - tasks_output이 비어 있음"
                        )
                    if not isinstance(final_result, list):
                        raise ValueError(
                            "[TouristAgent] 에러 - final_result가 리스트가 아님"
                        )
                else:
                    draft_crew = Crew(
                        agents=[self.agents["decider"]],
                        tasks=[self.tasks["decider_task"]],
                        verbose=True,
                    )
                    result = await draft_crew.kickoff_async(inputs=input_data)
                    if result is None:
                        raise ValueError(
                            "[TouristAgent] 에러 - Draft Crew 실행 결과가 None입니다."
                        )
                    if hasattr(result, "tasks_output") and result.tasks_output:
                        final_output = result.tasks_output[-1].raw
                        final_result = json.loads(final_output)
                    else:
                        raise ValueError(
                            "[TouristAgent] 에러 - tasks_output이 비어 있음"
                        )
                    if not isinstance(final_result, list):
                        raise ValueError(
                            "[TouristAgent] 에러 - final_result가 리스트가 아님"
                        )

                # 리뷰 데이터를 통한 이미지 업데이트
                if hasattr(result, "tasks_output"):
                    for task_output in result.tasks_output:
                        logger.info("Task output: %s", task_output)
                        if "관광지 리뷰 분석가" in str(task_output):
                            review_output = json.loads(task_output.raw)
                            for spot in final_result:
                                for review_spot in review_output:
                                    if spot["kor_name"] == review_spot.get("placeId"):
                                        spot["image_url"] = review_spot.get(
                                            "image_url", spot["image_url"]
                                        )
                                        logger.info(
                                            "Updated image from review for %s: %s",
                                            spot["kor_name"],
                                            spot["image_url"],
                                        )

                # 강제 이미지 업데이트: 두 단계로 이미지 검색 시도
                for spot in final_result:
                    base_query = f"{input_data.get('main_location','')} {spot.get('kor_name','')}"
                    query1 = f"{base_query} 관광 사진"
                    updated_image = await self.get_tourist_info_tool._arun(query1)
                    logger.info(
                        "Initial image search result for %s: %s",
                        spot.get("kor_name"),
                        updated_image,
                    )
                    if (
                        not updated_image
                        or "placeholder" in updated_image
                        or updated_image in used_image_urls
                    ):
                        fallback_query = f"{spot.get('kor_name','')} 대표 이미지"
                        updated_image = await self.get_tourist_info_tool._arun(
                            fallback_query
                        )
                        logger.info(
                            "Fallback image search result for %s: %s",
                            spot.get("kor_name"),
                            updated_image,
                        )
                    if (
                        updated_image
                        and "placeholder" not in updated_image
                        and updated_image not in used_image_urls
                    ):
                        spot["image_url"] = updated_image
                        used_image_urls.add(updated_image)
                        logger.info(
                            "Updated image for %s: %s",
                            spot.get("kor_name"),
                            updated_image,
                        )
                    else:
                        spot["image_url"] = (
                            "https://via.placeholder.com/300x200?text=Image+Not+Found"
                        )
                        logger.warning(
                            "Failed to update image for %s, using default placeholder.",
                            spot.get("kor_name"),
                        )

                # 먼저 새 추천 결과 내에서 중복 제거 (이름 기준)
                unique_final_result = []
                seen_names = set()
                for spot in final_result:
                    name = spot.get("kor_name")
                    if name and name not in seen_names:
                        unique_final_result.append(spot)
                        seen_names.add(name)

                # 캐시된 결과와 새 추천 결과 병합 (이름 기준)
                merged_spots = {}
                for spot in cached_tourist_lists:
                    name = spot.get("kor_name")
                    if name:
                        merged_spots[name] = spot
                for spot in unique_final_result:
                    name = spot.get("kor_name")
                    if name:
                        merged_spots[name] = spot
                merged_list = list(merged_spots.values())

                # 최종 추천: 하루에 3개씩 추천한 결과 중 상위 5개 선택 (예시로 5개 선택)
                final_merged = merged_list[:5]

                # 강제 스팟 카테고리 업데이트: 모든 스팟의 spot_category를 1로 설정
                for spot in final_merged:
                    spot["spot_category"] = 1

                # Redis 저장: 전체 병합된 결과 저장
                if redis_client and member_id is not None:
                    redis_key = str(member_id)
                    processed_result = {
                        "plan": {
                            "name": input_data.get("name", "여행 일정"),
                            "start_date": input_data["start_date"],
                            "end_date": input_data["end_date"],
                            "main_location": input_data.get(
                                "main_location", "Unknown Location"
                            ),
                            "created_at": datetime.now().strftime("%Y-%m-%d"),
                        },
                        "spots": merged_list,
                    }
                    await redis_client.set(
                        redis_key, json.dumps(processed_result), ex=86400
                    )
                    logger.info(
                        "[DEBUG] Redis에 key='%s'로 일정 데이터 저장 완료.", redis_key
                    )
                    saved_value = await redis_client.get(redis_key)
                    logger.info("[DEBUG] Redis에 실제로 저장된 값:\n %s", saved_value)

                final_result_with_time = self._assign_spot_times(
                    final_merged, days, input_data
                )
                return final_result_with_time

            else:
                # 수정(업데이트) 로직: 기존 저장된 계획 수정 시에도 동일하게 중복 제거
                current_plan_id = input_data.get("plan_id")
                if "main_location" not in input_data or not input_data["main_location"]:
                    raise ValueError(
                        "[TouristAgent] 에러 - main_location이 필요합니다."
                    )
                main_location = input_data["main_location"]
                plan_spots_with_info = await get_member_plan_spots(
                    current_plan_id, member_id, session
                )
                if plan_spots_with_info and "detail" in plan_spots_with_info:
                    existing_spot_names = list(
                        set(
                            item["spot"].kor_name
                            for item in plan_spots_with_info["detail"]
                        )
                    )
                    input_data["existing_spot_names"] = existing_spot_names
                    logger.info(
                        "🟡 DB에서 가져온 기존 관광지들: %s", existing_spot_names
                    )
                else:
                    logger.info("🟡 기존 DB 데이터가 없으므로 Redis 캐시를 사용합니다.")
                    cached_tourist_lists = await spot_redis_service.get_spots(
                        member_id, SpotCategory.SITE, main_location
                    )
                    input_data["existing_spot_names"] = cached_tourist_lists or []

                crew = Crew(
                    agents=list(self.agents.values()),
                    tasks=list(self.tasks.values()),
                    process=Process.sequential,
                    verbose=True,
                )
                result = await crew.kickoff_async(inputs=input_data)
                if result is None:
                    raise ValueError(
                        "[TouristAgent] 에러 - Crew 실행 결과가 None입니다."
                    )
                if hasattr(result, "tasks_output") and result.tasks_output:
                    final_output = result.tasks_output[-1].raw
                    final_result = json.loads(final_output)
                else:
                    raise ValueError("[TouristAgent] 에러 - tasks_output이 비어 있음")
                if not isinstance(final_result, list):
                    raise ValueError(
                        "[TouristAgent] 에러 - final_result가 리스트가 아님"
                    )

                # 리뷰를 통한 이미지 업데이트
                if hasattr(result, "tasks_output"):
                    for task_output in result.tasks_output:
                        logger.info("Task output: %s", task_output)
                        if "관광지 리뷰 분석가" in str(task_output):
                            review_output = json.loads(task_output.raw)
                            for spot in final_result:
                                for review_spot in review_output:
                                    if spot["kor_name"] == review_spot.get("placeId"):
                                        spot["image_url"] = review_spot.get(
                                            "image_url", spot["image_url"]
                                        )
                                        logger.info(
                                            "Updated image from review for %s: %s",
                                            spot["kor_name"],
                                            spot["image_url"],
                                        )

                for spot in final_result:
                    if (
                        not spot.get("image_url")
                        or "example.com" in spot.get("image_url")
                        or "placeholder" in spot.get("image_url")
                    ):
                        updated_image = await self.get_tourist_info_tool._arun(
                            spot.get("kor_name", "")
                        )
                        spot["image_url"] = updated_image
                        logger.info(
                            "Fallback updated image for %s: %s",
                            spot.get("kor_name"),
                            updated_image,
                        )

                # 중복 제거 및 스팟 카테고리 업데이트
                unique_final_result = []
                seen_names = set()
                for spot in final_result:
                    name = spot.get("kor_name")
                    if name and name not in seen_names:
                        spot["spot_category"] = 1
                        unique_final_result.append(spot)
                        seen_names.add(name)

                final_result_with_time = self._assign_spot_times(
                    unique_final_result, days, input_data
                )
                return final_result_with_time

        except Exception as e:
            logger.error("[TouristAgent] 에러 - %s", e)
            traceback.print_exc()
            raise e

    def _assign_spot_times(self, spots: list, days: int, input_data: dict) -> list:
        sorted_spots = []
        current_day = 1
        time_slots = ["08:00", "12:00", "18:00"]
        spot_index = 0

        while current_day <= days and spot_index < len(spots):
            for time_slot in time_slots:
                if spot_index >= len(spots):
                    break
                spot = spots[spot_index].copy()
                spot["day"] = current_day
                spot["order"] = time_slots.index(time_slot) + 1
                sorted_spots.append(spot)
                spot_index += 1
            current_day += 1

        while spot_index < len(spots):
            spot = spots[spot_index].copy()
            spot["day"] = days
            spot["order"] = len([s for s in sorted_spots if s["day"] == days]) + 1
            sorted_spots.append(spot)
            spot_index += 1

        return sorted_spots
