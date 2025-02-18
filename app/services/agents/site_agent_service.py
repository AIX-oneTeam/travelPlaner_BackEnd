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

from app.utils.time_check import time_check

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")


async def get_kakao_location_info(
    query: str,
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Kakao 키워드 검색 API를 호출하여 주어진 쿼리(예: 관광지 이름 + 메인 지역)로부터
    위도, 경도 및 보정된 주소(address_name)를 반환합니다.
    만약 유효한 정보를 찾지 못하면 (None, None, None)을 반환합니다.
    """
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": query}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            print(f"[Kakao Keyword API 응답] {data}")  # 디버깅 로그
        documents = data.get("documents", [])
        if documents:
            # 첫 번째 결과 사용
            result = documents[0]
            # 도로명 주소가 있으면 우선 사용
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
        print(f"Kakao API 키워드 검색 에러: {e}")
    return None, None, None


from app.services.agents.tools.site_tool import (
    NaverTouristWebSearchTool,
    NaverTouristImageSearchTool,
)


class TouristAgentService:
    """관광지 추천을 위한 Agent 서비스 (CrewAI 활용)"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TouristAgentService, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
        """서비스 초기화"""
        self.llm = LLM(model="gpt-3.5-turbo", temperature=0, api_key=OPENAI_API_KEY)
        self.web_search_tool = NaverTouristWebSearchTool()
        self.image_search_tool = NaverTouristImageSearchTool()
        self.agents = self._create_agents()

    def _process_input(
        self, input_data: dict, prompt: Optional[str] = None
    ) -> Tuple[dict, str]:
        """입력 데이터 전처리"""
        print(f"[입력 데이터] {input_data}")
        print(f"[프롬프트] {prompt}")
        if "concepts" not in input_data or not isinstance(input_data["concepts"], list):
            input_data["concepts"] = []
        prompt_text = f"추가 요청: {prompt}\n" if prompt else ""
        return input_data, prompt_text

    def _create_agents(self) -> Dict[str, Agent]:
        """Agent들을 생성하는 메서드"""
        return {
            "tourist_search": Agent(
                role="관광지 추천 전문가",
                goal="사용자에게 제공된 여행 정보를 바탕으로 관광지 추천을 진행한다.",
                backstory="나는 최신 관광 정보를 알고 있는 전문가이다.",
                tools=[self.web_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
            "image_update": Agent(
                role="관광지 이미지 검색 전문가",
                goal=(
                    "추천된 관광지 리스트의 각 항목에 대해 'kor_name'을 사용하여 최신 이미지를 검색하고, "
                    "각 항목의 image_url을 업데이트한다."
                ),
                backstory="나는 네이버 이미지 검색 API를 통해 관광지의 대표 이미지를 제공하는 전문가이다.",
                tools=[self.image_search_tool],
                llm=self.llm,
                verbose=True,
                async_execution=True,
            ),
        }

    def _create_tasks(self, input_data: dict, prompt_text: str) -> List[Task]:
        """Task들을 생성하는 메서드"""
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
            f"'{input_data['main_location']}' 지역의 관광지 추천을 위해 아래 요구사항을 충족하는 관광지를 최소 10곳 추천하라.\n"
            "요구사항:\n"
            f"- 여행 기간: {input_data['start_date']}부터 {input_data['end_date']}까지\n"
            f"- 연령대: {input_data['ages']}\n"
            f"- 동반자 수: {input_data['companion_count']}\n"
            f"- 여행 컨셉: {', '.join(input_data['concepts'])}\n"
            f"{prompt_text}\n"
            "각 관광지는 반드시 아래 JSON 객체 형식을 준수할 것:\n"
            f"{json_schema_prompt}\n"
            "주의: 결과는 반드시 순수한 JSON 배열 형식(예: [ {...}, {...}, ... ])로 반환하고, 다른 텍스트는 포함하지 말라."
        )
        task1 = Task(
            description=task1_description,
            agent=self.agents["tourist_search"],
            expected_output="관광지 추천 결과 (JSON 배열)",
        )
        task2 = Task(
            description=(
                "추천된 관광지 리스트의 각 항목에 대해 'kor_name'을 사용하여 최신 이미지를 검색하고, "
                "각 항목의 image_url 필드를 업데이트하라."
            ),
            agent=self.agents["image_update"],
            expected_output="관광지 이미지 업데이트 결과 (JSON 배열)",
            output_pydantic=spots_pydantic,
        )
        return [task1, task2]

    @time_check
    async def create_tourist_plan(
        self, input_data: dict, prompt: Optional[str] = None
    ) -> dict:
        """관광지 추천 워크플로우 실행"""
        try:
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
        결과 후처리: Crew의 마지막 태스크 결과를 pydantic 모델로 변환하고,
        네이버 API의 부정확한 주소 대신, 관광지 이름과 메인 지역을 결합한 쿼리로
        Kakao API의 키워드 검색을 통해 보정된 주소, 위도, 경도 정보를 조회하여 지도 URL을 업데이트한다.
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

        # 여행 기간에 따른 총 일수 계산 (예: 1박 2일이면 총 2일)
        try:
            start_date = datetime.strptime(input_data.get("start_date", ""), "%Y-%m-%d")
            end_date = datetime.strptime(input_data.get("end_date", ""), "%Y-%m-%d")
            total_days = (end_date - start_date).days + 1
            if total_days < 1:
                total_days = 1
        except Exception:
            total_days = 1

        for idx, spot in enumerate(spots_data.get("spots", [])):
            # 관광지 이름과 메인 지역을 결합한 쿼리 생성
            query = f"{spot.get('kor_name', '')} {input_data.get('main_location', '')}"
            new_lat, new_lon, new_address = await get_kakao_location_info(query)
            spot["latitude"] = new_lat
            spot["longitude"] = new_lon
            # 보정된 주소가 있으면 업데이트, 없으면 원래 주소 유지
            if new_address:
                spot["address"] = new_address
            # 유효한 좌표가 있으면 Kakao 지도 링크 생성
            if (
                new_lat is not None
                and new_lon is not None
                and new_lat != 0.0
                and new_lon != 0.0
            ):
                spot["map_url"] = (
                    f"https://map.kakao.com/link/map/{spot.get('kor_name', '')},{new_lat},{new_lon}"
                )
            # 동적 day_x 할당 (여행 기간 내에서 순환)c
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
            "message": "관광지 추천이 성공적으로 처리되었습니다.",
            "plan": plan_info,
            "spots": spots_data.get("spots", []),
        }
