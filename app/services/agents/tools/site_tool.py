import asyncio
import aiohttp
import httpx
import os
import re
import json
import logging
from crewai.tools import BaseTool
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import emoji
from typing import List, Dict, Optional, Union

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
AGENT_NAVER_CLIENT_ID = os.getenv("AGENT_NAVER_CLIENT_ID")
AGENT_NAVER_CLIENT_SECRET = os.getenv("AGENT_NAVER_CLIENT_SECRET")


def clean_query(query: str) -> str:
    """
    Cleans the input string by:
    1. Removing content after a pipe (|).
    2. Removing parentheses and the text within.
    3. Retaining only Korean, English, digits, whitespace, hyphens (-), commas, and periods.
    4. Trimming leading and trailing whitespace.
    """
    clean_lines = []
    for line in query.splitlines():
        line = line.split("|")[0]
        line = re.sub(r"\(.*?\)", "", line)
        line = re.sub(r"[^\uAC00-\uD7A3a-zA-Z0-9\s\-,.]", "", line)
        line = line.strip()
        if line:
            clean_lines.append(line)
    return " ".join(clean_lines)


async def check_url_openable_async(url: str) -> bool:
    """
    Sends a HEAD request using aiohttp to verify the URL's accessibility.
    Returns True if the status code is between 200 and 399.
    """
    if not url:
        return False
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        ) as session:
            async with session.head(url, allow_redirects=True) as response:
                return 200 <= response.status < 400
    except Exception as e:
        logger.error(f"Error checking URL '{url}': {e}")
        return False


