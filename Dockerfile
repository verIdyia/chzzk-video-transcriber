FROM nvidia/cuda:12.8.0-devel-ubuntu22.04

# Python 설치
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    && ln -s /usr/bin/python3 /usr/bin/python

# 추가 패키지 설치
RUN apt-get install -y \
    ffmpeg \
    git \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 파일 복사 및 설치
COPY requirements.txt .

# 1단계: PyTorch 먼저 설치 (의존성 충돌 방지)
# RTX 5090 지원을 위한 CUDA 12.8 우선 설치
RUN pip install --pre --index-url https://download.pytorch.org/whl/nightly/cu128 torch torchaudio torchvision || \
    echo "CUDA 12.8 nightly failed, trying alternatives..." && \
    pip install --pre --index-url https://download.pytorch.org/whl/nightly/cu126 torch torchaudio torchvision || \
    echo "CUDA 12.6 nightly failed, trying stable..." && \
    pip install torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu126 || \
    echo "All CUDA versions failed, installing CPU version..." && \
    pip install torch torchaudio torchvision

# 2단계: 기본 패키지 설치
RUN pip install --no-cache-dir streamlit ffmpeg-python requests tqdm

# 3단계: PyTorch 기반 패키지 설치 (의존성 충돌 방지)
RUN pip install --no-cache-dir openai-whisper --no-deps || pip install openai-whisper
RUN pip install --no-cache-dir pyannote.audio --no-deps || pip install pyannote.audio

# 4단계: 누락된 필수 의존성 수동 설치
RUN pip install numpy typing_extensions scipy librosa soundfile asteroid-filterbanks speechbrain torchmetrics lightning pytorch-lightning tiktoken einops

# 5단계: pyannote.audio 의존성 완성
RUN pip install omegaconf "pyannote.core>=5.0.0" "pyannote.database>=5.0.1" "pyannote.metrics>=3.2" "pyannote.pipeline>=3.0.1" "pytorch-metric-learning>=2.1.0" "rich>=12.0.0" "semver>=3.0.0" tensorboardX "torch-audiomentations>=0.11.0"

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