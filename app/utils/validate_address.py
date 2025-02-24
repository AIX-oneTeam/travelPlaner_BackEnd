def get_region_variations(region):
    region_mapping = {
        "강원특별자치도": ["강원특별자치도", "강원도", "강원"],
        "경기도": ["경기도", "경기"],
        "경상남도": ["경상남도", "경남"],
        "경상북도": ["경상북도", "경북"],
        "광주광역시": ["광주광역시", "광주"],
        "대구광역시": ["대구광역시", "대구"],
        "대전광역시": ["대전광역시", "대전"],
        "부산광역시": ["부산광역시", "부산"],
        "서울특별시": ["서울특별시", "서울"],
        "세종특별자치시": ["세종특별자치시", "세종"],
        "울산광역시": ["울산광역시", "울산"],
        "인천광역시": ["인천광역시", "인천"],
        "전라남도": ["전라남도", "전남"],
        "전북특별자치도": ["전북특별자치도", "전북", "전라북도"],
        "제주특별자치도": ["제주특별자치도", "제주", "제주도"],
        "충청남도": ["충청남도", "충남"],
        "충청북도": ["충청북도", "충북"]
    }
    return region_mapping.get(region, [region])

def validate_address(location):
    if "-" in location:
        region1, region2 = [p.strip() for p in location.split("-")]
        
        # 같은 지역명이 반복되는 경우 ("부산광역시 - 부산광역시")
        if region1 == region2:
            return get_region_variations(region1)
            
        # 다른 지역명이 있는 경우 ("강원특별자치도 - 강릉시")
        else:
            variations = get_region_variations(region1)
            return [f"{var} {region2}" for var in variations]
    
    # 하이픈이 없는 경우
    return get_region_variations(location)

# # 테스트
# test_cases = [
#     "부산광역시 -  부산광역시",
#     "강원특별자치도 - 강릉시",
#     "서울특별시 - 강남구",
#     "경상남도 - 창원시",
#     "경남"
# ]

# for case in test_cases:
#     result = validate_address(case)
#     print(f"입력: {case}")
#     print(f"출력: {result}")
#     print()