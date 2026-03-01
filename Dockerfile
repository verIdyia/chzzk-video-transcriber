FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04

# Python 설치
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    && ln -sf /usr/bin/python3 /usr/bin/python

# 추가 패키지 설치
RUN apt-get install -y \
    ffmpeg \
    git \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 파일 복사
COPY requirements.txt .

# 1단계: PyTorch 설치
# CUDA 12.8 (블랙웰 RTX 50시리즈 지원) → CUDA 12.6 폴백 (구형 GPU) → CPU 폴백
RUN pip install torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu128 || \
    echo "CUDA 12.8 failed, trying CUDA 12.6..." && \
    pip install torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu126 || \
    echo "All CUDA versions failed, installing CPU version..." && \
    pip install torch torchaudio torchvision

# 2단계: 기본 패키지 설치
RUN pip install --no-cache-dir streamlit ffmpeg-python requests tqdm

# 3단계: faster-whisper 설치 (openai-whisper 대체, 4배 빠름)
RUN pip install --no-cache-dir faster-whisper

# 4단계: 화자분리 - 토큰 불필요 옵션
RUN pip install --no-cache-dir simple-diarizer
RUN pip install --no-cache-dir "git+https://github.com/wenet-e2e/wespeaker.git" || true

# 5단계: 화자분리 - pyannote (HuggingFace 토큰 필요, 선택사항)
RUN pip install --no-cache-dir pyannote.audio --no-deps || true
RUN pip install --no-cache-dir omegaconf "pyannote.core>=5.0.0" "pyannote.database>=5.0.1" \
    "pyannote.pipeline>=3.0.1" "rich>=12.0.0" "semver>=3.0.0" tensorboardX || true

# 6단계: 추가 의존성
RUN pip install --no-cache-dir numpy scipy librosa soundfile

# 애플리케이션 파일 복사
COPY video_transcriber.py .
COPY app.py .
COPY config_manager.py .
COPY chzzk_downloader.py .
COPY audio_processor.py .
COPY utils.py .

# 데이터 디렉토리 생성 및 권한 설정
RUN mkdir -p /app/downloads /app/config && \
    chmod -R 777 /app/downloads /app/config

# 포트 노출
EXPOSE 8501

# 환경변수 설정
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# 헬스체크 추가
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health

# Streamlit 실행
CMD ["streamlit", "run", "video_transcriber.py"]
