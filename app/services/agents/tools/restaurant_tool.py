import asyncio
import aiohttp
import httpx
import os
import re
from datetime import datetime
from crewai.tools import BaseTool
from typing import List, Dict, Union
from dotenv import load_dotenv
import logging

from app.repository.db import get_async_session_manual
from app.repository.images.image_url_repository import get_image_url, save_image_url

logger = logging.getLogger("restaurant_agent_tools")
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler('logs/restaurant_agent_service.log', encoding="utf-8")
file_handler.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)

# 환경 변수 로드
load_dotenv()
GOOGLE_MAP_API_KEY = os.getenv("GOOGLE_MAP_API_KEY")
AGENT_NAVER_CLIENT_ID = os.getenv("AGENT_NAVER_CLIENT_ID")
AGENT_NAVER_CLIENT_SECRET = os.getenv("AGENT_NAVER_CLIENT_SECRET")
KAKAO_LOCAL_API_KEY = os.getenv("KAKAO_LOCAL_API_KEY")


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
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.head(url, follow_redirects=True)
            if 200 <= response.status_code < 400:
                return True
            else:
                return False
    except Exception as e:
        logger.error(f"Error checking URL '{url}': {e}")
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
        "주어진 좌표와 검색 키워드를 기반으로 구글맵에서 식당 정보를 검색합니다."
    )

    def calculate_target_count(self, start_date: str, end_date: str) -> int:
        """여행 일수에 따른 목표 수집 개수 계산"""
        start = datetime.strptime(start_date.split("T")[0], "%Y-%m-%d")
        end = datetime.strptime(end_date.split("T")[0], "%Y-%m-%d")
        days = (end - start).days + 1

        # 1일 7개, 2일 10개, 3일 13개, 4일 16개...
        if days == 1:
            return 7
        else:
            return 7 + (days - 1) * 3

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
            logger.error(f"[RestaurantBasicSearchTool] Details Error: {e}")
            return None

    async def search_with_filter(
        self,
        keywords: List[str],
        coordinates: str,
        filter_rating: float,
        filter_reviews: int,
        remaining_count: int,
        collected_names: set,
        session: aiohttp.ClientSession,
    ) -> List[Dict]:
        url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        collected = []
        lat, lng = coordinates.split(",")

        for keyword in keywords:
            if len(collected) >= remaining_count:
                break

            simplified_keyword = keyword.split(" - ")[-1]
            params = {
                "query": simplified_keyword,
                "language": "ko",
                "type": "restaurant",
                "location": f"{lat},{lng}",
                "radius": "5000",
                "key": GOOGLE_MAP_API_KEY,
            }

            # 첫 페이지 요청
            async with session.get(url, params=params) as response:
                data = await response.json()
                results = data.get("results", [])
                logger.info(
                    f"키워드 '{simplified_keyword}' 첫 요청 결과 수: {len(results)} (필터 기준: 평점 {filter_rating} 이상, 리뷰 {filter_reviews}개 이상)"
                )

                tasks = []
                for place in results:
                    place_id = place.get("place_id")
                    if place_id:
                        tasks.append(self.get_place_details(session, place_id))
                if tasks:
                    details_list = await asyncio.gather(*tasks, return_exceptions=True)
                    for details in details_list:
                        if len(collected) >= remaining_count:
                            break
                        if isinstance(details, Exception):
                            continue
                        if (
                            details
                            and details["rating"] >= filter_rating
                            and details["reviews"] >= filter_reviews
                            and details["title"] not in collected_names
                        ):
                            collected.append(details)
                            collected_names.add(details["title"])
                # ---------------------------------------------------------------------

                next_page_token = data.get("next_page_token")

                # 다음 페이지가 있고 목표 개수에 도달하지 않았을 때만 계속 검색
                while next_page_token and len(collected) < remaining_count:
                    try:
                        await asyncio.sleep(3)  # next_page_token 유효 대기
                        params["pagetoken"] = next_page_token
                        async with session.get(url, params=params) as resp:
                            data = await resp.json()
                            new_results = data.get("results", [])
                            logger.info(
                                f"키워드 '{simplified_keyword}' 추가 요청 결과 수: {len(new_results)}"
                            )

                            tasks = []
                            for place in new_results:
                                place_id = place.get("place_id")
                                if place_id:
                                    tasks.append(
                                        self.get_place_details(session, place_id)
                                    )
                            if tasks:
                                details_list = await asyncio.gather(
                                    *tasks, return_exceptions=True
                                )
                                for details in details_list:
                                    if len(collected) >= remaining_count:
                                        break
                                    if isinstance(details, Exception):
                                        continue
                                    if (
                                        details
                                        and details["rating"] >= filter_rating
                                        and details["reviews"] >= filter_reviews
                                        and details["title"] not in collected_names
                                    ):
                                        collected.append(details)
                                        collected_names.add(details["title"])
                            # -----------------------------------------------------------------

                            next_page_token = data.get("next_page_token")

                            # 목표 개수 달성 시 즉시 종료
                            if len(collected) >= remaining_count:
                                break
                    except Exception as e:
                        logger.error(f"추가 페이지 요청 오류: {e}")
                        break

        return collected

    async def _arun(
        self,
        coordinates: str,
        search_keywords: List[str],
        start_date: str,
        end_date: str,
        existing_spot_names: List[str] = None,
    ) -> List[Dict]:
        target_count = self.calculate_target_count(start_date, end_date)
        collected_spots = []
        collected_names = set(existing_spot_names) if existing_spot_names else set()

        logger.info(f"[keywords]: {search_keywords}")
        logger.info(f"[목표 수집 개수]: {target_count}")

        async with aiohttp.ClientSession() as session:
            # 1단계: 대도시 기준 (전체 키워드로 검색)
            remaining = target_count - len(collected_spots)
            logger.info(
                f"1단계 검색 시작 (평점 4.0 이상, 리뷰 500개 이상) - 목표: {remaining}개"
            )
            collected = await self.search_with_filter(
                search_keywords,
                coordinates,
                4.0,
                500,
                remaining,
                collected_names,
                session,
            )
            collected_spots.extend(collected)
            logger.info(f"1단계 검색 완료: {len(collected_spots)}개 수집")

            # 목표량 미달시 2단계: 중소도시 기준
            if len(collected_spots) < target_count:
                remaining = target_count - len(collected_spots)
                logger.info(
                    f"2단계 검색 시작 (평점 3.5 이상, 리뷰 200개 이상) - 목표: {remaining}개"
                )
                collected = await self.search_with_filter(
                    search_keywords,
                    coordinates,
                    3.5,
                    200,
                    remaining,
                    collected_names,
                    session,
                )
                collected_spots.extend(collected)
                logger.info(f"2단계 검색 완료: 총 {len(collected_spots)}개 수집")

            # 여전히 미달시 3단계: 외곽/지방 기준
            if len(collected_spots) < target_count:
                remaining = target_count - len(collected_spots)
                logger.info(
                    f"3단계 검색 시작 (평점 3.3 이상, 리뷰 100개 이상) - 목표: {remaining}개"
                )
                collected = await self.search_with_filter(
                    search_keywords,
                    coordinates,
                    3.3,
                    100,
                    remaining,
                    collected_names,
                    session,
                )
                collected_spots.extend(collected)
                logger.info(f"3단계 검색 완료: 총 {len(collected_spots)}개 수집")

        logger.info(f"최종 수집된 맛집 수: {len(collected_spots)}")
        return collected_spots

    def _run(
        self,
        coordinates: str,
        search_keywords: List[str],
        start_date: str,
        end_date: str,
        existing_spot_names: List[str] = None,
    ) -> List[Dict]:
        return asyncio.run(
            self._arun(
                coordinates, search_keywords, start_date, end_date, existing_spot_names
            )
        )


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
        logger.info(f"[네이버 세부정보 검색어]: {query}")

        params = {
            "query": query,
            "display": 3,
            "start": 1,
            "sort": "sim",
        }

        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                async with session.get(url, headers=headers, params=params) as response:
                    data = await response.json()
                    items = data.get("items", [])
                    if items:
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
                    else:
                        logger.warning(
                            f"[네이버 웹 검색] 시도 {attempt+1}/{max_attempts}: 결과 없음"
                        )
            except Exception as e:
                logger.error(
                    f"네이버 웹 검색 오류 시도 {attempt+1}/{max_attempts}: {str(e)}"
                )
            await asyncio.sleep(1)  # 재시도 전 잠시 대기
        return {"description": "정보를 찾을 수 없습니다.", "url": ""}

    async def _arun(self, restaurant_list: List[str]) -> Dict[str, Dict[str, str]]:
        results = {}
        async with aiohttp.ClientSession() as session:
            tasks = [self.fetch(session, restaurant) for restaurant in restaurant_list]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for restaurant, response in zip(restaurant_list, responses):
                results[restaurant] = response
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
        logger.info(f"[네이버 이미지 검색어]: {query}")

        params = {
            "query": query,
            "display": 5,
            "sort": "sim",
            "filter": "all",
        }

        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                async with session.get(url, headers=headers, params=params) as response:
                    data = await response.json()
                    items = data.get("items", [])
                    if not items:
                        logger.warning(
                            f"[네이버 이미지 검색] 시도 {attempt+1}/{max_attempts}: 결과 없음"
                        )
                    else:
                        # 받아온 여러 이미지 URL 중 실제 접근 가능한 URL을 선택 (check_url_openable_async 사용)
                        for item in items:
                            img_url = item.get("link", "")
                            if await check_url_openable_async(img_url):
                                return img_url
            except Exception as e:
                logger.error(
                    f"네이버 이미지 검색 오류 시도 {attempt+1}/{max_attempts}: {str(e)}"
                )
            await asyncio.sleep(1)  # 재시도 전 잠시 대기
        # 모든 시도 실패 시 None 반환
        return None

    async def _arun(
        self, restaurant_list: Union[List[str], List[Dict], Dict]
    ) -> Dict[str, str]:
        # 딕셔너리 리스트인 경우 처리
        if (
            isinstance(restaurant_list, list)
            and restaurant_list
            and isinstance(restaurant_list[0], dict)
        ):
            restaurants = [
                r.get("kor_name", "") for r in restaurant_list if r.get("kor_name")
            ]
        # 기존 로직 유지
        elif isinstance(restaurant_list, dict):
            if "type" in restaurant_list:
                restaurants = restaurant_list["type"]
            else:
                restaurants = []
        else:
            restaurants = (
                restaurant_list
                if isinstance(restaurant_list, list)
                else [restaurant_list]
            )

        restaurants = [str(r) for r in restaurants if r is not None]

        results = {}
        async with aiohttp.ClientSession() as session:
            tasks = [self.fetch(session, restaurant) for restaurant in restaurants]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for restaurant, response in zip(restaurants, responses):
                results[restaurant] = response
        return results

    def _run(self, restaurant_list: Union[List[str], Dict]) -> Dict[str, str]:
        return asyncio.run(self._arun(restaurant_list))


