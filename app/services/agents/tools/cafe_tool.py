from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import asyncio
import aiohttp       
import emoji
from crewai.tools import BaseTool
import json
from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field

from dotenv import load_dotenv
import os

load_dotenv()

# 네이버 API 관련 환경변수
AGENT_NAVER_CLIENT_ID = os.getenv("AGENT_NAVER_CLIENT_ID")
AGENT_NAVER_CLIENT_SECRET = os.getenv("AGENT_NAVER_CLIENT_SECRET")

class WebDriver:
    _driver = None
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_driver()
        return cls._instance
        
    def _initialize_driver(self):
        """WebDriver를 한 번만 초기화"""
        if WebDriver._driver is None:
            options = webdriver.ChromeOptions()
            options.add_argument("--headless")
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument("user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Mobile Safari/537.36")
            WebDriver._driver = webdriver.Chrome(options=options)    

    def get_driver(self):
        """WebDriver 인스턴스를 반환하는 메서드"""
        return WebDriver._driver        

    def quit_driver(self):
        """WebDriver 종료 메서드"""
        if WebDriver._driver:
            WebDriver._driver.quit()
            WebDriver._driver = None
         
def cafe_list_crawler(query):
    """
    네이버 지도에서 카페 정보를 크롤링하는 함수
    Args:
        query (str): 검색어
    Returns:
        list: 카페 정보 리스트
    """
    web_driver_instance = WebDriver()
    driver = web_driver_instance.get_driver() 
    spots_info = []
    
    try:
        url = f"https://m.map.naver.com/search2/search.naver?query={query}"
        driver.get(url)

        # 페이지 로딩 대기
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
      
        spots = WebDriverWait(driver, 10).until(
            EC.visibility_of_all_elements_located((By.CSS_SELECTOR, "li._lazyImgContainer")))
                
        for spot in spots:
            place_id = spot.get_attribute("data-id")
            map_url = f"https://m.place.naver.com/restaurant/{place_id}/location?filter=location&selected_place_id={place_id}"
            url = f"https://m.place.naver.com/restaurant/{place_id}/home"
            # 테스트 : https://m.place.naver.com/restaurant/1932943275/location?reviewSort=recent&filter=location&selected_place_id=1932943275

            try:
                address = spot.find_element(By.CLASS_NAME, "item_address").text.strip().replace("주소보기\n", "")
            except:
                address = "주소 없음"

            try:
                image_url = spot.find_element(By.CLASS_NAME, "_itemThumb").find_element(By.TAG_NAME, "img").get_attribute("src")
            except:
                image_url = "이미지 없음"
                
            spot_info = {
                "place_id": str(place_id),
                "kor_name": spot.get_attribute("data-title"),
                "address": address,
                "url": url,
                "image_url": image_url,
                "map_url" : map_url,
                "latitude": spot.get_attribute("data-latitude"),
                "longitude": spot.get_attribute("data-longitude"),
                "phone_number": spot.get_attribute("data-tel")
            }
            spots_info.append(spot_info)
        
        print(f"가져온 카페 개수: {len(spots_info)}")
        return spots_info

    except Exception as e:
        print(f"검색 오류 : {e}")
        return []
    
    finally:
        WebDriver().quit_driver()    
        
async def fetch_review(session, place_id):
    """
    비동기 리뷰 스크래퍼. 네이버 지도에서 카페를 정적 크롤링을 통해 검색하고 리뷰를 가져오는 도구.
    """
    url = f"https://m.place.naver.com/restaurant/{place_id}/review/visitor?reviewSort=recent"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
        "Referer": "https://m.place.naver.com/"
    }
    
    async with session.get(url, headers=headers) as response:
        if response.status != 200:
            print(f"{place_id} 요청 실패: {response.status}")
            return {"place_id": place_id, "reviews": []}

        html = await response.text()
        soup = BeautifulSoup(html, "html.parser")
        reviews = soup.find_all("div", class_="pui__vn15t2")
        reviews_list = [emoji.replace_emoji(review.text, replace='') for review in reviews]
        # print(len(reviews_list)) #10개 리뷰
        return {
            "place_id": place_id,
            "reviews": reviews_list
        }

async def fetch_business(session, place_id):
    """
    비동기 정보 스크래퍼. 네이버 지도에서 카페를 정적 크롤링을 통해 검색하고 정보를 가져오는 도구.
    """

    url = f"https://m.place.naver.com/restaurant/{place_id}/home"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
        "Referer": "https://m.place.naver.com/"
    }
    
    async with session.get(url, headers=headers) as response:
        if response.status != 200:
            print(f"{place_id} 요청 실패: {response.status}")
            return {"place_id": place_id, "reviews": []}

        html = await response.text()
        soup = BeautifulSoup(html, "html.parser")
        
        try:
            div_tag = soup.find("div", class_="jO09N")
            a_tag = div_tag.find("a") if div_tag else None
            url = a_tag["href"] if a_tag else "정보 없음"

            business_span = soup.find("span", class_="U7pYf")
            business_hour = business_span.find("span").text if business_span and business_span.find("span") else "정보 없음"

        except Exception as e:
            print(f"Parsing error: {e}")
            url = "정보 없음"
            business_hour = "정보 없음"
        
        return {
            "place_id": place_id,
            "url": url,
            "business_hour": business_hour
        }
                         
