#!/bin/bash

# 영상 트랜스크립트 생성기 Docker 실행 스크립트

echo "🎬 영상 트랜스크립트 생성기 Docker 실행 스크립트"
echo "================================================"

# Docker Compose 명령어 확인 및 설정
DOCKER_COMPOSE_CMD=""
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    echo "❌ Docker Compose를 찾을 수 없습니다."
    echo "Docker와 Docker Compose가 설치되어 있는지 확인해주세요."
    exit 1
fi

echo "📋 사용 중인 Docker Compose: $DOCKER_COMPOSE_CMD"

# GPU 지원 확인
if command -v nvidia-smi &> /dev/null; then
    if nvidia-smi &> /dev/null; then
        echo "🎮 NVIDIA GPU 감지됨"
        echo "🚀 GPU 가속 버전으로 실행합니다."
    else
        echo "⚠️  GPU가 감지되지 않았지만 CUDA 이미지로 실행합니다."
        echo "💡 앱에서 CPU 모드로 설정하세요."
    fi
else
    echo "⚠️  nvidia-smi를 찾을 수 없습니다."
    echo "💡 GPU가 없거나 드라이버가 설치되지 않았습니다."
fi

# 필요한 디렉토리 생성
echo "📁 필요한 디렉토리 생성 중..."
mkdir -p downloads config

# Docker Compose로 서비스 시작
echo "🚀 Docker 컨테이너 시작 중..."
$DOCKER_COMPOSE_CMD up -d --build

# 서비스 상태 확인
echo "⏳ 서비스 시작 대기 중..."
sleep 10

# 헬스체크
echo "🔍 서비스 상태 확인 중..."
if $DOCKER_COMPOSE_CMD ps | grep -q "Up"; then
    echo "✅ 서비스가 성공적으로 시작되었습니다!"
    echo ""
    echo "🌐 웹 인터페이스 접속: http://localhost:8501"
    echo ""
    echo "📋 유용한 Docker 명령어:"
    echo "  - 로그 확인: $DOCKER_COMPOSE_CMD logs -f"
    echo "  - 서비스 정지: $DOCKER_COMPOSE_CMD down"
    echo "  - 서비스 재시작: $DOCKER_COMPOSE_CMD restart"
    echo "  - 컨테이너 상태 확인: $DOCKER_COMPOSE_CMD ps"
else
    echo "❌ 서비스 시작에 실패했습니다."
    echo "로그를 확인하세요: $DOCKER_COMPOSE_CMD logs"
fi