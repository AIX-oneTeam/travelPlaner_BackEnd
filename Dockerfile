# 빌드
FROM python:3.12-slim as builder

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# 최종 빌드
FROM python:3.12-slim

# 작업 디렉토리 설정
WORKDIR /app

# Build Stage에서 설치된 패키지만 복사
COPY --from=builder /install /usr/local

# 애플리케이션 파일 복사
COPY . .

# 기본 명령어
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]