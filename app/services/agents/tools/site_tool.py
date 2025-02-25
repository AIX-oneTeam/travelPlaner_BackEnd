import asyncio
import aiohttp
import httpx
import os
import re
import json
import logging
import random
import difflib
from crewai.tools import BaseTool
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import emoji
from typing import List, Dict, Optional, Union, ClassVar

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

AGENT_NAVER_CLIENT_ID = os.getenv("AGENT_NAVER_CLIENT_ID")
AGENT_NAVER_CLIENT_SECRET = os.getenv("AGENT_NAVER_CLIENT_SECRET")
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")


def clean_query(query: str) -> str:
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
    if not url:
        return False
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        ) as session:
            async with session.head(url, allow_redirects=True) as response:
                logger.info(f"URL {url} status: {response.status}")
                return 200 <= response.status < 400
    except Exception as e:
        logger.error(f"Error checking URL '{url}': {e}")
        return False


class KakaoGeocodeTool:
    def __init__(self):
        self.api_key = KAKAO_API_KEY
        self.base_url = "https://dapi.kakao.com/v2/local/search/address.json"

    async def get_coordinates(self, address: str) -> dict:
        headers = {"Authorization": f"KakaoAK {self.api_key}"}
        params = {"query": address}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                self.base_url, headers=headers, params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    documents = data.get("documents", [])
                    if documents:
                        addr_info = documents[0].get("address", {})
                        try:
                            longitude = float(addr_info.get("x", 0))
                            latitude = float(addr_info.get("y", 0))
                        except (TypeError, ValueError):
                            longitude, latitude = 0, 0
                        return {"latitude": latitude, "longitude": longitude}
                    else:
                        logger.warning(
                            "KakaoGeocodeTool: No address info found for: %s", address
                        )
                        return {"latitude": 0, "longitude": 0}
                else:
                    logger.error(
                        "KakaoGeocodeTool: API error with status %s", response.status
                    )
                    return {"latitude": 0, "longitude": 0}


class NaverBlogSearchTool(BaseTool):
    name: str = "NaverBlogSearchTool"
    description: str = (
        "Searches Naver blogs and extracts review text for tourist spots."
    )

    async def _fetch_query(self, client: httpx.AsyncClient, query: str) -> list:
        await asyncio.sleep(random.uniform(0.05, 0.2))
        url = "https://openapi.naver.com/v1/search/blog.json"
        headers = {
            "X-Naver-Client-Id": AGENT_NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": AGENT_NAVER_CLIENT_SECRET,
        }
        params = {"query": query, "display": 10, "start": 1, "sort": "sim"}
        try:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            links = [item.get("link", "") for item in items if item.get("link")]
            return links
        except Exception as e:
            logger.error(f"[NaverBlogSearchTool] 검색 쿼리 {query} 에러: {str(e)}")
            return []

    async def _fetch_blog_data(self, client: httpx.AsyncClient, url: str) -> str:
        await asyncio.sleep(random.uniform(0.05, 0.2))
        url = url.replace("https://blog.naver.com", "https://m.blog.naver.com")
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Referer": "https://m.blog.naver.com/",
        }
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            reviews = text.split(".")[:3]
            return ". ".join(reviews).strip()
        except Exception as e:
            logger.error(f"[NaverBlogSearchTool] 블로그 데이터 크롤링 에러: {str(e)}")
            return ""

    async def _arun(self, query: str) -> str:
        cleaned_query = clean_query(query)
        async with httpx.AsyncClient() as client:
            links = await self._fetch_query(client, cleaned_query)
            if links:
                blog_review = await self._fetch_blog_data(client, links[0])
                return blog_review
            else:
                return ""

    def _run(self, query: str) -> str:
        return asyncio.run(self._arun(query))


