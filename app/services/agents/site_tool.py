import json
import re
import httpx
import asyncio
from dotenv import load_dotenv
from crewai.tools import BaseTool
from typing import List
import os

load_dotenv()

# 네이버 API 관련 환경변수
AGENT_NAVER_CLIENT_ID = os.getenv("AGENT_NAVER_CLIENT_ID")
AGENT_NAVER_CLIENT_SECRET = os.getenv("AGENT_NAVER_CLIENT_SECRET")

# 카카오 API 키 (카카오 지도 API에 사용 중인 REST API 키)
KAKAO_MAP_API_KEY = os.getenv("KAKAO_MAP_API_KEY")


async def check_url_openable_async(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.head(url, follow_redirects=True)
            return 200 <= response.status_code < 400
    except Exception:
        return False


def relevance_score(item_title: str, keywords: List[str]) -> int:
    title_clean = re.sub(r"<.*?>", "", item_title)
    score = 0
    for kw in keywords:
        if kw in title_clean:
            score += 1
    return score


class NaverWebSearchTool(BaseTool):
    name: str = "NaverWebSearch"
    description: str = "네이버 웹 검색 API를 사용해 관광지에 맞는 정보를 검색"

    async def _arun(self, query: str) -> str:
        if not AGENT_NAVER_CLIENT_ID or not AGENT_NAVER_CLIENT_SECRET:
            return "[NaverWebSearchTool] 네이버 API 자격 증명이 없습니다."
        url = "https://openapi.naver.com/v1/search/webkr.json"
        headers = {
            "X-Naver-Client-Id": AGENT_NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": AGENT_NAVER_CLIENT_SECRET,
        }
        params = {"query": query, "display": 3, "start": 1, "sort": "sim"}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
            items = data.get("items", [])
            if not items:
                return f"[NaverWebSearchTool] '{query}' 검색 결과 없음."
            results = []
            for item in items:
                title = item.get("title", "")
                link = item.get("link", "")
                desc = item.get("description", "")
                results.append(f"제목: {title}\n링크: {link}\n설명: {desc}\n")
            return "\n".join(results)
        except Exception as e:
            return f"[NaverWebSearchTool] 에러: {str(e)}"

    def _run(self, query: str) -> str:
        return asyncio.run(self._arun(query))


class NaverImageSearchTool(BaseTool):
    name: str = "NaverImageSearch"
    description: str = "네이버 이미지 검색 API를 사용해 관광지에 맞는 이미지 URL을 검색"

    async def _arun(self, query: str) -> str:
        if not query.strip():
            return ""
        if not AGENT_NAVER_CLIENT_ID or not AGENT_NAVER_CLIENT_SECRET:
            return "[NaverImageSearchTool] 네이버 API 자격 증명이 없습니다."
        url = "https://openapi.naver.com/v1/search/image"
        headers = {
            "X-Naver-Client-Id": AGENT_NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": AGENT_NAVER_CLIENT_SECRET,
        }
        params = {
            "query": query,
            "display": 10,
            "start": 1,
            "sort": "sim",
            "filter": "all",
        }
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
            items = data.get("items", [])
            if not items:
                return ""
            keywords = query.split()
            items_sorted = sorted(
                items,
                key=lambda item: relevance_score(item.get("title", ""), keywords),
                reverse=True,
            )
            valid_items = []
            for item in items_sorted:
                link = item.get("link")
                if link and "wikimedia.org" in link:
                    continue
                if link and await check_url_openable_async(link):
                    valid_items.append(item)
            if not valid_items:
                return ""
            return valid_items[0].get("link", "")
        except Exception as e:
            return f"[NaverImageSearchTool] 에러: {str(e)}"

    def _run(self, query: str) -> str:
        return asyncio.run(self._arun(query))


def extract_json_from_text(text: str) -> str:
    try:
        match = re.search(r"\[.*?\]", text, re.DOTALL)
        if match:
            return match.group(0)
    except Exception as e:
        print(f"JSON 추출 오류: {e}")
    return text


def extract_recommendations_from_output(output) -> list:
    try:
        if not isinstance(output, (str, bytes, bytearray)):
            output = str(output)
        json_str = extract_json_from_text(output)
        recommendations = json.loads(json_str)
        if isinstance(recommendations, list):
            return recommendations
        return []
    except Exception as e:
        print(f"파싱 오류: {e}")
        return []


async def get_image_url_for_place(query: str) -> str:
    modified_query = f"{query} 관광지"
    tool = NaverImageSearchTool()
    return await tool._arun(modified_query)


async def add_images_to_recommendations(recommendations: list) -> list:
    tasks = []
    for place in recommendations:
        query = place.get("kor_name", "").strip() or place.get("address", "").strip()
        tasks.append(asyncio.create_task(get_image_url_for_place(query)))
    image_urls = await asyncio.gather(*tasks, return_exceptions=True)
    for place, image_url in zip(recommendations, image_urls):
        if isinstance(image_url, Exception):
            place["image_url"] = ""
        else:
            place["image_url"] = image_url
    return recommendations


# ---- 카카오 API를 이용한 주소 기반 위도/경도 변환 함수 ----
async def get_lat_lon_for_place_kakao(address: str) -> (float, float):
    """
    카카오 주소-좌표 변환 API를 호출하여 주어진 주소의 위도와 경도를 반환합니다.
    API 문서: https://apis.map.kakao.com/web/guide/#addressCoord
    """
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_MAP_API_KEY}"}
    params = {"query": address}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        documents = data.get("documents", [])
        if documents:
            # 첫 번째 결과의 좌표 정보를 사용 (경도: x, 위도: y)
            x = float(documents[0]["address"].get("x", 0.0))
            y = float(documents[0]["address"].get("y", 0.0))
            return y, x  # (위도, 경도)
    except Exception as e:
        print(f"카카오 API 위도/경도 조회 에러: {e}")
    return 0.0, 0.0
