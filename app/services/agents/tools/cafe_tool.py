import json
import httpx
import asyncio
from dotenv import load_dotenv
from crewai.tools import BaseTool
from typing import List, Dict, Optional
import os
from bs4 import BeautifulSoup
import json
import emoji  
import re
load_dotenv()

# 네이버 API 관련 환경변수
AGENT_NAVER_CLIENT_ID = os.getenv("AGENT_NAVER_CLIENT_ID")
AGENT_NAVER_CLIENT_SECRET = os.getenv("AGENT_NAVER_CLIENT_SECRET")

def simplify_address(region: str) -> str:
    # 먼저 입력 문자열에 "-"가 포함되어 있으면 "-"로, 없으면 공백을 기준으로 분리합니다.
    if "-" in region:
        parts = [p.strip() for p in region.split("-")]
    else:
        parts = region.split(maxsplit=1)
        parts = [p.strip() for p in parts]

    # 시/도명을 단축하는 함수 (특정 도/시의 경우 별도 매핑)
    def shorten_province(prov: str) -> str:
        # 추가 매핑 규칙
        if prov == "충청북도":
            return "충북"
        if prov == "충청남도":
            return "충남"
        if prov == "경상남도":
            return "경남"
        if prov == "경상북도":
            return "경북"
        if prov == "세종특별자치시":
            return "세종"
        if prov == "전라남도":
            return "전남"
        # 기본 처리
        if "특별자치도" in prov:
            return prov.replace("특별자치도", "")
        elif "특별시" in prov:
            return prov.replace("특별시", "")
        elif "광역시" in prov:
            return prov.replace("광역시", "")
        elif prov.endswith("도"):
            return prov[:-1]
        elif prov.endswith("시"):
            return prov[:-1]
        else:
            return prov

    # 두번째 지역명(구/군/시)을 가공하는 함수
    def process_district(district: str, prov_short: str) -> str:
        # district가 '구', '군', '시'로 끝나면 마지막 글자 제거한 후보(candidate) 생성
        if district.endswith(("구", "군", "시")):
            candidate = district[:-1]
            # 예외: district가 province_short + "시"인 경우 원본 그대로 사용
            if district.endswith("시") and district == prov_short + "시":
                return district
            # 후보가 2글자면 단축해서 사용, 그렇지 않으면 원래 이름 사용
            if len(candidate) == 2:
                return candidate
            else:
                return district
        else:
            return district

    # 첫번째 부분(시/도) 처리
    province_str = parts[0]
    province_short = shorten_province(province_str)

    # 두번째 부분(구/군/시)이 있으면 처리
    if len(parts) > 1:
        district_str = parts[1]
        # 부산진구
        if province_str == "부산광역시" and district_str.startswith(province_short):
            result = district_str
        # 4글자구면 시/도 생략
        elif district_str != "부산진구" and len(district_str)==4:
            result = district_str[:-1]
        else:
            district_processed = process_district(district_str, province_short)
            result = f"{province_short} {district_processed}"
    else:
        result = province_short
        
    return result
    
