def extract_spots(data):
    all_spots = []

    # restaurant 섹션
    if 'restaurant' in data:
        for spot in data['restaurant'].get('spots', []):
            if 'kor_name' in spot:
                all_spots.append(spot)

    # site 섹션
    if 'site' in data:
        for spot in data['site']:
            if 'kor_name' in spot:
                all_spots.append(spot)

    # cafe 섹션
    if 'cafe' in data:
        for spot in data['cafe'].get('spots', []):
            if 'kor_name' in spot:
                all_spots.append(spot)

    # accommodation 섹션
    if 'accommodation' in data:
        for spot in data['accommodation']:
            if 'kor_name' in spot:
                all_spots.append(spot)

    return all_spots