class NaverTouristWebSearchTool(BaseTool):
    """
    A tool that uses the Naver Web Search API to fetch tourist-related information.
    """

    name: str = "NaverTouristWebSearchTool"
    description: str = (
        "Searches for tourist information using the Naver Web Search API."
    )

    async def _arun(self, query: str) -> str:
        if not AGENT_NAVER_CLIENT_ID or not AGENT_NAVER_CLIENT_SECRET:
            return "[NaverTouristWebSearchTool] No Naver API credentials found."
        url = "https://openapi.naver.com/v1/search/webkr.json"
        headers = {
            "X-Naver-Client-Id": AGENT_NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": AGENT_NAVER_CLIENT_SECRET,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://search.naver.com/",
        }
        cleaned_query = clean_query(query)
        logger.info(f"[Tourist Web Search Query]: {cleaned_query}")
        params = {"query": cleaned_query, "display": 3, "start": 1, "sort": "sim"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    data = await response.json()
                    items = data.get("items", [])
                    if not items:
                        return ""
                    results = []
                    for item in items:
                        title = re.sub(r"<.*?>", "", item.get("title", ""))
                        link = item.get("link", "")
                        description = item.get("description", "")
                        results.append(
                            f"Title: {title}\nLink: {link}\nDescription: {description}"
                        )
                    return "\n".join(results)
        except Exception as e:
            logger.error(f"Tourist web search error: {e}")
            return ""

    def _run(self, query: str) -> str:
        return asyncio.run(self._arun(query))


class NaverTouristImageSearchTool(BaseTool):
    """
    A tool that uses the Naver Image Search API to fetch representative images of tourist spots.
    """

    name: str = "NaverTouristImageSearchTool"
    description: str = (
        "Searches for representative images of tourist spots using the Naver Image Search API."
    )

    async def _arun(self, query: Union[str, dict]) -> str:
        if isinstance(query, dict):
            query = query.get("description", "")
        if not query.strip():
            return ""
        if not AGENT_NAVER_CLIENT_ID or not AGENT_NAVER_CLIENT_SECRET:
            return "[NaverTouristImageSearchTool] No Naver API credentials found."
        url = "https://openapi.naver.com/v1/search/image"
        headers = {
            "X-Naver-Client-Id": AGENT_NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": AGENT_NAVER_CLIENT_SECRET,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://search.naver.com/",
        }
        cleaned_query = clean_query(query)
        logger.info(f"[Tourist Image Search Query]: {cleaned_query}")
        params = {
            "query": cleaned_query,
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
            logger.error(f"Tourist image search error: {e}")
            return "https://via.placeholder.com/300x200?text=Error"

    def _run(self, query: Union[str, dict]) -> str:
        return asyncio.run(self._arun(query))


class NaverTouristReviewTool(BaseTool):
    """
    A tool that crawls Naver reviews to extract tourist spot reviews.
    """

    name: str = "NaverTouristReviewTool"
    description: str = (
        "Crawls Naver reviews to extract tourist spot reviews and representative image."
    )

    async def _fetch_review_data(
        self, client: httpx.AsyncClient, placeId: str
    ) -> Union[dict, str]:
        # 관광지 URL (restaurant 대신 attraction 사용)
        url = f"https://m.place.naver.com/attraction/{placeId}/review/visitor?reviewSort=recent"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Referer": "https://m.place.naver.com/",
        }
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            reviews = soup.find_all("div", class_="pui__vn15t2")
            if not reviews:
                return f"[NaverTouristReviewTool] Error: Reviews not found."
            thumbnail_tag = soup.find("a", class_="place_thumb")
            if not thumbnail_tag:
                return f"[NaverTouristReviewTool] Error: Thumbnail not found."
            thumbnail = thumbnail_tag.find("img").get("src")
            if not thumbnail:
                return f"[NaverTouristReviewTool] Error: Thumbnail URL not found."
            reviews_list = [
                emoji.replace_emoji(review.text, replace="") for review in reviews
            ]
            return {
                "placeId": placeId,
                "image_url": thumbnail,
                "reviews": reviews_list,
            }
        except Exception as e:
            return f"[NaverTouristReviewTool] Error: {str(e)}"

    async def _arun(self, placeIds: List[str]) -> str:
        async with httpx.AsyncClient() as client:
            tasks = [self._fetch_review_data(client, placeId) for placeId in placeIds]
            results = await asyncio.gather(*tasks)
        valid_results = [res for res in results if isinstance(res, dict)]
        return json.dumps(valid_results, indent=4, ensure_ascii=False)

    def _run(self, placeIds: List[str]) -> str:
        return asyncio.run(self._arun(placeIds))


class NaverTouristBusinessInfoTool(BaseTool):
    """
    A tool that crawls Naver business info to extract tourist spot details such as operating hours and website.
    """

    name: str = "NaverTouristBusinessInfoTool"
    description: str = (
        "Crawls Naver to extract business info of tourist spots including website, operating hours, and category."
    )

    async def _fetch_business_info(
        self, client: httpx.AsyncClient, placeId: str
    ) -> Union[dict, str]:
        # 관광지 정보 URL (restaurant 대신 attraction 사용)
        url = f"https://m.place.naver.com/attraction/{placeId}/home"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Referer": "https://m.place.naver.com/",
        }
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            result = {
                "placeId": placeId,
                "url": "정보 없음",
                "business_hour": "정보 없음",
                "category": "정보 없음",
            }
            try:
                div_tag = soup.find("div", class_="jO09N")
                if div_tag:
                    a_tag = div_tag.find("a")
                    result["url"] = (
                        a_tag.get("href", "정보 없음") if a_tag else "정보 없음"
                    )
            except:
                pass
            try:
                business_span = soup.find("span", class_="U7pYf")
                if business_span:
                    span = business_span.find("span")
                    result["business_hour"] = span.text.strip() if span else "정보 없음"
            except:
                pass
            try:
                category_span = soup.find("span", class_="lnJFt")
                if category_span:
                    result["category"] = category_span.text.strip() or "정보 없음"
            except:
                pass
            return result
        except Exception as e:
            return f"[NaverTouristBusinessInfoTool] Error: {str(e)}"

    async def _arun(self, placeIds: List[str]) -> str:
        async with httpx.AsyncClient() as client:
            tasks = [self._fetch_business_info(client, placeId) for placeId in placeIds]
            results = await asyncio.gather(*tasks)
        valid_results = [res for res in results if isinstance(res, dict)]
        return json.dumps(valid_results, indent=4, ensure_ascii=False)

    def _run(self, placeIds: List[str]) -> str:
        return asyncio.run(self._arun(placeIds))
