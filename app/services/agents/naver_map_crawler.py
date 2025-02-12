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
