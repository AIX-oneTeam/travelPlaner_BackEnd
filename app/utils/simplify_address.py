"""
검색을 위해 주소를 간소화 해주는 함수
예: 부산광역시 - 강서구 → 부산 강서
"""
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
        
def simplify_address(region: str) -> str:
    # 먼저 입력 문자열에 "-"가 포함되어 있으면 "-"로, 없으면 공백을 기준으로 분리합니다.
    if "-" in region:
        parts = [p.strip() for p in region.split("-")]
        if parts[0] == parts[1]:
            province_str = parts[0]
            province_short = shorten_province(province_str)
            return province_short  # 시/도만 반환
    else:
        parts = region.split(maxsplit=1)
        parts = [p.strip() for p in parts]

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


# print(simplify_address("부산광역시 - 부산광역시"))