# class NaverImageSearchTool(BaseTool):
#     name: str = "NaverImageSearch"
#     description: str = (
#         "네이버 이미지 검색 API를 사용해 식당의 대표 이미지를 검색합니다."
#     )

#     async def fetch(self, session: aiohttp.ClientSession, query: str):
#         url = "https://openapi.naver.com/v1/search/image"
#         headers = {
#             "X-Naver-Client-Id": AGENT_NAVER_CLIENT_ID,
#             "X-Naver-Client-Secret": AGENT_NAVER_CLIENT_SECRET,
#             "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
#             "Referer": "https://search.naver.com/",
#         }

#         query = clean_query(query)
#         logger.info(f"[🪔네이버 이미지 검색어]: {query}")

#         params = {
#             "query": query,
#             "display": 5,
#             "sort": "sim",
#             "filter": "all",
#         }

#         max_attempts = 2
#         for attempt in range(max_attempts):
#             logger.info(f"[🪔네이버 이미지 검색 {attempt+1}/{max_attempts}번째 시도]")
#             logger.info(f"[🪔네이버 이미지 검색 ]: {params}를 검색합니다.")

#             # db_session = await get_async_session_manual()
#             # try:
#             #     # DB에서 조회
#             #     existing_image_url = await get_image_url(query, db_session)
#             #     if existing_image_url:
#             #         logger.info(f"[🪔네이버 이미지 검색]: {existing_image_url}가 이미 DB에서 존재합니다.")
#             #         return existing_image_url