class QuerySchema(BaseModel):
    query: str = Field(
        ..., description="여행 지역 + 카페"
    )
    
class GetCafeListTool(BaseTool):
    """네이버 크롤링을 통해 카페 정보 수집"""
    name: str = "Cafe List and Information Tool"
    description: str = """
    네이버 지도에서 카페를 검색하고 정보를 가져오는 도구입니다.
    검색이 완료되면 카페 목록을 반환하고 작업을 종료합니다.
    한 번의 검색으로 충분한 정보를 제공합니다.
    """
    args_schema: Type[BaseModel] = QuerySchema
    _loop = None
    
    def __init__(self):
        super().__init__()
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
    
    # 리소스 정리        
    def __del__(self):            
        if self._loop and not self._loop.is_closed():
            self._loop.close()

    async def _collect_reviews(self, cafe_list):
        async with aiohttp.ClientSession() as session:
            tasks = [fetch_review(session, cafe["place_id"]) for cafe in cafe_list]
            return await asyncio.gather(*tasks)
     
    async def _collect_business_info(self, cafe_list):
        async with aiohttp.ClientSession() as session:
            tasks = [fetch_business(session, cafe["place_id"]) for cafe in cafe_list]
            return await asyncio.gather(*tasks)
            
    def _run(self, query: str) -> str:
        try:
            cafe_list = cafe_list_crawler(query)

            reviews = self._loop.run_until_complete(self._collect_reviews(cafe_list))
            
            for cafe, review in zip(cafe_list, reviews):
                cafe['reviews'] = review.get('reviews', [])

            business_info = self._loop.run_until_complete(self._collect_business_info(cafe_list))
            
            for cafe, info in zip(cafe_list, business_info):
                cafe['url'] = info.get('url', '')
                cafe['business_hour'] = info.get('business_hour', '')    
            
            return json.dumps({
                "status": "success",
                "count": len(cafe_list),
                "cafe_list": cafe_list
            }, ensure_ascii=False)

        except Exception as e:
            print(f"Execution error: {e}")
            return json.dumps({
                "status": "error",
                "message": str(e)
            })        

import json
import re
import httpx
import asyncio
from dotenv import load_dotenv
from crewai.tools import BaseTool
from typing import List
import os
import requests
from bs4 import BeautifulSoup
import json
import re
import emoji
    
load_dotenv()

# 네이버 API 관련 환경변수
AGENT_NAVER_CLIENT_ID = os.getenv("AGENT_NAVER_CLIENT_ID")
AGENT_NAVER_CLIENT_SECRET = os.getenv("AGENT_NAVER_CLIENT_SECRET")

# 1. 강남 카페 느좋
# 2. 강남 카페 내돈내산
# 3. 강남 카페 비추(제외)

class NaverWebSearchTool(BaseTool):
    name: str = "NaverWebSearch"
    description: str = "네이버 웹 검색 API를 사용해 카페 검색"

    async def _arun(self, query: str) -> str:
        if not AGENT_NAVER_CLIENT_ID or not AGENT_NAVER_CLIENT_SECRET:
            return "[NaverWebSearchTool] 네이버 API 자격 증명이 없습니다."
        url = "https://openapi.naver.com/v1/search/blog.json"
        headers = {
            "X-Naver-Client-Id": AGENT_NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": AGENT_NAVER_CLIENT_SECRET,
        }
        params = {"query": query, "display": 30, "start": 1, "sort": "sim"}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
            items = data.get("items", [])
            if not items:
                return f"[NaverWebSearchTool] '{query}' 검색 결과 없음."
            results = []
            print(len(items))
            for item in items:
                title = item.get("title", "")
                link = item.get("link", "")
                desc = item.get("description", "")
                # postdate = item.get("postdate", "") # 작성일자
                results.append(f"제목: {title}\n링크: {link}\n설명: {desc}\n")
            return "\n".join(results)
        except Exception as e:
            return f"[NaverWebSearchTool] 에러: {str(e)}"

    def _run(self, query: str) -> str:
        return asyncio.run(self._arun(query))

