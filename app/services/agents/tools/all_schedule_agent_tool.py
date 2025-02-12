import numpy as np
from typing import List, Dict
from geopy.distance import geodesic
from crewai.tools import BaseTool

class HaversineRouteOptimizer(BaseTool):
    """하버사인 공식을 활용하여 최적 방문 경로를 계산하는 도구"""

    name: str = "HaversineRouteOptimizer"
    description: str = "여행 일정에서 주어진 장소들의 최적 방문 순서를 거리 기반으로 제공합니다."

    def _run(self, spots: List[Dict]) -> List[Dict]:
        """주어진 장소들의 최적 방문 순서를 거리 기반으로 정렬"""
        if len(spots) < 2:
            return {"error": "최소 두 개 이상의 장소가 필요합니다."}

        # 모든 장소의 위도(latitude)와 경도(longitude) 리스트 추출
        locations = [(spot["latitude"], spot["longitude"]) for spot in spots]

        # 거리 행렬 계산
        distance_matrix = self._compute_distance_matrix(locations)

        # 최적 방문 순서 결정 (탐욕적 알고리즘)
        optimal_order = self._compute_optimal_route(distance_matrix)

        # 최적 순서대로 spots 정렬
        optimized_spots = [spots[i] for i in optimal_order]

        return optimized_spots

    def _compute_distance_matrix(self, locations: List[tuple]) -> np.ndarray:
        """위도, 경도 정보를 이용하여 거리 행렬 생성"""
        num_locations = len(locations)
        distance_matrix = np.zeros((num_locations, num_locations))

        for i in range(num_locations):
            for j in range(i + 1, num_locations):
                distance = geodesic(locations[i], locations[j]).kilometers  # 하버사인 거리(km)
                distance_matrix[i][j] = distance
                distance_matrix[j][i] = distance  # 대칭 행렬

        return distance_matrix

    def _compute_optimal_route(self, distance_matrix: np.ndarray) -> List[int]:
        """탐욕적(Greedy) 방법으로 최적 방문 순서를 계산"""
        num_locations = len(distance_matrix)
        visited = [False] * num_locations
        route = [0]  # 첫 번째 장소부터 시작
        visited[0] = True

        for _ in range(num_locations - 1):
            last_visited = route[-1]
            nearest = None
            nearest_distance = float("inf")

            # 가장 가까운 미방문 장소 찾기
            for i in range(num_locations):
                if not visited[i] and distance_matrix[last_visited][i] < nearest_distance:
                    nearest = i
                    nearest_distance = distance_matrix[last_visited][i]

            if nearest is not None:
                route.append(nearest)
                visited[nearest] = True

        return route