#             # logger.info(f"[🪔네이버 이미지 검색]: 데이터베이스에 결과가 없습니다. 웹에서 검색합니다.")
#             async with session.get(url, headers=headers, params=params) as response:
#                 data = await response.json()

#                 items = data.get("items", [])
#                 if not items:
#                     logger.warning(
#                         f"[🪔네이버 이미지 검색] 시도 {attempt+1}/{max_attempts}: 결과 없음"
#                     )
#                     continue

#                 # 받아온 여러 이미지 URL 중 실제 접근 가능한 URL을 선택
#                 for item in items:
#                     img_url = item.get("link", "")
#                     if await check_url_openable_async(img_url):
#                         logger.info(
#                             f"[🪔네이버 이미지 검색]: {img_url}를 찾았습니다. DB에 저장합니다."
#                         )
#                         # await save_image_url(img_url, query, db_session)
#                         # await db_session.commit()
#                         return img_url
#             # except Exception as e:
#             logger.error(
#                 f"[🪔네이버 이미지 검색 오류] 시도 {attempt+1}/{max_attempts}: {str(e)}"
#             )
#             # await db_session.commit()
#             # finally:
#             # await db_session.close()
#             await asyncio.sleep(1)  # 재시도 전 잠시 대기

#     async def _arun(
#         self, restaurant_list: Union[List[str], List[Dict], Dict]
#     ) -> Dict[str, str]:
#         # 딕셔너리 리스트인 경우 처리
#         if (
#             isinstance(restaurant_list, list)
#             and restaurant_list
#             and isinstance(restaurant_list[0], dict)
#         ):
#             restaurants = [
#                 r.get("kor_name", "") for r in restaurant_list if r.get("kor_name")
#             ]
#         # 기존 로직 유지
#         elif isinstance(restaurant_list, dict):
#             if "type" in restaurant_list:
#                 restaurants = restaurant_list["type"]
#             else:
#                 restaurants = []
#         else:
#             restaurants = (
#                 restaurant_list
#                 if isinstance(restaurant_list, list)
#                 else [restaurant_list]
#             )