class NaverBlogSearchTool(BaseTool):
    name: str = "NaverBlogSearch"
    description: str = "네이버 웹 검색 API를 사용해 카페 검색"

    async def _fetch_query(self, client: httpx.AsyncClient, query: str) -> str:

        url = "https://openapi.naver.com/v1/search/blog.json"
        headers = {
            "X-Naver-Client-Id": AGENT_NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": AGENT_NAVER_CLIENT_SECRET,
        }
        params = {"query": query, "display": 20, "start": 1, "sort": "sim"}
        try:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            if not items:
                return f"[NaverBlogSearchTool] '{query}' 검색 결과 없음."
            results = []
            for item in items:
                title = item.get("title", "")
                link = item.get("link", "")
                desc = item.get("description", "")
                results.append(f"제목: {title}\n링크: {link}\n설명: {desc}\n")
            result_text = "\n".join(results)
            return f"검색 쿼리: {query}\n결과:\n{result_text}"
        except Exception as e:
            return f"[NaverBlogSearchTool] 검색 쿼리 {query} 에러: {str(e)}"
        
    async def _arun(self, main_location: str, keywords:List[str]) -> str:
        if not AGENT_NAVER_CLIENT_ID or not AGENT_NAVER_CLIENT_SECRET:
            return "[NaverBlogSearchTool] 네이버 API 자격 증명이 없습니다."
        
        simplified_location = simplify_address(main_location)
        # keywords가 비어있으면 기본 검색어를 사용
        if keywords:
            keywords_query = f"{simplified_location} 카페 +{' +'.join(keywords)}"
        else:
            keywords_query = f"{simplified_location} 카페"
        
        querys =[keywords_query, simplified_location+" 카페", simplified_location+" 느좋 카페"]
        
        async with httpx.AsyncClient() as client:
            # 각 검색어마다 비동기 요청(task)을 생성합니다.
            tasks = [self._fetch_query(client, query) for query in querys]
            results = await asyncio.gather(*tasks)
            # 각 검색 결과를 구분하기 위해 빈 줄 두 개로 연결
            return "\n---------------\n".join(results)
            
    def _run(self, main_location: str, keywords:List[str]) -> str:
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
    
    
class NaverBlogCralwerTool(BaseTool):
    name: str = "NaverBlogCralwer"
    description: str = "개별 블로그 url에서 카페 정보 추출"
    
    async def _fetch_blog_data(self, client: httpx.AsyncClient, url: str) -> str:
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
                "name": data.get("name", ""),
                "address": data.get("address", ""),
                "latitude": data.get("latitude", ""),
                "longitude": data.get("longitude", ""),
                "tel": data.get("tel", ""),
            }                  

        except Exception as e:
            return f"[cafe_tool:NaverBlogCralwer] 에러: {str(e)}"

    async def process_cafe(self, client: httpx.AsyncClient, cafe_name:str, urls: List[str]) -> Optional[dict]:
        """
        해당 카페의 URL 리스트를 순차적으로 시도하여, 첫 번째 유효한 결과를 반환.
        """
        for idx, url in enumerate(urls):
                result = await self._fetch_blog_data(client, url)
                if isinstance(result, dict) and result.get("placeId"):
                    # 유효한 결과를 얻으면 바로 반환 (나머지 URL은 크롤링하지 않음)
                    # print(f"{cafe_name} - {idx}번만에 크롤링 성공")
                    return result
        return None


    async def _arun(self, cafe_urls: Dict[str, List[str]]) -> str:
        semaphore = asyncio.Semaphore(5)
        
        async def bounded_fetch(client, cafe_name, urls):
            async with semaphore:
                return await self.process_cafe(client, cafe_name, urls)
        
        async with httpx.AsyncClient() as client:
            tasks = [bounded_fetch(client, cafe_name, urls)   for cafe_name, urls in cafe_urls.items()]
            results = await asyncio.gather(*tasks)
            
            # 유효한 결과만 모아서 반환
            valid_results = [result for result in results if result is not None]
            return json.dumps(valid_results, indent=4, ensure_ascii=False)
    
    def _run(self, cafe_urls: Dict[str, List[str]]) -> str:
        return asyncio.run(self._arun(cafe_urls))

# cafe_blogs = {
#         "얼스어스": ["https://blog.naver.com/scr02070/223121950899", "https://blog.naver.com/ajy951230/223093046319", "https://blog.naver.com/congsuni04/223236886369"],
#         "반고커피": ["https://blog.naver.com/ordinary_chae/223683617720", "https://blog.naver.com/comiyoun/223611761198"],
# }    
# # url_lists = ["https://blog.naver.com/dannykgu/223574084699","https://blog.naver.com/jmy9927/223514138939","https://blog.naver.com/eodwk44/223675080896"]
# blog_tool = NaverBlogCralwerTool()
# result = await blog_tool._arun(cafe_blogs)
# print(result)
    
class NaverReviewCralwerTool(BaseTool):
    name: str = "NaverReviewCralwer"
    description: str = "네이버 리뷰를 크롤링해 카페 후기 추출"

    async def _fetch_review_data(self, client: httpx.AsyncClient, placeId: str) -> str:
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

        url = f"https://m.place.naver.com/restaurant/{placeId}/home"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Referer": "https://m.place.naver.com/"
        }
        try:        
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # 기본 반환 데이터
            result = {
                "placeId": placeId,
                "url": "정보 없음",
                "business_hour": "정보 없음",
                "category": "정보 없음"
            }
            
            # URL 정보 추출
            try:
                if div_tag := soup.find("div", class_="jO09N"):
                    if a_tag := div_tag.find("a"):
                        result["url"] = a_tag.get("href", "정보 없음")
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
    
                    
#---아래부터 사용하지 않는 툴-------------------------------------------------------------

# from bs4 import BeautifulSoup
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# import asyncio
# import aiohttp       
# import emoji
# from crewai.tools import BaseTool
# import json
# from crewai.tools import BaseTool
# from typing import Type
# from pydantic import BaseModel, Field

# from dotenv import load_dotenv
# import os

