from datetime import datetime
import itertools
import json
import httpx
import asyncio
from dotenv import load_dotenv
from crewai.tools import BaseTool
from typing import List, Optional
import os
from bs4 import BeautifulSoup
import json
import emoji  
import re
from app.utils.simplify_address import simplify_address
import random
import logging

from app.utils.validate_address import validate_address
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler('logs/cafe_agent.log', encoding="utf-8")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
load_dotenv()

# 에러 전용 로그 파일 생성
file_handler_error = logging.FileHandler('logs/cafe_agent_error.log', encoding="utf-8")
file_handler_error.setLevel(logging.ERROR)
formatter_error = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler_error.setFormatter(formatter_error)
logger.addHandler(file_handler_error)

# 네이버 API 관련 환경변수
AGENT_NAVER_CLIENT_ID = os.getenv("AGENT_NAVER_CLIENT_ID")
AGENT_NAVER_CLIENT_SECRET = os.getenv("AGENT_NAVER_CLIENT_SECRET")   
    
class NaverBlogSearchTool(BaseTool):
    name: str = "NaverBlogSearchTool"
    description: str = "블로그를 검색하고 url에서 카페 정보 추출"
    
    async def _fetch_query(self, client: httpx.AsyncClient, query: str) -> str:
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

            links = []
            for item in items:
                link = item.get("link", "")
                if link:  # 링크가 존재할 때만 추가
                    links.append(link)   

            return links
        
        except Exception as e:
            logger.error(f"[NaverBlogSearchTool] 검색 쿼리 {query} 에러: {str(e)}")
            return []
    
    async def _fetch_blog_data(self, client: httpx.AsyncClient, url: str) -> str:
        await asyncio.sleep(random.uniform(0.05, 0.2))
        url = url.replace('https://blog.naver.com', 'https://m.blog.naver.com')
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Referer": "https://m.blog.naver.com/"
        }
        try:
                        
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            a_tag = soup.find("a", class_="se-map-info __se_link")
            if not a_tag:
                return None

            data_module_content = a_tag.get("data-linkdata")
            data = json.loads(data_module_content)
            
            placeId = data.get("placeId")
            if not placeId:  # placeId가 없는 경우만 체크
                return None
                                    
            return {
                "placeId": placeId,
                "kor_name": data.get("name", "정보 없음"),
                "address": data.get("address", "정보 없음"),
                "latitude": data.get("latitude", 0),
                "longitude": data.get("longitude", 0),
                "phone_number": data.get("tel", "정보 없음"),
            }                  

        except Exception as e:
            return f"[cafe_tool:NaverBlogCralwer] 에러: {str(e)}"

    async def _arun(self, main_location: str, keywords: Optional[list]=["느좋"]) -> str:
        
        simplified_location = simplify_address(main_location)
        keywords_queries = [f"{simplified_location} {keyword} 카페" for keyword in keywords]
        basic_queries = [simplified_location + " 카페", simplified_location + " 느좋 카페"]
        queries = basic_queries + keywords_queries
        logger.info(f"사용한 검색어 : {queries}")
        valid_prefixes = validate_address(main_location)
        async with httpx.AsyncClient() as client:

            # 쿼리별 서치
            search_tasks = [self._fetch_query(client, query) for query in queries]
            search_results = await asyncio.gather(*search_tasks)
 
            # 중첩 리스트 평탄화
            cafe_urls_draft = list(itertools.chain.from_iterable(search_results))
            cafe_urls = [url for url in cafe_urls_draft if url.startswith(('https://blog.naver.com', 'https://m.blog.naver.com'))]
            
            if cafe_urls:

                # url 방문 개수 기록
                logger.info(f"NaverBlogSearchTool : 검색시 사용한 url 수 {len(cafe_urls)}")

                # 크롤링
                crawling_tasks = [self._fetch_blog_data(client, urls) for urls in cafe_urls]
                crawling_results = await asyncio.gather(*crawling_tasks)

                valid_results = [result for result in crawling_results if isinstance(result, dict)]
                error_results = [result for result in crawling_results if isinstance(result, str)]
            
                if error_results:
                    logger.error(f"[Cafetool] Crawling Errors: {error_results}")
                
                # 여기서 valid_results를 한 번에 필터링
                filtered_results = []
                for place_data in valid_results:
                    addr = place_data.get("address", "")
                    if any(addr.startswith(prefix) for prefix in valid_prefixes):
                        filtered_results.append(place_data)
                    else:
                        logger.info(f"주소 '{addr}'가 유효 접두어 {valid_prefixes} 중 하나로 시작하지 않아 필터링됨.")

                place_dict = {}
                for place_data in valid_results:
                    place_id = place_data['placeId']
                    
                    # 이미 존재하면 n_posting 증가
                    if place_id in place_dict:
                        place_dict[place_id]["n_posting"] += 1
                    else:
                        # 새로 추가할 때 n_posting = 1로 설정
                        place_dict[place_id] = {
                            "placeId": place_data.get("placeId") or "정보 없음",
                            "kor_name": place_data.get("kor_name") or "정보 없음",
                            "address": place_data.get("address") or "정보 없음",
                            "latitude": place_data.get("latitude") or "0",
                            "longitude": place_data.get("longitude") or "0",
                            "phone_number": place_data.get("phone_number") or "정보 없음",
                            "n_posting": 1
                        }

                # 리스트 형태로 변환
                result_list = list(place_dict.values())
                logger.info(f" Final Result: {result_list}") 
                return json.dumps(result_list, indent=4, ensure_ascii=False)
    
    def _run(self, main_location: str, keywords: list) -> str:
        return asyncio.run(self._arun(main_location, keywords))