class NaverBlogCralwerTool(BaseTool):
    name: str = "NaverBlogCralwer"
    description: str = "네이버 블로그를 크롤링해 카페 정보 추출"

    async def _fetch_blog_data(self, url: str) -> str:
        url = url.replace('https://blog.naver.com', 'https://m.blog.naver.com')
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Referer": "https://m.blog.naver.com/"
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            a_tag = soup.find("a", class_="se-map-info __se_link")
            if not a_tag:
                # print("지도 url이 없는 포스팅입니다. 다른 포스팅을 다시 검색하세요")
                return None

            data_module_content = a_tag.get("data-linkdata")
            data = json.loads(data_module_content)
            place_info={}
            place_info["placeId"] = data.get("placeId","")
            place_info["name"] = data.get("name","")
            place_info["address"] = data.get("address","")
            place_info["latitude"] = data.get("latitude","")
            place_info["longitude"] = data.get("longitude","")
            place_info["tel"] = data.get("tel","")                     
            place_info["url"] = data.get("bookingUrl","")                     

            return place_info

        except Exception as e:
            return f"[cafe_tool:NaverBlogCralwer] 에러: {str(e)}"

    async def _arun(self, urls: List[str]) -> str:
        """여러 개의 블로그 URL을 받아 카페 정보를 수집"""
        tasks = [self._fetch_blog_data(url) for url in urls if url]
        results = await asyncio.gather(*tasks)

        # 오류 메시지 제외하고 유효한 데이터만 반환
        cafes = [res for res in results if res and isinstance(res, dict) and "error" not in res]

        return json.dumps(cafes, indent=4, ensure_ascii=False)

    def _run(self, urls: List[str]) -> str:
        """동기 함수에서 실행 (urls는 블로그 URL 리스트)"""
        return asyncio.run(self._arun(urls))
    
class NaverReviewCralwerTool(BaseTool):
    name: str = "NaverReviewCralwer"
    description: str = "네이버 리뷰를 크롤링해 카페 후기 추출"

    async def _fetch_review_data(self, placeId: str) -> str:
        url = f"https://m.place.naver.com/restaurant/{placeId}/review/visitor?reviewSort=recent"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Referer": "https://m.place.naver.com/"
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            reviews = soup.find_all("div", class_="pui__vn15t2")
            if not reviews:
                return f"[cafe_tool:NaverReviewCralwer] 에러: {str(e)}"

            reviews_list = [emoji.replace_emoji(review.text, replace='') for review in reviews]
            return {
                "placeId": placeId,
                "reviews": reviews_list
            }
        except Exception as e:
            return f"[cafe_tool:NaverReviewCralwer] 에러: {str(e)}"

    async def _arun(self, placeIds: List[str]) -> str:
        """여러 개의 장소 placeId를 받아 카페 리뷰를 수집"""
        tasks = [self._fetch_review_data(placeId) for placeId in placeIds]
        results = await asyncio.gather(*tasks)

        # 오류 메시지 제외하고 유효한 데이터만 반환
        cafes = [res for res in results if "error" not in res]

        return json.dumps(cafes, indent=4, ensure_ascii=False)

    def _run(self, placeIds: List[str]) -> str:
        """동기 함수에서 실행 (queryplaceIds는 장소 placeId 리스트)"""
        return asyncio.run(self._arun(placeIds))
        

# naver_tool = NaverWebSearchTool()
# result = await naver_tool._arun("강남 카페")
# print(result)

# url_lists = ["https://blog.naver.com/moonyo1002/223740338163","https://blog.naver.com/bluerabbit_b/223740394460","https://blog.naver.com/pkj5456/223689489478"]
# blog_tool = NaverBlogCralwerTool()
# result = await blog_tool._arun(url_lists)
# print(result)

# placeIds = ["1785877248", "1614878009","1158509033"]
# review_tool = NaverReviewCralwerTool()
# result = await review_tool._arun(placeIds)
# print(result)


from crewai.tools import BaseTool

from pydantic import BaseModel, Field
from typing import Any, Type
import json
import requests
import os
from dotenv import load_dotenv

load_dotenv()
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
NAVER_PLACE_ID = os.getenv("NAVER_PLACE_ID")
NAVER_PLACE_SECRET = os.getenv("NAVER_PLACE_SECRET")

class QuerySchema(BaseModel):
    query: str = Field(
        ..., description="Mandatory search query for searching places on the map"
    )
    