# load_dotenv()

# # 네이버 API 관련 환경변수
# AGENT_NAVER_CLIENT_ID = os.getenv("AGENT_NAVER_CLIENT_ID")
# AGENT_NAVER_CLIENT_SECRET = os.getenv("AGENT_NAVER_CLIENT_SECRET")

# class WebDriver:
#     _driver = None
#     _instance = None
    
#     def __new__(cls):
#         if cls._instance is None:
#             cls._instance = super().__new__(cls)
#             cls._instance._initialize_driver()
#         return cls._instance
        
#     def _initialize_driver(self):
#         """WebDriver를 한 번만 초기화"""
#         if WebDriver._driver is None:
#             options = webdriver.ChromeOptions()
#             options.add_argument("--headless")
#             options.add_argument('--no-sandbox')
#             options.add_argument('--disable-dev-shm-usage')
#             options.add_argument("user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Mobile Safari/537.36")
#             WebDriver._driver = webdriver.Chrome(options=options)    

#     def get_driver(self):
#         """WebDriver 인스턴스를 반환하는 메서드"""
#         return WebDriver._driver        

#     def quit_driver(self):
#         """WebDriver 종료 메서드"""
#         if WebDriver._driver:
#             WebDriver._driver.quit()
#             WebDriver._driver = None
         
# def cafe_list_crawler(query):
#     """
#     네이버 지도에서 카페 정보를 크롤링하는 함수
#     Args:
#         query (str): 검색어
#     Returns:
#         list: 카페 정보 리스트
#     """
#     web_driver_instance = WebDriver()
#     driver = web_driver_instance.get_driver() 
#     spots_info = []
    
#     try:
#         url = f"https://m.map.naver.com/search2/search.naver?query={query}"
#         driver.get(url)

#         # 페이지 로딩 대기
#         WebDriverWait(driver, 10).until(
#             lambda d: d.execute_script("return document.readyState") == "complete"
#         )
      
#         spots = WebDriverWait(driver, 10).until(
#             EC.visibility_of_all_elements_located((By.CSS_SELECTOR, "li._lazyImgContainer")))
                
#         for spot in spots:
#             placeId = spot.get_attribute("data-id")
#             map_url = f"https://m.place.naver.com/restaurant/{placeId}/location?filter=location&selected_place_id={placeId}"
#             url = f"https://m.place.naver.com/restaurant/{placeId}/home"
#             # 테스트 : https://m.place.naver.com/restaurant/1932943275/location?reviewSort=recent&filter=location&selected_placeId=1932943275

#             try:
#                 address = spot.find_element(By.CLASS_NAME, "item_address").text.strip().replace("주소보기\n", "")
#             except:
#                 address = "주소 없음"

#             try:
#                 image_url = spot.find_element(By.CLASS_NAME, "_itemThumb").find_element(By.TAG_NAME, "img").get_attribute("src")
#             except:
#                 image_url = "이미지 없음"
                
#             spot_info = {
#                 "placeId": str(placeId),
#                 "kor_name": spot.get_attribute("data-title"),
#                 "address": address,
#                 "url": url,
#                 "image_url": image_url,
#                 "map_url" : map_url,
#                 "latitude": spot.get_attribute("data-latitude"),
#                 "longitude": spot.get_attribute("data-longitude"),
#                 "phone_number": spot.get_attribute("data-tel")
#             }
#             spots_info.append(spot_info)
        
#         print(f"가져온 카페 개수: {len(spots_info)}")
#         return spots_info

#     except Exception as e:
#         print(f"검색 오류 : {e}")
#         return []
    
#     finally:
#         WebDriver().quit_driver()    
        
# async def fetch_review(session, placeId):
#     """
#     비동기 리뷰 스크래퍼. 네이버 지도에서 카페를 정적 크롤링을 통해 검색하고 리뷰를 가져오는 도구.
#     """
#     url = f"https://m.place.naver.com/restaurant/{placeId}/review/visitor?reviewSort=recent"
#     headers = {
#         "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
#         "Referer": "https://m.place.naver.com/"
#     }
    
#     async with session.get(url, headers=headers) as response:
#         if response.status != 200:
#             print(f"{placeId} 요청 실패: {response.status}")
#             return {"placeId": placeId, "reviews": []}

#         html = await response.text()
#         soup = BeautifulSoup(html, "html.parser")
#         reviews = soup.find_all("div", class_="pui__vn15t2")
#         reviews_list = [emoji.replace_emoji(review.text, replace='') for review in reviews]
#         # print(len(reviews_list)) #10개 리뷰
#         return {
#             "placeId": placeId,
#             "reviews": reviews_list
#         }

