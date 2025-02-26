import traceback
import json
from datetime import datetime
from typing import Dict, Optional, List
import aiohttp
from crewai import Agent, Task, Crew, LLM, Process
from sqlmodel.ext.asyncio.session import AsyncSession
from redis.asyncio import Redis
import logging
import os
from dotenv import load_dotenv

from app.repository.members.mebmer_repository import get_memberId_by_email
from app.dtos.site_models import TouristSite, TouristSiteList
from app.utils.calculate_trip_days import calculate_trip_days
from app.utils.time_check import time_token_check


from app.repository.agents.site_plan_spots_repository import (
    get_member_plan_spots,
    get_latest_plan,
)

from app.services.agents.redis.spot_redis import SpotRedisService, SpotCategory

from app.services.agents.tools.site_tool import (
    NaverTouristWebSearchTool,
    NaverTouristImageSearchTool,
    NaverTouristBusinessInfoTool,
    KakaoGeocodeTool,
)

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler('logs/site_agent.log', encoding="utf-8")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

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
        self.get_tourist_business_info_tool = NaverTouristBusinessInfoTool()
        self.get_tourist_description_tool = NaverTouristWebSearchTool()
        self.kakao_tool = KakaoGeocodeTool()
        self.agents = self._create_agents()
        self.tasks = self._create_tasks({})
        logger.info(
            "TouristAgentService initialized with agents: %s", list(self.agents.keys())
        )

    def _create_agents(self) -> Dict[str, Agent]:
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
                role="관광지 웹 검색가",
                goal="관광지에 대한 웹 검색 결과를 활용하여, 관광지의 주요 특징 및 설명을 추출합니다.",
                backstory="최신 웹 검색 결과를 바탕으로 관광지 정보를 간략하게 요약합니다.",
                tools=[self.get_tourist_description_tool],
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
        # companion_count가 리스트인지 확인하고, 아니라면 빈 리스트로 처리
        companion_count = input_data.get("companion_count", [])
        if not isinstance(companion_count, list):
            companion_count = []
        companion_text = (
            ", ".join(
                [
                    f"{c.get('label', '미지정')} {c.get('count', 0)}명"
                    for c in companion_count
                ]
            )
            if companion_count
            else "동반자 정보 없음"
        )

        # existing_spot_names도 리스트인지 확인
        existing_spots = input_data.get("existing_spot_names", [])
        if not isinstance(existing_spots, list):
            existing_spots = []
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
            '  "spot_category": 1,\n'
            '  "phone_number": string or null,\n'
            '  "business_status": boolean or null,\n'
            '  "business_hours": string or null\n'
            "}}"
        )
        return {
            "collector_task": Task(
                description=f"{main_location}의 좌표를 조회해주세요.",
                agent=self.agents["collector"],
                expected_output=f"{main_location}의 좌표",
            ),
            "keyword_extraction_task": Task(
                description=(
                    f"이전 Task에서 얻은 {main_location}의 좌표와 여행 정보를 바탕으로 관광지 검색에 사용할 "
                    f"가장 효과적인 검색 키워드 3개를 생성해주세요:\n"
                    f"# 입력 정보\n지역: {main_location}\n"
                    f"좌표: {{coordinates}}\n"
                    f"여행 기간: {input_data.get('start_date', '')} ~ {input_data.get('end_date', '')}\n"
                    f"연령대: {input_data.get('ages', '연령대 미지정')}\n"
                    f"동반자: {companion_text}\n"
                    f"여행 컨셉: {input_data.get('concepts', '컨셉 미지정')}\n{prompt_text}\n"
                    "규칙: 정확히 3개의 검색 키워드를 생성하고, 반환 형식은 다음과 같습니다:\n"
                    '{{"coordinates": "이전 Task의 좌표", "keywords": ["키워드1", "키워드2", "키워드3"]}}'
                ),
                agent=self.agents["keyword_extraction"],
                expected_output=f"{main_location}의 좌표와 3개의 관광지 검색 키워드",
            ),
            "researcher_task": Task(
                description=(
                    f"기존에 추천된 관광지({existing_spots_text})를 제외하고, {main_location}의 새로운 관광지 기본 정보를 조회하세요.\n"
                    "단, 식당, 숙소, 상점 등 관광지가 아닌 장소는 제외하고, 실제 관광 명소(랜드마크, 공원, 박물관 등)만 포함하세요."
                ),
                agent=self.agents["researcher"],
                expected_output=f"{main_location}의 관광지 기본 정보 리스트",
            ),
            "researcher_detail_task": Task(
                description=(
                    f"{main_location}의 관광지 기본 정보 중 상세 정보가 필요한 항목에 대해, 추가 정보를 조회하세요.\n"
                    "업종, 운영시간, 웹사이트 등의 정보를 포함하고, 불필요한 장소는 제거해주세요."
                ),
                agent=self.agents["researcher_detail"],
                expected_output=f"{main_location}의 관광지 상세 정보 리스트",
            ),
            "reviewer_task": Task(
                description=(
                    f"{main_location} 지역의 관광지에 대한 웹 검색 결과를 활용하여, 관광지의 주요 특징 및 설명을 요약하세요.\n"
                    f"# 입력 정보\n지역: {main_location}\n"
                    "웹 검색 결과에서 관광지에 관한 정보를 종합하여, 관광지의 특징과 설명을 간략하게 요약하고 반환하세요.\n"
                    "반환 형식은 다음과 같습니다:\n"
                    '{{"kor_name": "관광지 이름", "eng_name": null, "address": "주소", "url": null, "image_url": "이미지 URL", "map_url": "지도 URL", "spot_category": 1, "phone_number": null, "business_status": null, "business_hours": null}}'
                ),
                agent=self.agents["reviewer"],
                expected_output=f"{main_location}의 관광지 웹 검색 결과 (JSON array)",
                output_pydantic=TouristSiteList,
            ),
            "decider_task": Task(
                description=(
                    f"{main_location}의 고객 요구사항을 반영한 관광지를 최종 추천합니다.\n"
                    "이전 태스크(reviewer_task)에서 제공된 관광지 데이터를 기반으로, "
                    f"{input_data.get('ages', '연령대 미지정')} 연령대와 동반자({companion_text})의 "
                    f"여행 기간 {input_data.get('start_date', '')} ~ {input_data.get('end_date', '')}에 적합한 관광지를 선정하세요.\n"
                    "만약 이전 태스크의 데이터가 없거나 부족한 경우, "
                    f"{main_location} 내에서 인기 있는 관광지를 추천하세요.\n"
                    "반드시 아래 JSON 스키마에 맞추어 결과를 반환하세요. spot_category는 반드시 1로 설정하세요:\n"
                    + json_schema_prompt
                ),
                agent=self.agents["decider"],
                expected_output=f"{main_location}의 최종 관광지 추천 결과 (JSON array)",
                output_pydantic=TouristSiteList,
            ),
        }

    async def filter_image(self, image_url: str) -> bool:
        if "profile" in image_url or "person" in image_url:
            return False
        return True

    async def update_spot_image(
        self, spot: dict, main_location: str, used_image_urls: set
    ):
        queries = [
            f"{main_location} {spot['kor_name']} 사진",
            f"{spot['kor_name']} 대표 사진",
        ]
        for query in queries:
            image_url = await self.get_tourist_info_tool._arun(query)
            if (
                image_url
                and await self.filter_image(image_url)
                and image_url not in used_image_urls
            ):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.head(
                            image_url, timeout=aiohttp.ClientTimeout(total=5)
                        ) as resp:
                            if resp.status == 200:
                                spot["image_url"] = image_url
                                used_image_urls.add(image_url)
                                logger.info(
                                    f"Updated image for {spot['kor_name']}: {image_url}"
                                )
                                return
                except Exception as e:
                    logger.warning(f"Image URL {image_url} 접근 실패: {e}")
        spot["image_url"] = None
        logger.warning(
            f"Failed to update image for {spot['kor_name']}, setting to None."
        )

    async def update_spot_coordinates(self, spot: dict, main_location: str):
        """관광지의 주소를 기반으로 위도/경도 정보를 업데이트합니다."""
        try:
            address = spot.get("address")
            if not address:
                address = f"{main_location} {spot['kor_name']}"
            coords = await self.kakao_tool.get_coordinates(address)
            spot["latitude"] = coords["latitude"]
            spot["longitude"] = coords["longitude"]
            if spot["latitude"] == 0 and spot["longitude"] == 0:
                coords = await self.kakao_tool.get_coordinates(
                    f"{main_location} {spot['kor_name']}"
                )
                spot["latitude"] = coords["latitude"]
                spot["longitude"] = coords["longitude"]
            logger.info(f"Updated coordinates for {spot['kor_name']}: {coords}")
        except Exception as e:
            logger.error(f"Failed to get coordinates for {spot['kor_name']}: {e}")
            spot["latitude"] = 0
            spot["longitude"] = 0

    async def fetch_additional_spots(
        self,
        main_location: str,
        seen_spots: set,
        required_count: int,
        exclusion_list: List[str],
    ) -> List[dict]:
        query = f"{main_location} 관광지 추천"
        search_result = await self.get_tourist_list_tool._arun(query)
        additional_spots = []
        used_image_urls = set()
        if search_result:
            try:
                lines = search_result.split("\n")
                for i in range(0, len(lines), 3):
                    if i + 2 < len(lines) and "Title:" in lines[i]:
                        title = lines[i].split("Title:")[1].split("Link:")[0].strip()
                        if title in exclusion_list:
                            continue
                        key = (title, f"{main_location} {title}")
                        if key not in seen_spots:
                            spot = {
                                "kor_name": title,
                                "eng_name": None,
                                "address": f"{main_location} {title}",
                                "url": None,
                                "image_url": None,
                                "map_url": f"https://map.naver.com/?query={title}",
                                "spot_category": 1,
                                "phone_number": None,
                                "business_status": True,
                                "business_hours": "09:00 - 18:00",
                            }
                            await self.update_spot_image(
                                spot, main_location, used_image_urls
                            )
                            spot["spot_category"] = 1
                            additional_spots.append(spot)
                            seen_spots.add(key)
                            if len(additional_spots) >= required_count:
                                break
            except Exception as e:
                logger.warning(f"추가 관광지 파싱 실패: {e}")
        return additional_spots

    @time_token_check
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
        if "coordinates" not in input_data or not input_data["coordinates"]:
            main_location = input_data.get("main_location")
            if main_location:
                coords = await self.kakao_tool.get_coordinates(main_location)
                input_data["coordinates"] = (
                    f"{coords['latitude']}° N, {coords['longitude']}° E"
                )
            else:
                input_data["coordinates"] = "37.3942° N, 126.9255° E"
        # concepts가 리스트인지 확인
        concepts = input_data.get("concepts", [])
        if not isinstance(concepts, list):
            concepts = []
        input_data["concepts"] = ", ".join(concepts)
        input_data["prompt"] = input_data.get("prompt", "") or prompt
        days = calculate_trip_days(
            input_data.get("start_date", ""), input_data.get("end_date", "")
        )
        input_data["days"] = days
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
                provider = input_data.get("provider")
                member_id = await get_memberId_by_email(email, session, provider)
                if not member_id:
                    raise ValueError(
                        "[TouristAgent] 에러 - 인증된 사용자를 찾을 수 없습니다."
                    )
                input_data["member_id"] = member_id
            member_id = input_data["member_id"]
            main_location = input_data.get("main_location")
            if not main_location:
                raise ValueError("[TouristAgent] 에러 - main_location이 필요합니다.")
            if not hasattr(self, "agents"):
                logger.error("self.agents is not defined, reinitializing")
                self.initialize()
            self.tasks = self._create_tasks(input_data, prompt)
            logger.info(
                "[TouristAgent] Tasks updated with main_location: %s", main_location
            )
            self.tasks["researcher_task"].context = [self.tasks["collector_task"]]
            self.tasks["researcher_detail_task"].context = [
                self.tasks["researcher_task"]
            ]
            self.tasks["reviewer_task"].context = [self.tasks["researcher_detail_task"]]
            self.tasks["decider_task"].context = [self.tasks["reviewer_task"]]
            cached_tourist_lists = await spot_redis_service.get_spots(
                member_id, SpotCategory.SITE, main_location
            )
            exclusion_list = [
                spot.get("kor_name")
                for spot in cached_tourist_lists
                if spot.get("kor_name")
            ]
            input_data["existing_spot_names"] = exclusion_list
            used_image_urls = set()
            seen_spots = set()
            existing_spots_from_db = []
            if input_data.get("plan_id"):
                plan_spots = await get_member_plan_spots(
                    input_data["plan_id"], member_id, session
                )
                if plan_spots and "detail" in plan_spots:
                    existing_spots_from_db = [
                        {
                            "kor_name": item["spot"].kor_name,
                            "eng_name": item["spot"].eng_name,
                            "address": item["spot"].address,
                            "url": item["spot"].url,
                            "image_url": item["spot"].image_url,
                            "map_url": item["spot"].map_url,
                            "spot_category": 1,
                            "phone_number": item["spot"].phone_number,
                            "business_status": item["spot"].business_status,
                            "business_hours": item["spot"].business_hours,
                        }
                        for item in plan_spots["detail"]
                    ]
                    input_data["existing_spot_names"] = [
                        spot["kor_name"] for spot in existing_spots_from_db
                    ]
                    for spot in existing_spots_from_db:
                        seen_spots.add((spot["kor_name"], spot["address"]))
            if not input_data.get("plan_id"):
                logger.info(
                    "[TouristAgent] Cached tourist lists: %s", cached_tourist_lists
                )
                cached_unique = [
                    spot for spot in cached_tourist_lists if spot.get("kor_name")
                ]
                if len(cached_unique) < days * 3:
                    crew = Crew(
                        agents=list(self.agents.values()),
                        tasks=list(self.tasks.values()),
                        process=Process.sequential,
                        verbose=True,
                    )
                    result = await crew.kickoff_async(inputs=input_data)
                    logger.info(f"----------result.token_usage.__dict__: {result.token_usage.__dict__}")      

                    logger.info(
                        "[TouristAgent] Crew execution completed with result: %s",
                        result,
                    )
                    if (
                        result is None
                        or not hasattr(result, "tasks_output")
                        or not result.tasks_output
                    ):
                        raise ValueError(
                            "[TouristAgent] 에러 - Crew 실행 결과가 비어 있음"
                        )
                    final_output = result.tasks_output[-1].raw
                    try:
                        final_result = json.loads(final_output)
                        if isinstance(final_result, dict) and "spots" in final_result:
                            final_result = final_result["spots"]
                        if not isinstance(final_result, list):
                            raise ValueError(
                                "[TouristAgent] 에러 - final_result가 리스트가 아님"
                            )
                    except json.JSONDecodeError:
                        logger.warning("final_output 파싱 실패, 기본 데이터 사용")
                        final_result = cached_unique
                else:
                    draft_crew = Crew(
                        agents=[self.agents["decider"]],
                        tasks=[self.tasks["decider_task"]],
                        verbose=True,
                    )
                    result = await draft_crew.kickoff_async(inputs=input_data)
                    logger.info(f"----------result.token_usage.__dict__: {result.token_usage.__dict__}")      

                    if (
                        result is None
                        or not hasattr(result, "tasks_output")
                        or not result.tasks_output
                    ):
                        raise ValueError(
                            "[TouristAgent] 에러 - Draft Crew 실행 결과가 비어 있음"
                        )
                    final_output = result.tasks_output[-1].raw
                    try:
                        final_result = json.loads(final_output)
                        if isinstance(final_result, dict) and "spots" in final_result:
                            final_result = final_result["spots"]
                        if not isinstance(final_result, list):
                            raise ValueError(
                                "[TouristAgent] 에러 - final_result가 리스트가 아님"
                            )
                    except json.JSONDecodeError:
                        logger.warning("final_output 파싱 실패, 기본 데이터 사용")
                        final_result = cached_unique
                final_result = [
                    spot
                    for spot in final_result
                    if spot.get("kor_name") not in exclusion_list
                ]
                if hasattr(result, "tasks_output"):
                    for task_output in result.tasks_output:
                        if "관광지 웹 검색가" in str(task_output):
                            try:
                                web_output = json.loads(task_output.raw)
                                for spot in final_result:
                                    full_place_id = (
                                        f"{main_location} {spot['kor_name']}"
                                    )
                                    for web_spot in web_output:
                                        if full_place_id == web_spot.get("placeId"):
                                            spot["image_url"] = web_spot.get(
                                                "image_url", spot["image_url"]
                                            )
                                            spot["description"] = web_spot.get(
                                                "description",
                                                spot.get("description", ""),
                                            )
                            except json.JSONDecodeError:
                                logger.warning("웹 검색 결과 파싱 실패, 데이터 없음")
                unique_final_result = []
                for spot in final_result:
                    key = (spot.get("kor_name"), spot.get("address"))
                    if key not in seen_spots:
                        spot["placeId"] = f"{main_location} {spot['kor_name']}"
                        await self.update_spot_image(
                            spot, main_location, used_image_urls
                        )
                        await self.update_spot_coordinates(spot, main_location)
                        spot["spot_category"] = 1
                        unique_final_result.append(spot)
                        seen_spots.add(key)
                merged_list = unique_final_result
                final_merged = []
                final_seen = set()
                for spot in merged_list:
                    key = (spot.get("kor_name"), spot.get("address"))
                    if key not in final_seen and len(final_merged) < input_data["n"]:
                        spot["spot_category"] = 1
                        final_merged.append(spot)
                        final_seen.add(key)
                if len(final_merged) < input_data["n"]:
                    required_count = input_data["n"] - len(final_merged)
                    logger.warning(
                        f"Only {len(final_merged)} spots found, fetching {required_count} additional spots."
                    )
                    additional_spots = await self.fetch_additional_spots(
                        main_location, final_seen, required_count, exclusion_list
                    )
                    for spot in additional_spots:
                        spot["spot_category"] = 1
                    final_merged.extend(additional_spots)
                if redis_client and member_id:
                    redis_key = str(member_id)
                    processed_result = {
                        "plan": {
                            "name": input_data.get("name", "여행 일정"),
                            "start_date": input_data["start_date"],
                            "end_date": input_data["end_date"],
                            "main_location": main_location,
                            "created_at": datetime.now().strftime("%Y-%m-%d"),
                        },
                        "spots": final_merged,
                    }
                    await redis_client.set(
                        redis_key, json.dumps(processed_result), ex=86400
                    )
                    logger.info("[DEBUG] Redis에 key='%s'로 저장 완료.", redis_key)
                for spot in final_merged:
                    spot["spot_category"] = 1
                final_result_with_time = self._assign_spot_times(
                    final_merged, days, input_data
                )
                for spot in final_result_with_time:
                    spot["spot_category"] = 1
                    
                    
                final_result_dict = {
                    "spots": final_result_with_time,  # 리스트는 여기 저장
                    "token_usage": result.token_usage.__dict__  # token_usage는 별도로 저장
                }
                return final_result_dict    

            else:
                current_plan_id = input_data.get("plan_id")
                if "main_location" not in input_data or not input_data["main_location"]:
                    raise ValueError(
                        "[TouristAgent] 에러 - main_location이 필요합니다."
                    )
                main_location = input_data["main_location"]
                crew = Crew(
                    agents=list(self.agents.values()),
                    tasks=list(self.tasks.values()),
                    process=Process.sequential,
                    verbose=True,
                )
                result = await crew.kickoff_async(inputs=input_data)
                logger.info(f"----------result.token_usage.__dict__: {result.token_usage.__dict__}")      
                
                if (
                    result is None
                    or not hasattr(result, "tasks_output")
                    or not result.tasks_output
                ):
                    raise ValueError("[TouristAgent] 에러 - Crew 실행 결과가 비어 있음")
                final_output = result.tasks_output[-1].raw
                try:
                    final_result = json.loads(final_output)
                    if isinstance(final_result, dict) and "spots" in final_result:
                        final_result = final_result["spots"]
                    if not isinstance(final_result, list):
                        raise ValueError(
                            "[TouristAgent] 에러 - final_result가 리스트가 아님"
                        )
                except json.JSONDecodeError:
                    logger.warning("final_output 파싱 실패, DB 데이터 사용")
                    final_result = existing_spots_from_db
                if hasattr(result, "tasks_output"):
                    for task_output in result.tasks_output:
                        if "관광지 웹 검색가" in str(task_output):
                            try:
                                web_output = json.loads(task_output.raw)
                                for spot in final_result:
                                    full_place_id = (
                                        f"{main_location} {spot['kor_name']}"
                                    )
                                    for web_spot in web_output:
                                        if full_place_id == web_spot.get("placeId"):
                                            spot["image_url"] = web_spot.get(
                                                "image_url", spot["image_url"]
                                            )
                                            spot["description"] = web_spot.get(
                                                "description",
                                                spot.get("description", ""),
                                            )
                            except json.JSONDecodeError:
                                logger.warning("웹 검색 결과 파싱 실패, 데이터 없음")
                unique_final_result = []
                for spot in final_result:
                    key = (spot.get("kor_name"), spot.get("address"))
                    if key not in seen_spots:
                        spot["placeId"] = f"{main_location} {spot['kor_name']}"
                        await self.update_spot_image(
                            spot, main_location, used_image_urls
                        )
                        await self.update_spot_coordinates(spot, main_location)
                        spot["spot_category"] = 1
                        unique_final_result.append(spot)
                        seen_spots.add(key)
                for spot in unique_final_result:
                    spot["spot_category"] = 1
                final_result_with_time = self._assign_spot_times(
                    unique_final_result, days, input_data
                )
                for spot in final_result_with_time:
                    spot["spot_category"] = 1
                    
                final_result_dict = {
                    "spots": final_result_with_time,  # 리스트는 여기 저장
                    "token_usage": result.token_usage.__dict__  # token_usage는 별도로 저장
                }
                return final_result_dict

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
                spot["spot_category"] = 1
                sorted_spots.append(spot)
                spot_index += 1
            current_day += 1
        while spot_index < len(spots):
            spot = spots[spot_index].copy()
            spot["day"] = days
            spot["order"] = len([s for s in sorted_spots if s["day"] == days]) + 1
            spot["spot_category"] = 1
            sorted_spots.append(spot)
            spot_index += 1
        return sorted_spots