#         restaurants = [str(r) for r in restaurants if r is not None]

#         results = {}
#         async with aiohttp.ClientSession() as session:
#             tasks = [self.fetch(session, restaurant) for restaurant in restaurants]
#             responses = await asyncio.gather(*tasks, return_exceptions=True)
#             for restaurant, response in zip(restaurants, responses):
#                 results[restaurant] = response
#         return results

#     def _run(self, restaurant_list: Union[List[str], Dict]) -> Dict[str, str]:
#         return asyncio.run(self._arun(restaurant_list))


# 5. 카카오 로컬 API를 사용해 식당의 상세 정보를 조회하는 Tool
class KakaoLocalSearchTool(BaseTool):
    name: str = "KakaoLocalSearch"
    description: str = "카카오 로컬 API를 사용해 식당의 위치 정보를 검색합니다."

    async def fetch(self, session: aiohttp.ClientSession, name: str, location: str):
        url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_LOCAL_API_KEY}"}

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

        max_attempts = 2
        for query in search_queries:
            for attempt in range(max_attempts):
                logger.info(
                    f"[카카오 로컬 검색어 시도]: {query} (시도 {attempt+1}/{max_attempts})"
                )
                params = {
                    "query": query,
                    "category_group_code": "FD6",
                    "size": 1,
                }
                try:
                    async with session.get(
                        url, headers=headers, params=params
                    ) as response:
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
                            logger.info(
                                f"[카카오 로컬 검색 성공] 검색어: {query}, 결과: {result}"
                            )
                            return result
                        else:
                            logger.warning(
                                f"[카카오 로컬 검색] 시도 {attempt+1}/{max_attempts}: 결과 없음"
                            )
                except Exception as e:
                    logger.error(
                        f"카카오 로컬 검색 오류 시도 {attempt+1}/{max_attempts}: {str(e)}"
                    )
                await asyncio.sleep(1)  # 재시도 전 잠시 대기
        logger.warning(
            f"[카카오 로컬 검색 실패] 모든 검색어 시도 실패: {search_queries}"
        )
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
            results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

    def _run(self, restaurant_names: List[str], location: str) -> List[Dict]:
        return asyncio.run(self._arun(restaurant_names, location))