# async def fetch_business(session, placeId):
#     """
#     비동기 정보 스크래퍼. 네이버 지도에서 카페를 정적 크롤링을 통해 검색하고 정보를 가져오는 도구.
#     """

#     url = f"https://m.place.naver.com/restaurant/{placeId}/home"
#     headers = {
#         "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
#         "Referer": "https://m.place.naver.com/"
#     }
    
#     async with session.get(url, headers=headers) as response:
#         if response.status != 200:
#             print(f"{placeId} 요청 실패: {response.status}")
#             return {"placeId": placeId, "reviews": []}

#         html = await response.text()
#         soup = BeautifulSoup(html, "html.parser")
        
#         try:
#             div_tag = soup.find("div", class_="jO09N")
#             a_tag = div_tag.find("a") if div_tag else None
#             url = a_tag["href"] if a_tag else "정보 없음"

#             business_span = soup.find("span", class_="U7pYf")
#             business_hour = business_span.find("span").text if business_span and business_span.find("span") else "정보 없음"

#         except Exception as e:
#             print(f"Parsing error: {e}")
#             url = "정보 없음"
#             business_hour = "정보 없음"
        
#         return {
#             "placeId": placeId,
#             "url": url,
#             "business_hour": business_hour
#         }
                         
# class QuerySchema(BaseModel):
#     query: str = Field(
#         ..., description="여행 지역 + 카페"
#     )
    
# class GetCafeListTool(BaseTool):
#     """네이버 크롤링을 통해 카페 정보 수집"""
#     name: str = "Cafe List and Information Tool"
#     description: str = """
#     네이버 지도에서 카페를 검색하고 정보를 가져오는 도구입니다.
#     검색이 완료되면 카페 목록을 반환하고 작업을 종료합니다.
#     한 번의 검색으로 충분한 정보를 제공합니다.
#     """
#     args_schema: Type[BaseModel] = QuerySchema
#     _loop = None
    
#     def __init__(self):
#         super().__init__()
#         if self._loop is None:
#             self._loop = asyncio.new_event_loop()
#             asyncio.set_event_loop(self._loop)
    
#     # 리소스 정리        
#     def __del__(self):            
#         if self._loop and not self._loop.is_closed():
#             self._loop.close()

#     async def _collect_reviews(self, cafe_list):
#         async with aiohttp.ClientSession() as session:
#             tasks = [fetch_review(session, cafe["placeId"]) for cafe in cafe_list]
#             return await asyncio.gather(*tasks)
     
#     async def _collect_business_info(self, cafe_list):
#         async with aiohttp.ClientSession() as session:
#             tasks = [fetch_business(session, cafe["placeId"]) for cafe in cafe_list]
#             return await asyncio.gather(*tasks)
            
#     def _run(self, query: str) -> str:
#         try:
#             cafe_list = cafe_list_crawler(query)

#             reviews = self._loop.run_until_complete(self._collect_reviews(cafe_list))
            
#             for cafe, review in zip(cafe_list, reviews):
#                 cafe['reviews'] = review.get('reviews', [])

#             business_info = self._loop.run_until_complete(self._collect_business_info(cafe_list))
            
#             for cafe, info in zip(cafe_list, business_info):
#                 cafe['url'] = info.get('url', '')
#                 cafe['business_hour'] = info.get('business_hour', '')    
            
#             return json.dumps({
#                 "status": "success",
#                 "count": len(cafe_list),
#                 "cafe_list": cafe_list
#             }, ensure_ascii=False)

#         except Exception as e:
#             print(f"Execution error: {e}")
#             return json.dumps({
#                 "status": "error",
#                 "message": str(e)
#             })        


# from crewai.tools import BaseTool

# from pydantic import BaseModel, Field
# from typing import Any, Type
# import json
# import requests
# import os
# from dotenv import load_dotenv

# load_dotenv()
# SERPER_API_KEY = os.getenv("SERPER_API_KEY")
# NAVER_placeId = os.getenv("NAVER_placeId")
# NAVER_PLACE_SECRET = os.getenv("NAVER_PLACE_SECRET")

# class QuerySchema(BaseModel):
#     query: str = Field(
#         ..., description="Mandatory search query for searching places on the map"
#     )
    
# class GoogleMapSearchTool(BaseTool):
#     """구글 맵 검색 API를 사용해 텍스트 정보를 검색"""
#     name: str = "Google MapSearch"
#     description: str = "구글 맵 검색 API를 사용해 텍스트 정보를 검색"
#     args_schema: Type[BaseModel] = QuerySchema
    
