# 🎬 치지직 영상 트랜스크립트 생성기

치지직(Chzzk) 다시보기 영상의 특정 구간을 다운로드하고 AI 음성인식으로 트랜스크립트를 생성하는 도구입니다.  
**영상 구간의 채팅도 함께 수집**하여 완전한 콘텐츠 분석이 가능합니다.

## ✨ 주요 기능

### 🎥 영상 처리
- 치지직 다시보기 영상 다운로드
- 정확한 시간 구간 지정 (초 단위)
- 다양한 화질 선택 (4K ~ 360p)
- 성인 인증 영상 지원 (쿠키 인증)

### 🎙️ AI 음성인식
- **OpenAI Whisper** 기반 고품질 음성인식
- **화자분리** 기능 (여러 명이 말할 때 구분)
- GPU 가속 지원 (CUDA/Apple Silicon)
- SRT 자막 파일 생성

### 💬 실시간 채팅 수집
- 영상 구간에 해당하는 **실시간 채팅 자동 수집**
- 타임스탬프 기반 정확한 동기화
- 도네이션/후원 메시지 구분 표시
- 트랜스크립트와 채팅 통합 분석

## 🚀 빠른 시작

### Docker 사용 (강력 권장)

```bash
# 저장소 클론
git clone [repository-url]
cd chzzk-video-transcriber

# Docker Compose로 실행
docker-compose up --build

# 브라우저에서 접속
# http://localhost:8501
```

### 로컬 설치 (고급 사용자용)

⚠️ **중요 주의사항**: 
- **Linux/macOS 환경 권장** - Windows에서는 호환성 문제가 있을 수 있습니다
- **PyTorch 생태계의 복잡한 의존성**으로 인해 Docker 사용을 강력히 권장합니다
- **FFmpeg 경로 문제** 등으로 Windows에서 예상치 못한 오류 발생 가능

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# PyTorch 설치 (CUDA 버전에 맞게)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126

# 나머지 의존성 설치
pip install streamlit ffmpeg-python requests tqdm
pip install numpy scipy soundfile librosa tiktoken einops
pip install openai-whisper pyannote.audio

