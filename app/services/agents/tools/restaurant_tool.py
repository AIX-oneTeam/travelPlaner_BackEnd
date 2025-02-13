import asyncio
import aiohttp
import httpx
import datetime
import os
import re
from crewai.tools import BaseTool
from typing import List, Dict, Type
from pydantic import BaseModel, create_model
from dotenv import load_dotenv


# 환경 변수 로드
load_dotenv()
GOOGLE_MAP_API_KEY = os.getenv("GOOGLE_MAP_API_KEY")
AGENT_NAVER_CLIENT_ID = os.getenv("AGENT_NAVER_CLIENT_ID")
AGENT_NAVER_CLIENT_SECRET = os.getenv("AGENT_NAVER_CLIENT_SECRET")
KAKAO_MAP_API_KEY = os.getenv("KAKAO_MAP_API_KEY")


def clean_query(query: str) -> str:
    """
    입력 문자열이 여러 줄일 경우, 각 줄에 대해
    1. 파이프(|) 이후 내용 제거
    2. 괄호와 괄호 안의 내용 제거
    3. 한글, 영어, 숫자, 공백, 하이픈(-)만 남기고 나머지 제거
    4. 앞뒤 공백 제거
    를 수행하고, 각 줄의 결과를 하나의 문자열로 반환합니다.
    """
    clean_lines = []
    for line in query.splitlines():
        # 1. 파이프(|)가 있는 경우, 파이프와 그 이후의 모든 내용을 제거합니다.
        line = line.split("|")[0]
        # 2. 괄호 ()와 그 안의 내용을 모두 제거합니다.
        line = re.sub(r"\([^)]*\)", "", line)
        # 3. 한글(가-힣), 영어(a-z, A-Z), 숫자(0-9), 공백(\s), 하이픈(-) 외의 모든 문자를 제거합니다.
        line = re.sub(r"[^\uAC00-\uD7A3a-zA-Z0-9\s\-]", "", line)
        # 4. 양쪽 공백 제거
        line = line.strip()
        if line:
            clean_lines.append(line)
    return " ".join(clean_lines)

async def check_url_openable_async(url: str) -> bool:
    """
    주어진 URL에 대해 HEAD 요청을 보내어 접근 가능한지 확인합니다.

    - HTTP 상태 코드가 200 이상 400 미만이면 접근 가능(True)로 간주합니다.
    - 예외가 발생하거나 상태 코드가 해당 범위에 있지 않으면 False를 반환합니다.
    """
    # URL이 빈 문자열이면 False 반환
    if not url:
        return False

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.head(url, follow_redirects=True)
            if 200 <= response.status_code < 400:
                return True
            else:
                return False
    except Exception as e:
        print(f"Error checking URL '{url}': {e}")
        return False


# 1. Google Geocoding API를 사용하여 좌표를 조회하는 Tool
class GeocodingTool(BaseTool):
    name: str = "GeocodingTool"
    description: str = (
        "Google Geocoding API를 사용하여 주어진 위치의 위도와 경도를 조회합니다. "
        "입력된 location 값은 변경 없이 그대로 반환합니다."
    )

    async def _arun(self, location: str) -> Dict:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"address": location, "key": GOOGLE_MAP_API_KEY}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    data = await response.json()
                    if data.get("results"):
                        loc = data["results"][0]["geometry"]["location"]
                        coordinates = f"{loc['lat']},{loc['lng']}"
                    else:
                        coordinates = ""
        except Exception as e:
            coordinates = f"[GeocodingTool] Error: {str(e)}"
        return {"location": location, "coordinates": coordinates}

    def _run(self, location: str) -> Dict:
        return asyncio.run(self._arun(location))