class NaverTouristWebSearchTool(BaseTool):
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
    name: str = "NaverTouristImageSearchTool"
    description: str = (
        "Searches for representative images of tourist spots using the Naver Image Search API."
    )
    used_urls: ClassVar[set] = set()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.info("Initializing NaverTouristImageSearchTool")

    def similarity(self, a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio()

    async def _arun(self, query: Union[str, dict]) -> str:
        if isinstance(query, dict):
            query = query.get("description", "")
        if not query.strip():
            logger.warning("Empty query provided to NaverTouristImageSearchTool.")
            return "https://via.placeholder.com/300x200?text=No+Query"

        if not AGENT_NAVER_CLIENT_ID or not AGENT_NAVER_CLIENT_SECRET:
            logger.error("Naver API credentials are missing.")
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
        params = {"query": cleaned_query, "display": 10, "sort": "sim", "filter": "all"}

        SIMILARITY_THRESHOLD = 0.05

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
                    logger.info(f"API Response: {data}")
                    items = data.get("items", [])
                    if not items:
                        logger.warning(
                            f"No image items found for query: {cleaned_query}"
                        )
                        return "https://via.placeholder.com/300x200?text=No+Image"

                    for item in items:
                        img_url = item.get("link", "")
                        title = item.get("title", "").lower()
                        if img_url in self.used_urls:
                            logger.info(f"Skipping duplicate image URL: {img_url}")
                            continue
                        sim = self.similarity(cleaned_query.lower(), title)
                        if sim < SIMILARITY_THRESHOLD:
                            logger.info(
                                f"Skipping image due to low similarity: {title} (similarity={sim:.2f})"
                            )
                            continue
                        logger.info(f"Checking image URL: {img_url}")
                        if await check_url_openable_async(img_url):
                            logger.info(f"Valid image URL found: {img_url}")
                            self.used_urls.add(img_url)
                            return img_url
                        else:
                            logger.warning(f"Image URL not accessible: {img_url}")

                    logger.info(
                        "No accessible or unique image URLs found, returning placeholder."
                    )
                    return "https://via.placeholder.com/300x200?text=No+Image"
        except Exception as e:
            logger.error(f"Tourist image search error: {e}")
            return "https://via.placeholder.com/300x200?text=Error"

    def _run(self, query: Union[str, dict]) -> str:
        return asyncio.run(self._arun(query))


class NaverTouristReviewTool(BaseTool):
    name: str = "NaverTouristReviewTool"
    description: str = (
        "Crawls Naver reviews to extract tourist spot reviews and representative image."
    )

    async def _find_place_id(self, query: str) -> Optional[str]:
        if not AGENT_NAVER_CLIENT_ID or not AGENT_NAVER_CLIENT_SECRET:
            logger.error("Naver API credentials missing for place ID search.")
            return None
        url = "https://openapi.naver.com/v1/search/local.json"
        headers = {
            "X-Naver-Client-Id": AGENT_NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": AGENT_NAVER_CLIENT_SECRET,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        }
        cleaned_query = clean_query(query)
        params = {"query": cleaned_query, "display": 1, "sort": "random"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    data = await response.json()
                    logger.info(f"Place ID search response for {cleaned_query}: {data}")
                    items = data.get("items", [])
                    if items:
                        link = items[0].get("link", "")
                        place_id = re.search(r"place/(\d+)", link)
                        if place_id:
                            logger.info(
                                f"Found place ID {place_id.group(1)} for {query}"
                            )
                            return place_id.group(1)
                        logger.warning(f"No place ID found in link: {link}")
                        return None
                    logger.warning(f"No items found for query: {cleaned_query}")
                    return None
        except Exception as e:
            logger.error(f"Place ID search error for {query}: {e}")
            return None

    async def _fetch_review_data(
        self, client: httpx.AsyncClient, place_id: str, original_query: str
    ) -> Union[dict, str]:
        url = f"https://m.place.naver.com/place/{place_id}/review/visitor?reviewSort=recent"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Referer": "https://m.place.naver.com/",
        }
        try:
            resp = await client.get(url, headers=headers, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            reviews = soup.find_all("div", class_="pui__vn15t2")
            if reviews:
                thumbnail_tag = soup.find("a", class_="place_thumb")
                thumbnail = (
                    thumbnail_tag.find("img").get("src") if thumbnail_tag else None
                )
                reviews_list = [
                    emoji.replace_emoji(review.text, replace="") for review in reviews
                ]
                logger.info(
                    f"Reviews fetched for place_id {place_id}: {reviews_list[:2]}"
                )
                return {
                    "placeId": place_id,
                    "image_url": thumbnail
                    or "https://via.placeholder.com/300x200?text=No+Thumbnail",
                    "reviews": reviews_list,
                }
            else:
                logger.warning(
                    f"No reviews found for place_id {place_id} via mobile, trying blog fallback."
                )
                blog_tool = NaverBlogSearchTool()
                blog_query = f"{original_query} 관광지 리뷰"
                blog_review_text = await blog_tool._arun(blog_query)
                if blog_review_text:
                    return {
                        "placeId": place_id,
                        "image_url": "https://via.placeholder.com/300x200?text=No+Thumbnail",
                        "reviews": blog_review_text.split(".")[:3],
                    }
                else:
                    logger.warning(f"No blog results for fallback query: {blog_query}")
                    return {"placeId": place_id, "image_url": None, "reviews": []}
        except Exception as e:
            logger.error(f"Review fetch error for place_id {place_id}: {e}")
            return f"[NaverTouristReviewTool] Error: {str(e)}"

    async def _arun(self, placeIds: List[str]) -> str:
        async with httpx.AsyncClient() as client:
            tasks = []
            for place_name in placeIds:
                place_id = await self._find_place_id(place_name)
                if place_id:
                    tasks.append(self._fetch_review_data(client, place_id, place_name))
                else:
                    logger.warning(f"Skipping {place_name} due to no place ID found.")
                    tasks.append(
                        asyncio.sleep(
                            0,
                            result={
                                "placeId": place_name,
                                "image_url": None,
                                "reviews": [],
                            },
                        )
                    )
            results = await asyncio.gather(*tasks)
        valid_results = [res for res in results if isinstance(res, dict)]
        logger.info(
            f"Valid review results: {len(valid_results)} out of {len(placeIds)}"
        )
        return json.dumps(valid_results, indent=4, ensure_ascii=False)

    def _run(self, placeIds: List[str]) -> str:
        return asyncio.run(self._arun(placeIds))


class NaverTouristBusinessInfoTool(BaseTool):
    name: str = "NaverTouristBusinessInfoTool"
    description: str = (
        "Crawls Naver to extract business info of tourist spots including website, operating hours, and category."
    )

    async def _fetch_business_info(
        self, client: httpx.AsyncClient, placeId: str
    ) -> Union[dict, str]:
        url = f"https://m.place.naver.com/place/{placeId}/home"
        headers = {
            "X-Naver-Client-Id": AGENT_NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": AGENT_NAVER_CLIENT_SECRET,
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Referer": "https://m.place.naver.com/",
        }
        try:
            resp = await client.get(url, headers=headers, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            result = {
                "placeId": placeId,
                "url": "정보 없음",
                "business_hour": "정보 없음",
                "category": "정보 없음",
            }
            div_tag = soup.find("div", class_="jO09N")
            if div_tag:
                a_tag = div_tag.find("a")
                result["url"] = a_tag.get("href", "정보 없음") if a_tag else "정보 없음"
            business_span = soup.find("span", class_="U7pYf")
            if business_span:
                span = business_span.find("span")
                result["business_hour"] = span.text.strip() if span else "정보 없음"
            category_span = soup.find("span", class_="lnJFt")
            if category_span:
                result["category"] = category_span.text.strip() or "정보 없음"
            return result
        except Exception as e:
            logger.error(f"Business info fetch error for {placeId}: {e}")
            return f"[NaverTouristBusinessInfoTool] Error: {str(e)}"

    async def _arun(self, placeIds: List[str]) -> str:
        async with httpx.AsyncClient() as client:
            tasks = [self._fetch_business_info(client, placeId) for placeId in placeIds]
            results = await asyncio.gather(*tasks)
        valid_results = [res for res in results if isinstance(res, dict)]
        return json.dumps(valid_results, indent=4, ensure_ascii=False)

    def _run(self, placeIds: List[str]) -> str:
        return asyncio.run(self._arun(placeIds))
