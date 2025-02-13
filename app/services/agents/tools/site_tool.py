import asyncio
import aiohttp
from crewai.tools import BaseTool
from typing import Dict
from dotenv import load_dotenv
import os
import re
import httpx
from typing import Union

# 환경 변수 로드
load_dotenv()
AGENT_NAVER_CLIENT_ID = os.getenv("AGENT_NAVER_CLIENT_ID")
AGENT_NAVER_CLIENT_SECRET = os.getenv("AGENT_NAVER_CLIENT_SECRET")


def clean_query(query: str) -> str:
    """
    입력 문자열을 정리하여 반환합니다.
    1. 파이프(|) 이후의 내용을 제거
    2. 괄호와 괄호 안의 내용을 제거
    3. 한글, 영어, 숫자, 공백, 하이픈(-)만 남기고 나머지 문자 제거
    4. 앞뒤 공백 제거
    """
    clean_lines = []
    for line in query.splitlines():
        line = line.split("|")[0]
        line = re.sub(r"\([^)]*\)", "", line)
        line = re.sub(r"[^\uAC00-\uD7A3a-zA-Z0-9\s\-]", "", line)
        line = line.strip()
        if line:
            clean_lines.append(line)
    return " ".join(clean_lines)


async def check_url_openable_async(url: str) -> bool:
    """
    주어진 URL에 대해 HEAD 요청을 보내어 접근 가능한지 확인합니다.
    HTTP 상태 코드가 200 이상 400 미만이면 접근 가능(True)로 간주합니다.
    """
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.head(url, follow_redirects=True)
            return 200 <= response.status_code < 400
    except Exception as e:
        print(f"Error checking URL '{url}': {e}")
        return False


class NaverTouristWebSearchTool(BaseTool):
    """
    네이버 웹 검색 API를 사용해 관광지 관련 정보를 검색하는 도구입니다.
    """

    name: str = "NaverTouristWebSearchTool"
    description: str = "네이버 웹 검색 API를 사용해 관광지 관련 정보를 검색합니다."

    async def _arun(self, query: str) -> str:
        if not AGENT_NAVER_CLIENT_ID or not AGENT_NAVER_CLIENT_SECRET:
            return "[NaverTouristWebSearchTool] 네이버 API 자격 증명이 없습니다."

        url = "https://openapi.naver.com/v1/search/webkr.json"
        headers = {
            "X-Naver-Client-Id": AGENT_NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": AGENT_NAVER_CLIENT_SECRET,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://search.naver.com/",
        }
        query = clean_query(query)
        print(f"[관광지 웹 검색어]: {query}")
        params = {"query": query, "display": 3, "start": 1, "sort": "sim"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    data = await response.json()
                    items = data.get("items", [])
                    if not items:
                        return ""
                    results = []
                    for item in items:
                        # HTML 태그 제거
                        title = re.sub(r"<.*?>", "", item.get("title", ""))
                        link = item.get("link", "")
                        description = item.get("description", "")
                        results.append(
                            f"제목: {title}\n링크: {link}\n설명: {description}"
                        )
                    return "\n".join(results)
        except Exception as e:
            print(f"관광지 웹 검색 오류: {e}")
            return ""

    def _run(self, query: str) -> str:
        return asyncio.run(self._arun(query))


class NaverTouristImageSearchTool(BaseTool):
    """
    네이버 이미지 검색 API를 사용해 관광지의 대표 이미지를 검색하는 도구입니다.
    """

    name: str = "NaverTouristImageSearchTool"
    description: str = (
        "네이버 이미지 검색 API를 사용해 관광지의 대표 이미지를 검색합니다."
    )

    async def _arun(self, query: Union[str, dict]) -> str:

        if isinstance(query, dict):
            query = query.get("description", "")
        if not query.strip():
            return ""
        if not AGENT_NAVER_CLIENT_ID or not AGENT_NAVER_CLIENT_SECRET:
            return "[NaverTouristImageSearchTool] 네이버 API 자격 증명이 없습니다."

        url = "https://openapi.naver.com/v1/search/image"
        headers = {
            "X-Naver-Client-Id": AGENT_NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": AGENT_NAVER_CLIENT_SECRET,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://search.naver.com/",
        }
        query = clean_query(query)
        print(f"[관광지 이미지 검색어]: {query}")
        params = {
            "query": query,
            "display": 5,
            "sort": "sim",
            "filter": "all",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    data = await response.json()
                    items = data.get("items", [])
                    if not items:
                        return "https://via.placeholder.com/300x200?text=No+Image"
                    for item in items:
                        img_url = item.get("link", "")
                        if await check_url_openable_async(img_url):
                            return img_url
                    return "https://via.placeholder.com/300x200?text=No+Image"
        except Exception as e:
            print(f"관광지 이미지 검색 오류: {e}")
            return "https://via.placeholder.com/300x200?text=Error"

    def _run(self, query: Union[str, dict]) -> str:
        return asyncio.run(self._arun(query))