class GoogleMapSearchTool(BaseTool):
    """구글 맵 검색 API를 사용해 텍스트 정보를 검색"""
    name: str = "Google MapSearch"
    description: str = "구글 맵 검색 API를 사용해 텍스트 정보를 검색"
    args_schema: Type[BaseModel] = QuerySchema
    
    def _run(self, query: str) -> str:
        if not SERPER_API_KEY:
            return "[GoogleMapSearchTool] serper.dev API 자격 증명이 없습니다."

        payload = json.dumps({
        "q": query
        })
        
        url = "https://google.serper.dev/maps"
        headers = {
            "X-API-KEY": os.environ["SERPER_API_KEY"],
            "content-type": "application/json",
        }

        try:
            with requests.Session() as session:
                resp = session.post(url, headers=headers, data=payload)

            resp.raise_for_status()
            data = resp.json()
            places = data.get("places", [])

            if not places:
                return f"[GoogleMapSearchTool] '{query}' 검색 결과 없음."

            results = []
            for place in places:
                title = place.get("title", "")
                address = place.get("address", "")
                latitude = place.get("latitude", "")
                longitude = place.get("longitude", "")
                website = place.get("website", "")                                               
                phoneNumber = place.get("phoneNumber", "")
                openingHours = place.get("openingHours", "")
                thumbnailUrl = place.get("thumbnailUrl", "")                                          
                map_url = f"https://www.google.com/maps/place/?q=place_id:{place.get('placeId', '')}"
                results.append(f"이름: {title}\n주소: {address}\n위도: {latitude}\n경도: {longitude}\n홈페이지: {website}\n전화번호: {phoneNumber}\n운영시간: {openingHours}\n썸네일: {thumbnailUrl}\n지도주소: {map_url}\n---")

            return "\n".join(results)

        except Exception as e:
            return f"[GoogleMapSearchTool] 에러: {str(e)}"

# tool = GoogleMapSearchTool()
# result = tool._run("강남 마들렌")
# print(result)

class NaverLocalSearchTool(BaseTool):
    """네이버 local 검색 API를 사용해 텍스트 정보를 검색"""
    name: str = "네이버 local Search Tool"
    description: str = "네이버 local 검색 API를 사용해 카페 정보를 검색"
    args_schema: Type[BaseModel] = QuerySchema
    
    def _run(self, query, display=1, start=1, sort="random")-> str:
        
        search_url = "https://openapi.naver.com/v1/search/local.json"
        headers = {
            "X-Naver-Client-Id": NAVER_PLACE_ID,
            "X-Naver-Client-Secret": NAVER_PLACE_SECRET,
        }

        params = {
            "query": query,
            "display": display,
            "start": start,
            "sort": sort,
        }

        with requests.Session() as session:
            response = session.get(search_url, headers=headers, params=params)

        results = []
        if response.status_code == 200:
            result = response.json()
            cafes = result.get("items",[])
  
            if not cafes:  # 검색 결과가 없으면 오류 방지
                return f"[NaverLocalSearchTool] '{query}'에 대한 검색 결과가 없습니다."

            # 첫 번째 결과가 있는지 확인 후 접근
            first_cafe = cafes[0] if len(cafes) > 0 else {}

            title = first_cafe.get('title', '정보 없음')
            address = first_cafe.get('roadAddress', '정보 없음')
            url = first_cafe.get('link', '정보 없음')
  
            results.append(f"이름: {title}\n주소: {address}\n웹사이트: {url}---")
            return "\n".join(results)

        else:
            print("Error:", response.status_code, response.text)
            return None
    

# tool = HomeURLSearchTool()
# result = tool._run("강남 마들마들")
# print(result)
from pydantic import BaseModel
from typing import Type


class MultiToolWrapper(BaseTool):
    """두 개의 툴을 동시에 실행하는 툴"""
    name: str = "Multi Tool Wrapper"
    description: str = "크로스체크를 위해 google map과 naver local api를 이용하는 툴"
    args_schema: Type[BaseModel] = QuerySchema
    
    def __init__(self, google_tool: GoogleMapSearchTool, naver_tool: NaverLocalSearchTool):
        super().__init__()
        self._google_tool = google_tool 
        self._naver_tool = naver_tool
        
    def _run(self, query: str) -> str:
        google_search_result = self._google_tool._run(query)
        naver_search_result = self._naver_tool._run(query)
        
        return f"구글 맵 검색 결과:\n{google_search_result}\n\n 네이버 로컬 검색 결과:\n{naver_search_result}"


    # 네이버 블로그 본문 추출
    # content = soup.find('div', {'class': 'se-main-container'})
    # if content:
    #     # 텍스트 추출 및 공백 정리
    #     text = ' '.join(content.stripped_strings)
    #     cleaned_text = re.sub(r'\s+', ' ', text).strip()
        
    #     # 불필요한 문자열 제거
    #     unwanted_strings = ['blog.naver.com', 'search.naver.com', 'open.kakao.com']
    #     for unwanted in unwanted_strings:
    #         cleaned_text = cleaned_text.replace(unwanted, '').strip()

    #     # 이모티콘 제거
    #     cleaned_text = emoji.replace_emoji(cleaned_text, replace='')
            
    # print(cleaned_text)