# async def main():
#     print("Client ID:", AGENT_NAVER_CLIENT_ID)
#     print("Client Secret:", AGENT_NAVER_CLIENT_SECRET)

#     blog_tool = NaverBlogSearchTool()
#     result = await blog_tool._arun("서울특별시 - 강남구", ["힐링", "오션뷰"])
#     print(result)


# # 비동기 함수 실행
# if __name__ == "__main__":
#     asyncio.run(main())


# cafe_blogs = ["https://blog.naver.com/scr02070/223121950899", "https://blog.naver.com/ajy951230/223093046319", "https://blog.naver.com/congsuni04/223236886369","https://blog.naver.com/ordinary_chae/223683617720", "https://blog.naver.com/comiyoun/223611761198"]
# blog_tool = NaverBlogCralwerTool()
# result = await blog_tool._arun(cafe_blogs)
# print(result)
    
class NaverReviewCralwerTool(BaseTool):
    name: str = "NaverReviewCralwerTool"
    description: str = "네이버 리뷰를 크롤링해 카페 후기 추출"

    async def _fetch_review_data(self, client: httpx.AsyncClient, placeId: str) -> str:
        await asyncio.sleep(random.uniform(0.05, 0.2))
        url = f"https://m.place.naver.com/restaurant/{placeId}/review/visitor?reviewSort=recent"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Referer": "https://m.place.naver.com/"
        }
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            reviews = soup.find_all("div", class_="pui__vn15t2")
            if not reviews:
                return f"[cafe_tool:NaverReviewCralwer] 에러: 리뷰를 찾을 수 없습니다.]"

            thumbnail = soup.find("a", class_="place_thumb").find("img").get("src")
            if not thumbnail:
                return f"[cafe_tool:NaverReviewCralwer] 에러: 이미지를 찾을 수 없습니다.]"

            reviews_list = [emoji.replace_emoji(review.text, replace='') for review in reviews]
            return {
                "placeId": placeId,
                "image_url": thumbnail,
                "reviews": reviews_list,
            }
        except Exception as e:
            return f"[cafe_tool:NaverReviewCralwer] 에러: {str(e)}"

    async def _arun(self, placeIds: List[str]) -> str:
        """여러 개의 장소 placeId를 받아 카페 리뷰를 수집"""
                   
        # url 방문 개수 기록
        logger.info(f"NaverReviewCralwerTool : 검색시 사용한 url 수 {len(placeIds)}")


        async with httpx.AsyncClient() as client:
            tasks = [self._fetch_review_data(client, placeId) for placeId in placeIds]
            results = await asyncio.gather(*tasks)

        # 오류 메시지 제외하고 유효한 데이터만 반환
        cafes = [res for res in results if "error" not in res]

        return json.dumps(cafes, indent=4, ensure_ascii=False)

    def _run(self, placeIds: List[str]) -> str:
        """동기 함수에서 실행 (queryplaceIds는 장소 placeId 리스트)"""
        return asyncio.run(self._arun(placeIds))

