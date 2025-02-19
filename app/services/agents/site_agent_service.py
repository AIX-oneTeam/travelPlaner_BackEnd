import os
import json
import asyncio
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import aiohttp
import logging
import threading
from crewai import Agent, Task, Crew, LLM
from fastapi import HTTPException
from app.dtos.spot_models import spots_pydantic
from dotenv import load_dotenv
from app.utils.time_check import time_check

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")


REDIS_URL = os.getenv("REDIS_URL")

# Redis 연결
r = redis.from_url(REDIS_URL, decode_responses=True)

# 테스트
r.set("test", "value")
print(r.get("test"))


async def get_kakao_location_info(
    query: str,
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Calls the Kakao Keyword Search API with the given query and returns the latitude, longitude, and corrected address.
    If valid information is not found, returns (None, None, None).
    """
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": query}
    try:
        async with aiohttp.ClientSession() as client:
            async with client.get(url, headers=headers, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()
                logger.info(f"[Kakao Keyword API Response] {data}")
        documents = data.get("documents", [])
        if documents:
            result = documents[0]
            if result.get("road_address"):
                address_name = result["road_address"].get("address_name")
                x = float(result["road_address"].get("x", 0.0))
                y = float(result["road_address"].get("y", 0.0))
            else:
                address_name = result.get("address_name")
                x = float(result.get("x", 0.0))
                y = float(result.get("y", 0.0))
            return y, x, address_name
    except Exception as e:
        logger.error(f"Kakao API Keyword Search Error: {e}")
    return None, None, None


# Import tool classes from site_tool module
from app.services.agents.tools.site_tool import (
    NaverTouristWebSearchTool,
    NaverTouristImageSearchTool,
)


class TouristAgentService:
    """Tourist recommendation service using CrewAI agents"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TouristAgentService, cls).__new__(cls)
                cls._instance.initialize()
        return cls._instance

    def initialize(self):
        """Initialize the service"""
        self.llm = LLM(model="gpt-4o-mini", temperature=0, api_key=OPENAI_API_KEY)
        self.web_search_tool = NaverTouristWebSearchTool()
        self.image_search_tool = NaverTouristImageSearchTool()
        self.agents = self._create_agents()

    def _process_input(
        self, input_data: dict, prompt: Optional[str] = None
    ) -> Tuple[dict, str]:
        logger.info(f"[Input Data] {input_data}")
        logger.info(f"[Prompt] {prompt}")

<<<<<<< HEAD
        plan_id = input_data.get("plan_id")
        if not plan_id:
            raise HTTPException(status_code=400, detail="plan_id must be provided")

        # Redis에서 기존 추천 장소 확인
        existing_spots = r.smembers(f"plan:{plan_id}:recommended_spots")
        if existing_spots:
            # Redis에서 가져온 값은 set이므로 list로 변환하여 사용
            existing_spots = {spot.decode("utf-8") for spot in existing_spots}
            logger.info(f"[Existing spots in plan {plan_id}]: {existing_spots}")
        else:
            existing_spots = []
=======
        if not input_data.get("main_location"):
            raise HTTPException(
                status_code=400, detail="main_location must be provided"
            )
>>>>>>> dev

        if "concepts" not in input_data or not isinstance(input_data["concepts"], list):
            input_data["concepts"] = []

        main_location_text = f"Location: {input_data.get('main_location')}. "

<<<<<<< HEAD
        exclusion_text = (
            f"Please exclude these spots: {', '.join(existing_spots)}. "
            if existing_spots
            else ""
        )

        prompt_text = (
            f"{main_location_text}{exclusion_text}{prompt} "
            if prompt
            else f"{main_location_text}{exclusion_text}"
        )
=======
        exclusion_text = ""
        existing_spots = input_data.get("existing_spots", [])
        if existing_spots:
            existing_names = ", ".join(
                [spot.get("kor_name", "") for spot in existing_spots]
            )
            exclusion_text = (
                f"Previously recommended tourist spots: ({existing_names}). "
                "Please strictly exclude these and recommend 5 new tourist spots. "
            )

        if prompt:
            prompt_text = f"Additional instructions: {main_location_text}{exclusion_text}{prompt}\n"
        else:
            prompt_text = (
                f"Additional instructions: {main_location_text}{exclusion_text}\n"
            )
>>>>>>> dev

        return input_data, prompt_text

    def _create_agents(self) -> Dict[str, Agent]:
        """Create agents with instructions in English."""
        return {
            "tourist_search": Agent(
                role="Tourist Recommendation Expert",
<<<<<<< HEAD
                goal="Recommend at least 5 tourist spots based on the provided travel information.",
=======
                goal="Recommend tourist spots based on the provided travel information.",
>>>>>>> dev
                backstory="I have up-to-date knowledge about popular tourist destinations.",
                tools=[self.web_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            "image_update": Agent(
                role="Image Search Specialist",
                goal="For each recommended tourist spot, use its 'kor_name' to fetch the latest image and update the 'image_url' field.",
                backstory="I provide representative images for tourist spots using the Naver Image Search API.",
                tools=[self.image_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
        }

    def _create_tasks(self, input_data: dict, prompt_text: str) -> List[Task]:
        json_schema_prompt = (
            "{\n"
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
            "}"
        )

        task1_description = (
            f"Recommend at least 5 tourist spots in the area of '{input_data['main_location']}' that satisfy the following requirements:\n"
            "Requirements:\n"
            f"- Travel period: from {input_data['start_date']} to {input_data['end_date']}\n"
            f"- Age group: {input_data['ages']}\n"
            f"- Number of companions: {input_data['companion_count']}\n"
            f"- Travel concepts: {', '.join(input_data['concepts'])}\n"
            f"{prompt_text}\n"
            "Each tourist spot must strictly follow the following JSON object format:\n"
            f"{json_schema_prompt}\n"
            "Note: The result must be a pure JSON array (e.g., [ {{...}}, {{...}}, ... ]) without any extra text."
        )
        task1 = Task(
            description=task1_description,
            agent=self.agents["tourist_search"],
            expected_output="Tourist recommendation results (JSON array)",
        )

        task2 = Task(
            description=(
                "For each recommended tourist spot, use its 'kor_name' to search for the latest image, "
                "and update the 'image_url' field accordingly."
            ),
            agent=self.agents["image_update"],
            expected_output="Tourist image update results (JSON array)",
            output_pydantic=spots_pydantic,
        )

        return [task1, task2]

    @time_check
    async def create_tourist_plan(
        self, input_data: dict, prompt: Optional[str] = None
    ) -> dict:
        """
        Execute the tourist recommendation workflow using the original English prompt.
        """
        try:
            processed_input, prompt_text = self._process_input(input_data, prompt)
            tasks = self._create_tasks(processed_input, prompt_text)
            crew = Crew(tasks=tasks, agents=list(self.agents.values()), verbose=True)
            result = await crew.kickoff_async()
            return await self._process_result(result, processed_input)
        except Exception as e:
            logger.exception("Error creating tourist plan")
            raise HTTPException(status_code=500, detail=str(e))

    async def _process_result(self, result, input_data: dict) -> dict:
        """
        Post-process the result: convert the final task result using the Pydantic model,
        and update the map URL using Kakao API based on a combined query of the tourist spot name and main location.
        """
        try:
            if hasattr(result, "tasks_output") and result.tasks_output:
                final_task_output = result.tasks_output[-1]
                if (
                    hasattr(final_task_output, "pydantic")
                    and final_task_output.pydantic
                ):
                    spots_data = final_task_output.pydantic.model_dump()
                elif hasattr(final_task_output, "raw") and final_task_output.raw:
                    spots_data = json.loads(final_task_output.raw)
                else:
                    spots_data = {"spots": []}
            else:
                spots_data = {"spots": []}
        except Exception as e:
            logger.error("Error processing result: %s", e)
            spots_data = {"spots": []}

<<<<<<< HEAD
        # Deduplication logic (inclusion of new spots only)
=======
        # Deduplication logic
>>>>>>> dev
        existing_spot_names = [
            spot.get("kor_name", "") for spot in input_data.get("existing_spots", [])
        ]
        unique_spots = [
            spot
            for spot in spots_data.get("spots", [])
            if spot.get("kor_name", "") not in existing_spot_names
        ]
        spots_data["spots"] = unique_spots
<<<<<<< HEAD

        # Continue with processing (map, Kakao info, etc.)
        return spots_data
=======

        # Calculate total days from start_date to end_date
        try:
            start_date = datetime.strptime(input_data.get("start_date", ""), "%Y-%m-%d")
            end_date = datetime.strptime(input_data.get("end_date", ""), "%Y-%m-%d")
            total_days = (end_date - start_date).days + 1
            if total_days < 1:
                total_days = 1
        except Exception:
            total_days = 1

        # Update each spot with Kakao map info and day_x in parallel using asyncio.gather
        spots = spots_data.get("spots", [])
        queries = [
            f"{spot.get('kor_name', '')} {input_data.get('main_location', '')}"
            for spot in spots
        ]
        kakao_results = await asyncio.gather(
            *(get_kakao_location_info(query) for query in queries)
        )
        for idx, (spot, (new_lat, new_lon, new_address)) in enumerate(
            zip(spots, kakao_results)
        ):
            spot["latitude"] = new_lat
            spot["longitude"] = new_lon
            if new_address:
                spot["address"] = new_address
            if (
                new_lat is not None
                and new_lon is not None
                and new_lat != 0.0
                and new_lon != 0.0
            ):
                spot["map_url"] = (
                    f"https://map.kakao.com/link/map/{spot.get('kor_name', '')},{new_lat},{new_lon}"
                )
            if not spot.get("day_x") or spot.get("day_x") == 0:
                spot["day_x"] = (idx % total_days) + 1

        plan_info = {
            "main_location": input_data.get("main_location", ""),
            "start_date": input_data.get("start_date", ""),
            "end_date": input_data.get("end_date", ""),
            "ages": input_data.get("ages", ""),
            "companion_count": (
                sum(
                    companion.get("count", 0)
                    for companion in input_data.get("companion_count", [])
                )
                if isinstance(input_data.get("companion_count"), list)
                else 0
            ),
            "concepts": ", ".join(input_data.get("concepts", [])),
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "updated_at": datetime.now().strftime("%Y-%m-%d"),
        }
        return {
            "message": "Tourist recommendations processed successfully.",
            "plan": plan_info,
            "spots": spots_data.get("spots", []),
        }
>>>>>>> dev