# 애플리케이션 실행
streamlit run video_transcriber.py
```

## 📖 사용 방법

### 1. 기본 설정 (사이드바)
- **다운로드 경로**: 파일 저장 위치 설정
- **Whisper 모델**: 음성인식 정확도 선택 
  - **권장**: medium (RTX 3060+ 필요)
  - **최고품질**: large-v3 (RTX 4070+ 필요)
  - **저사양**: small (GTX 1660+ 가능)
- **네이버 쿠키**: 성인 인증용 (필요시)
- **HuggingFace 토큰**: 화자분리용 (선택사항)

### 2. 영상 정보 입력
- **치지직 URL**: 다시보기 영상 주소 입력
- **시간 구간**: 시작/종료 시간 (HH:MM:SS 형식)
- **옵션 선택**: 화자분리, 채팅 수집 여부

### 3. 처리 및 결과
- "트랜스크립트 생성" 버튼 클릭
- 진행 상황 실시간 확인
- 완료 후 파일 다운로드

## 📋 사용 예시

### 입력
```
URL: https://chzzk.naver.com/video/1234567890
시작 시간: 00:15:30
종료 시간: 00:18:45
채팅 수집: ✅ 체크
```

### 출력 파일
- **트랜스크립트**: 음성인식 결과 + 채팅 로그
- **채팅 파일**: 구간별 채팅만 별도 저장

### 채팅 로그 형식
```
[00:15:35] [닉네임123] : ㅋㅋㅋㅋ 이거 진짜 웃기네
[00:15:42] [도네이션] [후원자] : 1000원 후원! 안녕하세요~
[00:15:55] [시청자456] : 이 부분 다시 볼래요
```

## 🔧 고급 설정

### 네이버 쿠키 설정 (성인 인증용)
1. 치지직에 로그인한 브라우저에서 F12 개발자 도구 열기
2. Application → Cookies → chzzk.naver.com
3. `NID_AUT`, `NID_SES` 값 복사
4. 형식: `NID_AUT=값; NID_SES=값;`

### HuggingFace 토큰 (화자분리용)
1. [huggingface.co](https://huggingface.co) 가입
2. Settings → Access Tokens → New token
3. pyannote/speaker-diarization 모델 접근 권한 필요

### GPU 설정 및 Whisper 모델 권장사항

#### NVIDIA GPU
| 모델 | VRAM 요구량 | 처리 속도 | 정확도 | 권장 GPU |
|------|-------------|-----------|--------|-----------|
| tiny | ~1GB | 매우 빠름 | 낮음 | GTX 1050+ |
| base | ~1GB | 빠름 | 보통 | GTX 1060+ |
| small | ~2GB | 보통 | 좋음 | GTX 1660+ |
| medium | ~5GB | 느림 | 매우 좋음 | RTX 3060+ |
| large-v2 | ~10GB | 매우 느림 | 최고 | RTX 3080+ |
| large-v3 | ~10GB | 매우 느림 | 최고 | RTX 4070+ |

#### 기타 설정
- **Apple Silicon**: MPS 자동 감지 (M1/M2/M3 통합 메모리 사용)
- **CPU 전용**: 자동 폴백 (매우 느림, 16GB+ RAM 권장)

## 📁 프로젝트 구조

```
├── app.py                    # 메인 Streamlit 애플리케이션
├── video_transcriber.py      # 실행 진입점
├── config_manager.py         # 설정 관리
├── chzzk_downloader.py       # 치지직 다운로더
├── audio_processor.py        # 음성 처리
├── utils.py                  # 유틸리티 함수
├── Dockerfile                # Docker 설정
├── docker-compose.yml        # Docker Compose 설정
└── requirements.txt          # Python 의존성 (참조용)
```

## 🔍 지원 형식

### 입력
- 치지직 다시보기 URL (모든 형식)
- 시간: HH:MM:SS, MM:SS, 초 단위
- 영상: 모든 화질 (자동/수동 선택)

### 출력
- **TXT**: 타임스탬프 + 내용 + 채팅
- **SRT**: 자막 파일 + 별도 채팅 파일
- **인코딩**: UTF-8 (한글 완벽 지원)

## ⚠️ 주의사항

### 시스템 요구사항

#### 운영체제
- **권장**: Linux (Ubuntu 20.04+), macOS (Intel/Apple Silicon)
- **제한적 지원**: Windows (Docker Desktop 사용 권장)
- **Docker**: 모든 플랫폼에서 안정적 동작 보장

#### 하드웨어
- **메모리**: 최소 8GB RAM (16GB 권장, CPU 사용 시 32GB+ 권장)
- **저장공간**: 영상 크기의 2배 이상
- **GPU**: 
  - **일반 사용**: GTX 1660+ (4GB VRAM)
  - **고품질**: RTX 3060+ (8GB VRAM) 
  - **최고 품질**: RTX 3080+ (12GB VRAM)
- **Docker**: nvidia-docker2 설치 필요 (GPU 사용 시)

### ⚠️ 중요 사용 제한
- **개인/연구/교육 목적으로만 사용**
- **상업적 이용 금지**
- **저작권 보호 콘텐츠 다운로드 금지**
- **치지직 서비스 약관 준수 필요**
- **과도한 API 호출로 인한 서버 부하 방지**
- **콘텐츠 제작자의 권리 존중**

### 문제 해결
- **쿠키 오류**: 브라우저에서 최신 쿠키 재복사
- **다운로드 실패**: URL 및 시간 구간 확인
- **GPU 미인식**: Docker 환경에서 nvidia-docker 설치
- **메모리 부족**: 더 작은 Whisper 모델 선택

## 🛠️ 개발 정보

### 기술 스택
- **Frontend**: Streamlit
- **AI**: OpenAI Whisper, pyannote.audio
- **Video**: FFmpeg, requests (직접 스트림 다운로드)
- **Backend**: Python 3.10+

### 의존성 관리
- Docker의 복잡한 설치 순서로 의존성 충돌 해결
- CUDA 버전별 폴백 체인 구현
- 선택적 의존성 지원 (GPU/CPU 자동 감지)

## 📝 라이선스 및 면책조항

### 라이선스
이 소프트웨어는 MIT 라이선스 하에 배포됩니다.

### ⚠️ 중요 면책조항
- 이 도구는 **연구 및 교육 목적**으로만 제공됩니다
- **치지직 서비스의 비공식 API**를 사용하며, 서비스 변경 시 작동하지 않을 수 있습니다
- **사용자는 관련 법률 및 서비스 약관을 준수할 책임**이 있습니다
- **저작권 침해, 서비스 약관 위반 등의 책임은 사용자에게 있습니다**
- 개발자는 이 도구의 사용으로 인한 어떠한 법적 문제에도 책임지지 않습니다

### 권장사항
- 본인이 제작한 콘텐츠 또는 명시적 허가받은 콘텐츠만 처리하세요
- 공정 이용(Fair Use) 범위 내에서만 사용하세요

## 🙏 참고 및 감사

### 참고한 오픈소스 프로젝트
이 프로젝트는 다음 오픈소스 프로젝트들을 참고하여 개발되었습니다:

- **[chzzk-vod-downloader](https://github.com/321098123/chzzk-vod-downloader)** - 치지직 다운로드 기본 구조 참고
- **[ChzzkChat](https://github.com/Buddha7771/ChzzkChat)** - 채팅 수집 로직 참고
- **[chzzk-vod-downloader-v2](https://github.com/honey720/chzzk-vod-downloader-v2)** - 개선된 다운로드 방식 참고

### 개발 도구
- **[Claude Code](https://claude.ai/code)** - 코드 리팩토링 및 아키텍처 설계
- **[Google Gemini](https://gemini.google.com)** - 코드 최적화 및 문제 해결

### 오픈소스 라이브러리
- **[OpenAI Whisper](https://github.com/openai/whisper)** - 음성인식
- **[pyannote.audio](https://github.com/pyannote/pyannote-audio)** - 화자분리
- **[Streamlit](https://streamlit.io)** - 웹 인터페이스
- **[FFmpeg](https://ffmpeg.org)** - 미디어 처리

## 🤝 기여하기

이슈나 개선 사항이 있으시면 GitHub Issues를 통해 제보해 주세요.

---

**Made with ❤️ for Content Creators and Researchers**  
*Built with AI assistance and community contributions*