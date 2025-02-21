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

# 테스트
test_cases = [
    "부산광역시 -  부산광역시",
    "강원특별자치도 - 강릉시",
    "서울특별시 - 강남구",
    "경상남도 - 창원시",
    "경남"
]

valid_prefixes =  validate_address("전북특별자치도 - 여수시")
print(valid_prefixes )
valid_results = [{"address": "전북특별자치도 여수시"},{"address": "전북 여수시"}, {"address": "전라북도 여수시"}]
filtered_results = []
for place_data in valid_results:
    addr = place_data.get("address", "")
    if any(addr.startswith(prefix) for prefix in valid_prefixes):
        filtered_results.append(place_data)
    else:
        print(f"주소 '{addr}'가 유효 접두어 {valid_prefixes} 중 하나로 시작하지 않아 필터링됨.")

print(filtered_results)
    