# placeIds = ["1785877248", "1614878009","1158509033"]
# review_tool = NaverReviewCralwerTool()
# result = await review_tool._arun(placeIds)
# print(result)
    
class NaverBusinessInfoTool(BaseTool):
    name: str = "NaverBusinessInfoCralwer"
    description: str = "네이버 업체 정보를 크롤링해 카페 운영시간, 웹사이트 정보 추출"
    
    async def _fetch_business_info(self, client: httpx.AsyncClient, placeId: str) -> str:
        """
        비동기 정보 스크래퍼. 네이버 지도에서 카페를 정적 크롤링을 통해 검색하고 정보를 가져오는 도구.
        """
        await asyncio.sleep(random.uniform(0.05, 0.2))
        url = f"https://m.place.naver.com/restaurant/{placeId}/home"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Referer": "https://m.place.naver.com/"
        }
        try:        
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            
            website = f"https://m.place.naver.com/restaurant/{placeId}/home"
            
            # 기본 반환 데이터
            result = {
                "placeId": placeId,
                "url": website,
                "business_hour": "정보 없음",
                "category": "정보 없음"
            }
            
            # URL 정보 추출
            try:
                if div_tag := soup.find("div", class_="jO09N"):
                    if a_tag := div_tag.find("a"):
                        result["url"] = a_tag.get("href") or website
            except:
                pass
                
            # 영업시간 정보 추출
            try:
                if business_span := soup.find("span", class_="U7pYf"):
                    if span := business_span.find("span"):
                        result["business_hour"] = span.text.strip() or "정보 없음"
            except:
                pass
            
            # 업종 정보 추출
            try:
                if category_span := soup.find("span", class_="lnJFt"):
                    result["category"] = category_span.text.strip() or "정보 없음"
            except:
                pass

            return result
                
        except Exception as e:
            return f"[cafe_tool:_fetch_business_info] 에러: {str(e)}"
    
    async def _arun(self, placeIds: List[str]) -> str:
        """여러 개의 장소 placeId를 받아 카페 리뷰를 수집"""

        # url 방문 개수 기록
        logger.info(f"NaverBusinessInfoTool : 검색시 사용한 url 수 {len(placeIds)}")
        
        async with httpx.AsyncClient() as client:
            tasks = [self._fetch_business_info(client, placeId) for placeId in placeIds]
            results = await asyncio.gather(*tasks)

        # 오류 메시지 제외하고 유효한 데이터만 반환
        cafes = [res for res in results if "error" not in res]

        return json.dumps(cafes, indent=4, ensure_ascii=False)

    def _run(self, placeIds: List[str]) -> str:
        """동기 함수에서 실행 (queryplaceIds는 장소 placeId 리스트)"""
        return asyncio.run(self._arun(placeIds))

# placeIds = ["1785877248", "1614878009","1158509033"]
# info_tool = NaverBusinessInfoTool()
# result = await info_tool._arun(placeIds)
# print(result)
    
  