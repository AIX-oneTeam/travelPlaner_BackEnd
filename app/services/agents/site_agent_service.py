import os
import traceback
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import httpx
from crewai import Agent, Task, Crew, LLM
from fastapi import HTTPException
from app.dtos.spot_models import spots_pydantic
from dotenv import load_dotenv


load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")


async def get_kakao_location_info(
    query: str,
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Calls the Kakao Keyword Search API with the given query (e.g., tourist spot name + main location)
    and returns the latitude, longitude, and corrected address (address_name).
    If valid information is not found, returns (None, None, None).
    """
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": query}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            print(f"[Kakao Keyword API Response] {data}")  # Debug log
        documents = data.get("documents", [])
        if documents:
            # Use the first result
            result = documents[0]
            # Prefer the road address if available
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
        print(f"Kakao API Keyword Search Error: {e}")
    return None, None, None


# Import tool classes (assuming these are defined elsewhere and remain unchanged)
from app.services.agents.tools.site_tool import (
    NaverTouristWebSearchTool,
    NaverTouristImageSearchTool,
)


class TouristAgentService:
    """Tourist recommendation service using CrewAI agents"""

    _instance = None

    def __new__(cls):
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
        """Preprocess input data"""
        print(f"[Input Data] {input_data}")
        print(f"[Prompt] {prompt}")
        if "concepts" not in input_data or not isinstance(input_data["concepts"], list):
            input_data["concepts"] = []
        # The prompt text is now in English
        prompt_text = f"Additional instructions: {prompt}\n" if prompt else ""
        return input_data, prompt_text

    def _create_agents(self) -> Dict[str, Agent]:
        """Create agents with instructions in English."""
        return {
            "tourist_search": Agent(
                role="Tourist Recommendation Expert",
                goal="Recommend tourist spots based on the provided travel information.",
                backstory="I have up-to-date knowledge about popular tourist destinations.",
                tools=[self.web_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            "image_update": Agent(
                role="Image Search Specialist",
                goal=(
                    "For each recommended tourist spot, use its 'kor_name' to fetch the latest image and update the 'image_url' field."
                ),
                backstory="I provide representative images for tourist spots using the Naver Image Search API.",
                tools=[self.image_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
        }

    def _create_tasks(self, input_data: dict, prompt_text: str) -> List[Task]:
        """Create tasks for the agents."""
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
            "Note: The result must be a pure JSON array (e.g., [ {...}, {...}, ... ]) without any extra text."
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

    async def create_tourist_plan(
        self, input_data: dict, prompt: Optional[str] = None
    ) -> dict:
        """Execute the tourist recommendation workflow using the original Korean prompt."""
        try:
            # No translation: directly use the Korean prompt
            processed_input, prompt_text = self._process_input(input_data, prompt)
            tasks = self._create_tasks(processed_input, prompt_text)
            crew = Crew(tasks=tasks, agents=list(self.agents.values()), verbose=True)
            result = await crew.kickoff_async()
            return await self._process_result(result, processed_input)
        except Exception as e:
            traceback.print_exc()
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
            print("Error processing result:", e)
            spots_data = {"spots": []}

        # Calculate the total number of travel days (e.g., 1 night 2 days means 2 days)
        try:
            start_date = datetime.strptime(input_data.get("start_date", ""), "%Y-%m-%d")
            end_date = datetime.strptime(input_data.get("end_date", ""), "%Y-%m-%d")
            total_days = (end_date - start_date).days + 1
            if total_days < 1:
                total_days = 1
        except Exception:
            total_days = 1

        for idx, spot in enumerate(spots_data.get("spots", [])):
            # Create a combined query using the tourist spot name and main location
            query = f"{spot.get('kor_name', '')} {input_data.get('main_location', '')}"
            new_lat, new_lon, new_address = await get_kakao_location_info(query)
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
            # Assign day_x dynamically over the travel period
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
