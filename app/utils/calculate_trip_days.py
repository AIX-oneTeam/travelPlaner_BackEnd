
from datetime import datetime
from dateutil import parser

# 동선 에이전트 실행 후 start,end date에 붙은 시간 처리(YYYY-MM-DD로 통일)
def normalize_date(date_str: str) -> datetime.date:
        return parser.isoparse(date_str).date() 

def calculate_trip_days(start_date_str: str, end_date_str: str) -> int:
    start_dt = normalize_date(start_date_str)
    end_dt = normalize_date(end_date_str)
    delta = end_dt - start_dt
    return delta.days + 1