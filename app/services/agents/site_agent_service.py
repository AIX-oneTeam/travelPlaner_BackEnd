import traceback
from crewai import Agent, Task, Crew, LLM, Process
from app.dtos.spot_models import spots_pydantic
from app.utils.calculate_trip_days import calculate_trip_days
from app.services.agents.tools.site_tool import (
    NaverTouristWebSearchTool,
    NaverTouristImageSearchTool,
    NaverTouristReviewTool,
    NaverTouristBusinessInfoTool,
)
from typing import Dict, Optional
import os
from dotenv import load_dotenv
from app.utils.time_check import time_check
from redis.asyncio import Redis
import json

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


async def save_tourist_info(tourist_data_list: dict, redis_client: Redis):
    try:
        ONE_DAY_IN_SECONDS = 86400
        for tourist_data in tourist_data_list.get("spots", []):
            tourist_id = tourist_data["placeId"]
            location = tourist_data["main_location"]
            await redis_client.set(
                f"tourist:{tourist_id}", json.dumps(tourist_data), ex=ONE_DAY_IN_SECONDS
            )
            await redis_client.sadd(f"tag:{location}", tourist_id)
            await redis_client.expire(f"tag:{location}", ONE_DAY_IN_SECONDS)
        return "[TouristAgentService] - save_tourist_info: 성공적으로 저장되었습니다."
    except Exception as e:
        error_details = traceback.format_exc()
        return (
            f"[TouristAgentService] - save_tourist_info : 저장 중 오류 발생: {str(e)}"
        )


async def get_tourists_by_tag(tag: str, redis_client: Redis):
    tourist_ids = await redis_client.smembers(f"tag:{tag}")
    if not tourist_ids:
        return None
    tourists = []
    for tourist_id in tourist_ids:
        tourist_data = await redis_client.get(f"tourist:{tourist_id}")
        if tourist_data:
            tourists.append(json.loads(tourist_data))
    return tourists


class TouristAgentService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TouristAgentService, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
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
        self.tasks = self._create_tasks()

        self.tasks["researcher_task"].context = [self.tasks["collector_task"]]
        self.tasks["researcher_detail_task"].context = [self.tasks["researcher_task"]]
        self.tasks["reviewer_task"].context = [self.tasks["researcher_detail_task"]]
        self.tasks["decider_task"].context = [self.tasks["reviewer_task"]]
        self.draft_crew = Crew(
            agents=[self.agents["decider"]],
            tasks=[self.tasks["decider_task"]],
            verbose=True,
        )
        self.crew = Crew(
            agents=list(self.agents.values()),
            tasks=list(self.tasks.values()),
            process=Process.sequential,
            verbose=True,
        )

    def _create_agents(self) -> Dict[str, Agent]:
        return {
            "collector": Agent(
                role="관광지 리스트 생성 전문가",
                goal="포스팅된 횟수가 많은 관광지부터 내림차순으로 정렬해주세요",
                backstory="포스팅된 횟수가 많은 관광지부터 내림차순으로 정렬해주세요",
                tools=[self.get_tourist_list_tool],
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True,
            ),
            "researcher": Agent(
                role="관광지 기본 정보 수집 및 위치 검증가",
                goal="관광지의 기본 정보를 수집하고 고객의 여행 지역에 위치하지 않은 관광지는 삭제합니다.",
                backstory="블로그에서 관광지의 기본 정보를 수집하고, 고객의 여행 지역에 위치하지 않은 관광지는 삭제해주세요.",
                tools=[self.get_tourist_info_tool],
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True,
            ),
            "researcher_detail": Agent(
                role="관광지 상세 정보 수집 및 업종 검증가",
                goal="관광지의 상세 정보를 수집하고 업종에 관광지 또는 여행지가 포함되지 않은 장소는 삭제합니다.",
                backstory="관광지의 상세 정보를 수집하고, 업종에 관광지 또는 여행지가 포함되지 않은 장소는 삭제해주세요.",
                tools=[self.get_tourist_business_info_tool],
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True,
            ),
            "reviewer": Agent(
                role="관광지 리뷰 분석가",
                goal="관광지의 리뷰를 분석하고, 관광지의 주요 특징을 추출합니다.",
                backstory="관광지의 최신 후기를 읽고, 관광지의 주요 특징을 분석합니다.",
                tools=[self.get_tourist_review_tool],
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True,
            ),
            "decider": Agent(
                role="고객의 요구사항을 반영한 관광지 선정",
                goal="고객의 여행지에서 인기있고, 고객의 선호도를 반영한 관광지를 선정합니다.",
                backstory="고객에게 가장 적합한 관광지를 선별하고 추천해줍니다.",
                allow_delegation=False,
                max_iter=1,
                llm=self.llm,
                verbose=True,
                stop_on_failure=True,
            ),
        }

    def _create_tasks(self) -> Dict[str, Task]:
        return {
            "collector_task": Task(
                description="관광지 리스트를 수집하고 기본 정보를 추출합니다.",
                expected_output="관광지 리스트 (JSON array) with basic info",
                agent=self.agents["collector"],
            ),
            "researcher_task": Task(
                description="수집된 관광지 정보를 위치 및 카테고리 기반으로 필터링합니다.",
                expected_output="필터링된 관광지 리스트 (JSON array)",
                agent=self.agents["researcher"],
            ),
            "researcher_detail_task": Task(
                description="세부 정보를 수집하고 업종 필터링을 통해 관광지를 최종적으로 정리합니다.",
                expected_output="세부 정보가 반영된 관광지 리스트 (JSON array)",
                agent=self.agents["researcher_detail"],
            ),
            "reviewer_task": Task(
                description="관광지 리뷰를 분석하고 특징을 추출하여 추천에 반영합니다.",
                expected_output="관광지 리뷰 분석 결과 (JSON array)",
                agent=self.agents["reviewer"],
            ),
            "decider_task": Task(
                description="고객의 요구에 맞는 관광지를 추천합니다.",
                expected_output="최종 관광지 추천 결과 (JSON array)",
                agent=self.agents["decider"],
            ),
        }

    @time_check
    async def create_tourist_plan(
        self, input_data: dict, redis_client: Redis = None
    ) -> dict:
        if input_data is None:
            raise ValueError("[TouristAgent] 에러 - input_data이 없습니다.")

        input_data["concepts"] = ", ".join(input_data.get("concepts", []))
        input_data["prompt"] = input_data.get("prompt", "")
        days = calculate_trip_days(
            input_data.get("start_date", ""), input_data.get("end_date", "")
        )
        input_data["days"] = days
        input_data["n"] = days * 2

        if redis_client is None:
            raise ValueError("[TouristAgent] 에러 - Redis 연결을 확인해주세요")

        try:
            cached_tourist_lists = (
                await get_tourists_by_tag(input_data["main_location"], redis_client)
                or []
            )
            input_data["cached_tourist_lists"] = cached_tourist_lists
            if len(cached_tourist_lists) < days * 2:
                result = await self.crew.kickoff_async(inputs=input_data)
                reviewer_result = self.tasks[
                    "reviewer_task"
                ].output.pydantic.model_dump()
                await save_tourist_info(reviewer_result, redis_client)
                return result.pydantic.model_dump()
            else:
                result = await self.draft_crew.kickoff_async(inputs=input_data)
                return result.pydantic.model_dump()
        except Exception as e:
            print(f"[TouristAgent] 에러 - {e}")
            raise e