#     def _run(self, query: str) -> str:
#         if not SERPER_API_KEY:
#             return "[GoogleMapSearchTool] serper.dev API 자격 증명이 없습니다."

#         payload = json.dumps({
#         "q": query
#         })
        
#         url = "https://google.serper.dev/maps"
#         headers = {
#             "X-API-KEY": os.environ["SERPER_API_KEY"],
#             "content-type": "application/json",
#         }

#         try:
#             with requests.Session() as session:
#                 resp = session.post(url, headers=headers, data=payload)

#             resp.raise_for_status()
#             data = resp.json()
#             places = data.get("places", [])

#             if not places:
#                 return f"[GoogleMapSearchTool] '{query}' 검색 결과 없음."

#             results = []
#             for place in places:
#                 title = place.get("title", "")
#                 address = place.get("address", "")
#                 latitude = place.get("latitude", "")
#                 longitude = place.get("longitude", "")
#                 website = place.get("website", "")                                               
#                 phoneNumber = place.get("phoneNumber", "")
#                 openingHours = place.get("openingHours", "")
#                 thumbnailUrl = place.get("thumbnailUrl", "")                                          
#                 map_url = f"https://www.google.com/maps/place/?q=placeId:{place.get('placeId', '')}"
#                 results.append(f"이름: {title}\n주소: {address}\n위도: {latitude}\n경도: {longitude}\n홈페이지: {website}\n전화번호: {phoneNumber}\n운영시간: {openingHours}\n썸네일: {thumbnailUrl}\n지도주소: {map_url}\n---")

#             return "\n".join(results)

#         except Exception as e:
#             return f"[GoogleMapSearchTool] 에러: {str(e)}"

# # tool = GoogleMapSearchTool()
# # result = tool._run("강남 마들렌")
# # print(result)

# class NaverLocalSearchTool(BaseTool):
#     """네이버 local 검색 API를 사용해 텍스트 정보를 검색"""
#     name: str = "네이버 local Search Tool"
#     description: str = "네이버 local 검색 API를 사용해 카페 정보를 검색"
#     args_schema: Type[BaseModel] = QuerySchema
    
#     def _run(self, query, display=1, start=1, sort="random")-> str:
        
#         search_url = "https://openapi.naver.com/v1/search/local.json"
#         headers = {
#             "X-Naver-Client-Id": NAVER_placeId,
#             "X-Naver-Client-Secret": NAVER_PLACE_SECRET,
#         }

#         params = {
#             "query": query,
#             "display": display,
#             "start": start,
#             "sort": sort,
#         }

#         with requests.Session() as session:
#             response = session.get(search_url, headers=headers, params=params)

#         results = []
#         if response.status_code == 200:
#             result = response.json()
#             cafes = result.get("items",[])
  
#             if not cafes:  # 검색 결과가 없으면 오류 방지
#                 return f"[NaverLocalSearchTool] '{query}'에 대한 검색 결과가 없습니다."

#             # 첫 번째 결과가 있는지 확인 후 접근
#             first_cafe = cafes[0] if len(cafes) > 0 else {}

#             title = first_cafe.get('title', '정보 없음')
#             address = first_cafe.get('roadAddress', '정보 없음')
#             url = first_cafe.get('link', '정보 없음')
  
#             results.append(f"이름: {title}\n주소: {address}\n웹사이트: {url}---")
#             return "\n".join(results)

#         else:
#             print("Error:", response.status_code, response.text)
#             return None
    

# # tool = HomeURLSearchTool()
# # result = tool._run("강남 마들마들")
# # print(result)
# from pydantic import BaseModel
# from typing import Type


# class MultiToolWrapper(BaseTool):
#     """두 개의 툴을 동시에 실행하는 툴"""
#     name: str = "Multi Tool Wrapper"
#     description: str = "크로스체크를 위해 google map과 naver local api를 이용하는 툴"
#     args_schema: Type[BaseModel] = QuerySchema
    
#     def __init__(self, google_tool: GoogleMapSearchTool, naver_tool: NaverLocalSearchTool):
#         super().__init__()
#         self._google_tool = google_tool 
#         self._naver_tool = naver_tool
        
#     def _run(self, query: str) -> str:
#         google_search_result = self._google_tool._run(query)
#         naver_search_result = self._naver_tool._run(query)
        
#         return f"구글 맵 검색 결과:\n{google_search_result}\n\n 네이버 로컬 검색 결과:\n{naver_search_result}"



