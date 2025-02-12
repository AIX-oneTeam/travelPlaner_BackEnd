from typing import List
from crewai import Agent, Task, Crew, LLM, Process
from app.dtos.spot_models import spots_pydantic,calculate_trip_days
from app.services.agents.naver_map_crawler import GetCafeListTool
from app.services.agents.travel_all_schedule_agent_service import spots_pydantic, calculate_trip_days
from pydantic import BaseModel
import os
from dotenv import load_dotenv
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        
class CafeAgentService:
    """
    카페 에이전트 인스턴스를 싱글톤 패턴으로 관리하는 클래스
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CafeAgentService, cls).__new__(cls)
            cls._instance.initialize()  # 최초 한 번만 초기화
        return cls._instance  # 동일한 인스턴스 반환

    def initialize(self):
        """CrewAI 관련 객체들을 한 번만 생성"""
        print("cafe agent를 초기화합니다")
                
        self.llm = LLM(
            model="gpt-4o-mini",
            api_key=OPENAI_API_KEY,
            temperature=0,
            max_tokens=4000
        )
        self.get_cafe_list_tool = GetCafeListTool()

        # 에이전트 정의
        self.researcher = Agent(
            role="카페 정보 검색 및 분석 전문가",
            goal="고객 선호도를 분석해 최적의 카페를 찾을 수 있는 검색어를 추출하고, 정보 수집 후 각 카페의 주요 특징 분석",
            backstory="""
            사용자의 여행을 특별하게 만들기 위해, 최적의 카페를 찾고 카페의 매력을 심층 분석하여 사용자가 최적의 선택을 할 수 있도록 하세요.
            """,
            tools=[self.get_cafe_list_tool],
            allow_delegation=False,
            max_iter=1,
            llm=self.llm,
            verbose=True,
            stop_on_failure=True
        )
        
        self.crew = None   
        
    async def cafe_agent(self, user_input, user_prompt=""):
        """
        CrewAI를 실행하여 사용자 맞춤 카페를 추천하는 서비스
        """
        if user_input is None:
            raise ValueError("user_input이 없습니다. 잘못된 요청을 보냈는지 확인해주세요")
        
        user_input["concepts"] = ', '.join(user_input.get('concepts',''))
        user_input["user_prompt"] = user_prompt
        user_input["n"] = calculate_trip_days(user_input.get('start_date',''),user_input.get('end_date',''))*2
        
        # 태스크 정의(user_input에 다라 값이 바뀌므로 __init__밖에 설정)
        researcher_task = Task(
            description="""
            고객의 정보를 반영한 {n}개의 카페 정보를 반환해주세요.
            tool 사용시 검색어는 "{main_location} 카페"를 입력해주세요
            description에는 카페의 리뷰를 분석해 사람들이 공통적으로 좋아했던 카페의 주요 특징과 메뉴 이름을 포함해 간략히 적어주세요.
            
            고객의 선호도({concepts})와 요구사항({user_prompt})에 "프랜차이즈"가 포함되지 않는 경우, 프랜차이즈 카페는 제외해주세요.
            프랜차이즈 카페 : 스타벅스, 투썸플레이스, 이디야, 빽다방, 메가커피 등 전국에 매장이 5개 이상인 커피 전문점 
 
            고객의 요구사항({user_prompt}), 여행 컨셉({concepts}), 주 연령대({ages})를 반영해 우선 순위를 정하고 우선 순위가 높은 카페를 반환해주세요.    
            부정적인 의견이 있으면 선택하지 마세요.
            
            모르는 정보는 지어내지 말고 "정보 없음"으로 작성하세요.
            """,
            expected_output="""
            서로 다른 {n}개의 카페 정보를 반환하세요.
            """,        
            agent=self.researcher,
            output_json=spots_pydantic
        )

        # 멀티 에이전트 시스템 설정
        crew = Crew(
            agents=[self.researcher],
            tasks=[researcher_task],
            process=Process.sequential,
            verbose=True
        )

        # 실행
        try:
            result = await crew.kickoff_async(inputs=user_input)
            print(result)
            return result.json_dict.get("spots",[])
        except Exception as e:
            print(f"Error during execution: {e}")

            # 오류가 발생한 경우 Observation을 직접 확인
            if hasattr(e, 'Observation'):
                print(f"Tool Output (Observation): {e.Observation}")