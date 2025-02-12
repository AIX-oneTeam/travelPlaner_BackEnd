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