# 2. Google Places API를 사용해 맛집 기본 정보를 조회하는 Tool
class RestaurantBasicSearchTool(BaseTool):
    name: str = "RestaurantBasicSearchTool"
    description: str = (
        "주어진 좌표와 location 정보를 기반으로 구글맵에서 식당의 title, rating, reviews를 검색합니다."
    )

    async def get_place_details(
        self, session: aiohttp.ClientSession, place_id: str
    ) -> Dict:
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            "place_id": place_id,
            "fields": "name,rating,user_ratings_total,geometry",
            "language": "ko",
            "key": GOOGLE_MAP_API_KEY,
        }
        try:
            async with session.get(url, params=params) as response:
                data = await response.json()
                result = data.get("result", {})
                return {
                    "title": result.get("name"),
                    "rating": result.get("rating", 0),
                    "reviews": result.get("user_ratings_total", 0),
                }
        except Exception as e:
            print(f"[RestaurantBasicSearchTool] Details Error: {e}")
            return None

    async def _arun(self, location: str, coordinates: str) -> List[Dict]:
        url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        all_candidates = []
        lat, lng = coordinates.split(",")
        params = {
            "query": f"{location} 맛집",
            "language": "ko",
            "type": "restaurant",
            "location": f"{lat},{lng}",
            "radius": "5000",
            "key": GOOGLE_MAP_API_KEY,
        }

        async def fetch_places(filter_rating: float, filter_reviews: int):
            """특정 필터링 기준으로 Google Places API에서 식당 정보를 가져오는 함수"""
            candidates = []
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    data = await response.json()
                    results = data.get("results", [])
                    print(
                        f"첫 요청 결과 수: {len(results)} (필터 기준: 평점 {filter_rating} 이상, 리뷰 {filter_reviews}개 이상)"
                    )

                    for place in results:
                        place_id = place.get("place_id")
                        if place_id:
                            details = await self.get_place_details(session, place_id)
                            if (
                                details
                                and details["rating"] >= filter_rating
                                and details["reviews"] >= filter_reviews
                            ):
                                candidates.append(details)

                    next_page_token = data.get("next_page_token")

                    # 추가 요청: 후보 수가 15개 미만이면 추가로 요청
                    while next_page_token and len(candidates) < 15:
                        try:
                            await asyncio.sleep(3)  # next_page_token 유효 대기
                            params["pagetoken"] = next_page_token
                            async with session.get(url, params=params) as response:
                                data = await response.json()
                                new_results = data.get("results", [])
                                print(f"추가 요청 결과 수: {len(new_results)}")

                                for place in new_results:
                                    if len(candidates) >= 40:
                                        break
                                    place_id = place.get("place_id")
                                    if place_id:
                                        details = await self.get_place_details(
                                            session, place_id
                                        )
                                        if (
                                            details
                                            and details["rating"] >= filter_rating
                                            and details["reviews"] >= filter_reviews
                                        ):
                                            candidates.append(details)

                                next_page_token = data.get("next_page_token")
                        except Exception as e:
                            print(f"추가 페이지 요청 오류: {e}")
                            break
            return candidates

        try:
            # 1차 필터링: 평점 4.0 이상 & 리뷰 500개 이상
            all_candidates = await fetch_places(4.0, 500)

            # 첫 번째 결과가 2개 미만이면 기준 완화 (외곽 지역 판단)
            if len(all_candidates) < 2:
                print(
                    "첫 페이지 결과가 2개 미만 → 필터링 조건 완화 (평점 3.5 이상, 리뷰 100개 이상) 후 재요청"
                )
                all_candidates = await fetch_places(3.5, 100)

            print(f"최종 수집된 맛집 수: {len(all_candidates)}")
        except Exception as e:
            print(f"[RestaurantBasicSearchTool] Search Error: {e}")
        return all_candidates

    def _run(self, location: str, coordinates: str) -> List[Dict]:
        return asyncio.run(self._arun(location, coordinates))


# 3. 네이버 웹 검색 API를 사용해 식당의 세부 정보를 조회하는 Tool
class NaverWebSearchTool(BaseTool):
    name: str = "NaverWebSearch"
    description: str = "네이버 웹 검색 API를 사용해 식당의 상세 정보를 검색합니다."

    async def fetch(self, session: aiohttp.ClientSession, query: str):
        url = "https://openapi.naver.com/v1/search/webkr.json"
        headers = {
            "X-Naver-Client-Id": AGENT_NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": AGENT_NAVER_CLIENT_SECRET,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://search.naver.com/",
        }

        # 입력 문자열을 clean_query 함수를 통해 정리합니다.
        query = clean_query(query)
        print(f"[네이버 세부정부 검색어]: {query}")

        params = {
            "query": query,
            "display": 3,
            "start": 1,
            "sort": "sim",
        }
        try:
            async with session.get(url, headers=headers, params=params) as response:
                data = await response.json()
                items = data.get("items", [])
                if not items:
                    return {"description": "정보를 찾을 수 없습니다.", "url": ""}
                descriptions = []
                for item in items:
                    desc = item.get("description", "").strip()
                    if desc and len(desc) > 30:
                        descriptions.append(desc)
                combined_description = " ".join(descriptions)
                return {
                    "description": (
                        combined_description[:200]
                        if len(combined_description) > 200
                        else combined_description
                    ),
                    "url": items[0].get("link", "") if items else "",
                }
        except Exception as e:
            print(f"네이버 웹 검색 오류: {str(e)}")
            return {"description": "정보 없음", "url": ""}

    async def _arun(self, restaurant_list: List[str]) -> Dict[str, Dict[str, str]]:
        results = {}
        async with aiohttp.ClientSession() as session:
            for restaurant in restaurant_list:
                results[restaurant] = await self.fetch(session, restaurant)
        return results

    def _run(self, restaurant_list: List[str]) -> Dict[str, Dict[str, str]]:
        return asyncio.run(self._arun(restaurant_list))


