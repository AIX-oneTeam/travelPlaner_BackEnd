# site_tool.py
import asyncio
import httpx
import re
from crewai.tools import BaseTool
from dotenv import load_dotenv
import os

load_dotenv()

# 네이버 API 관련 환경변수
AGENT_NAVER_CLIENT_ID = os.getenv("AGENT_NAVER_CLIENT_ID")
AGENT_NAVER_CLIENT_SECRET = os.getenv("AGENT_NAVER_CLIENT_SECRET")


async def check_url_openable_async(url: str) -> bool:
    """
    주어진 URL에 대해 HEAD 요청을 보내어 접근 가능한지 확인합니다.
    HTTP 상태 코드가 200 이상 400 미만이면 True를 반환합니다.
    """
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.head(url, follow_redirects=True)
            return 200 <= response.status_code < 400
    except Exception:
        return False


class NaverWebSearchTool(BaseTool):
    name: str = "NaverWebSearchTool"
    description: str = "네이버 웹 검색 API를 사용해 관광지 추천 정보를 검색합니다."

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
                return ""
            results = []
            for item in items:
                # HTML 태그 제거
                title = re.sub(r"<.*?>", "", item.get("title", ""))
                link = item.get("link", "")
                description = item.get("description", "")
                results.append(f"제목: {title}\n링크: {link}\n설명: {description}")
            return "\n".join(results)
        except Exception as e:
            return f"[NaverWebSearchTool] 에러: {str(e)}"

    def _run(self, query: str) -> str:
        return asyncio.run(self._arun(query))


class NaverImageSearchTool(BaseTool):
    name: str = "NaverImageSearchTool"
    description: str = (
        "네이버 이미지 검색 API를 사용해 관광지의 대표 이미지를 검색합니다."
    )

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
            "display": 5,
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
                return "https://via.placeholder.com/300x200?text=No+Image"
            for item in items:
                img_url = item.get("link", "")
                if await check_url_openable_async(img_url):
                    return img_url
            return "https://via.placeholder.com/300x200?text=No+Image"
        except Exception as e:
            return f"[NaverImageSearchTool] 에러: {str(e)}"

    def _run(self, query: str) -> str:
        return asyncio.run(self._arun(query))
