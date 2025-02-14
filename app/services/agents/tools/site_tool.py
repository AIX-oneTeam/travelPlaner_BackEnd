import asyncio
import aiohttp
from crewai.tools import BaseTool
from typing import Dict, Union
from dotenv import load_dotenv
import os
import re
import httpx

# Load environment variables
load_dotenv()
AGENT_NAVER_CLIENT_ID = os.getenv("AGENT_NAVER_CLIENT_ID")
AGENT_NAVER_CLIENT_SECRET = os.getenv("AGENT_NAVER_CLIENT_SECRET")


def clean_query(query: str) -> str:
    """
    Cleans the input string by:
    1. Removing content after a pipe (|).
    2. Removing parentheses and the text within.
    3. Retaining only Korean, English, digits, whitespace, and hyphens (-).
    4. Trimming leading and trailing whitespace.
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
    Sends a HEAD request to the given URL to verify its accessibility.
    Returns True if the HTTP status code is between 200 and 399.
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
        query = clean_query(query)
        print(f"[Tourist Web Search Query]: {query}")
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
                        # Remove HTML tags
                        title = re.sub(r"<.*?>", "", item.get("title", ""))
                        link = item.get("link", "")
                        description = item.get("description", "")
                        results.append(
                            f"Title: {title}\nLink: {link}\nDescription: {description}"
                        )
                    return "\n".join(results)
        except Exception as e:
            print(f"Tourist web search error: {e}")
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
        query = clean_query(query)
        print(f"[Tourist Image Search Query]: {query}")
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
            print(f"Tourist image search error: {e}")
            return "https://via.placeholder.com/300x200?text=Error"

    def _run(self, query: Union[str, dict]) -> str:
        return asyncio.run(self._arun(query))