# 4. 네이버 이미지 검색 API를 사용해 식당의 대표 이미지를 조회하는 Tool
class NaverImageSearchTool(BaseTool):
    name: str = "NaverImageSearch"
    description: str = (
        "네이버 이미지 검색 API를 사용해 식당의 대표 이미지를 검색합니다."
    )

    async def fetch(self, session: aiohttp.ClientSession, query: str):
        url = "https://openapi.naver.com/v1/search/image"
        headers = {
            "X-Naver-Client-Id": AGENT_NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": AGENT_NAVER_CLIENT_SECRET,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://search.naver.com/",
        }

        query = clean_query(query)
        print(f"[네이버 이미지 검색어]: {query}")

        params = {
            "query": query,
            "display": 5,
            "sort": "sim",
            "filter": "all",
        }
        try:
            async with session.get(url, headers=headers, params=params) as response:
                data = await response.json()
                items = data.get("items", [])
                if not items:
                    return "https://via.placeholder.com/300x200?text=No+Image"

                # 받아온 여러 이미지 URL 중 실제 접근 가능한 URL을 선택 (check_url_openable_async 사용)
                for item in items:
                    img_url = item.get("link", "")
                    if await check_url_openable_async(img_url):
                        return img_url

                # 만약 모두 접근 불가능하다면, 기본 이미지 URL 반환
                return "https://via.placeholder.com/300x200?text=No+Image"
        except Exception as e:
            print(f"네이버 이미지 검색 오류: {str(e)}")
            return "https://via.placeholder.com/300x200?text=Error"

    async def _arun(self, restaurant_list: List[str]) -> Dict[str, str]:
        results = {}
        async with aiohttp.ClientSession() as session:
            for restaurant in restaurant_list:
                results[restaurant] = await self.fetch(session, restaurant)
        return results

    def _run(self, restaurant_list: List[str]) -> Dict[str, str]:
        return asyncio.run(self._arun(restaurant_list))


# 5. 카카오 로컬 API를 사용해 식당의 상세 정보를 조회하는 Tool
class KakaoLocalSearchTool(BaseTool):
    name: str = "KakaoLocalSearch"
    description: str = "카카오 로컬 API를 사용해 식당의 위치 정보를 검색합니다."

    async def fetch(self, session: aiohttp.ClientSession, name: str, location: str):
        url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_MAP_API_KEY}"}

        # 검색어 변형 리스트 생성 (location 포함)
        search_queries = [
            f"{location} {name}",  # 예: "해운대 할매집 돼지국밥 본점"
            (
                f"{location} {name.split()[-2]} {name.split()[-1]}"
                if len(name.split()) > 2
                else f"{location} {name}"
            ),  # "해운대 돼지국밥 본점"
            (
                f"{location} {' '.join(name.split()[:-1])}"
                if len(name.split()) > 1
                else f"{location} {name}"
            ),  # "해운대 할매집 돼지국밥"
            f"{location} {name.split()[0]}",  # "해운대 할매집"
        ]

        for query in search_queries:
            print(f"[카카오 로컬 검색어 시도]: {query}")
            params = {
                "query": query,
                "category_group_code": "FD6",
                "size": 1,
            }

            try:
                async with session.get(url, headers=headers, params=params) as response:
                    data = await response.json()
                    documents = data.get("documents", [])

                    if documents:
                        place = documents[0]
                        place_id = place.get("id")

                        result = {
                            "kor_name": name,
                            "address": place.get("road_address_name")
                            or place.get("address_name", ""),
                            "latitude": float(place.get("y", 0)) or None,
                            "longitude": float(place.get("x", 0)) or None,
                            "map_url": (
                                f"https://map.kakao.com/link/map/{place_id}"
                                if place_id
                                else ""
                            ),
                            "phone_number": place.get("phone", ""),
                            # "category_name": place.get("category_name", ""),
                        }
                        print(
                            f"[카카오 로컬 검색 성공] 검색어: {query}, 결과: {result}"
                        )
                        return result

            except Exception as e:
                print(f"카카오 로컬 검색 오류: {str(e)}")
                continue

        print(f"[카카오 로컬 검색 실패] 모든 검색어 시도 실패: {search_queries}")
        return self._get_empty_result(name)

    def _get_empty_result(self, name: str) -> dict:
        """검색 실패 시 기본값 반환"""
        return {
            "kor_name": name,
            "address": "",
            "latitude": None,
            "longitude": None,
            "map_url": "",
            "phone_number": "",
            # "category_name": "",
        }

    async def _arun(self, restaurant_names: List[str], location: str) -> List[Dict]:
        """모든 식당 정보를 병렬로 처리"""
        results = []
        async with aiohttp.ClientSession() as session:
            tasks = [self.fetch(session, name, location) for name in restaurant_names]
            results = await asyncio.gather(*tasks)
        return results

    def _run(self, restaurant_names: List[str], location: str) -> List[Dict]:
        return asyncio.run(self._arun(restaurant_names, location))
