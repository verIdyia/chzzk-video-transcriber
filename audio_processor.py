"""
Audio processing module for transcription and speaker diarization.
Supports faster-whisper (primary) and openai-whisper (fallback).
Supports WeSpeaker (no auth), simple-diarizer (no auth), and pyannote (HuggingFace token).
"""
import ffmpeg
import torch
import time
from typing import Optional, Tuple, Dict, Any, List
from utils import format_time

# Whisper backends
FASTER_WHISPER_AVAILABLE = False
OPENAI_WHISPER_AVAILABLE = False

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    pass

if not FASTER_WHISPER_AVAILABLE:
    try:
        import whisper
        OPENAI_WHISPER_AVAILABLE = True
    except ImportError:
        pass

# Diarization backends
WESPEAKER_AVAILABLE = False
SIMPLE_DIARIZER_AVAILABLE = False
PYANNOTE_AVAILABLE = False

try:
    import wespeaker
    WESPEAKER_AVAILABLE = True
except ImportError:
    pass

try:
    from simple_diarizer.diarizer import Diarizer
    SIMPLE_DIARIZER_AVAILABLE = True
except ImportError:
    pass

try:
    from pyannote.audio import Pipeline
    PYANNOTE_AVAILABLE = True
except ImportError:
    pass

try:
    import streamlit as st
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False


# Whisper model options for UI
WHISPER_MODELS = {
    "large-v3": "최고 정확도 (VRAM ~10GB)",
    "large-v3-turbo": "빠른 속도 + 좋은 정확도 (VRAM ~6GB)",
    "turbo": "빠른 속도 + 좋은 정확도 (VRAM ~6GB)",
    "large-v2": "안정적 정확도 (VRAM ~10GB)",
    "medium": "중간 (VRAM ~5GB)",
    "small": "가벼운 모델 (VRAM ~2GB)",
    "base": "매우 가벼운 모델 (VRAM ~1GB)",
    "tiny": "초경량 (VRAM ~1GB)",
}

# Diarization backend options
DIARIZATION_BACKENDS = {}
if WESPEAKER_AVAILABLE:
    DIARIZATION_BACKENDS["wespeaker"] = "WeSpeaker (토큰 불필요, 추천)"
if SIMPLE_DIARIZER_AVAILABLE:
    DIARIZATION_BACKENDS["simple"] = "Simple Diarizer (토큰 불필요)"
if PYANNOTE_AVAILABLE:
    DIARIZATION_BACKENDS["pyannote"] = "Pyannote (HuggingFace 토큰 필요)"
if not DIARIZATION_BACKENDS:
    DIARIZATION_BACKENDS["none"] = "화자분리 사용 불가 (패키지 미설치)"


class AudioProcessor:
    """Handles audio extraction, transcription, and speaker diarization."""

    def __init__(self, whisper_model: str = "large-v3-turbo",
                 hf_token: Optional[str] = None,
                 diarization_backend: str = "auto",
                 use_gpu: bool = True):
        self.whisper_model_name = whisper_model
        self.hf_token = hf_token
        self.diarization_backend = diarization_backend
        self.use_gpu = use_gpu
        self.device = self._get_device()
        self.whisper = None
        self.diarization_pipeline = None

        # Auto-select diarization backend
        if self.diarization_backend == "auto":
            if WESPEAKER_AVAILABLE:
                self.diarization_backend = "wespeaker"
            elif SIMPLE_DIARIZER_AVAILABLE:
                self.diarization_backend = "simple"
            elif PYANNOTE_AVAILABLE and self.hf_token:
                self.diarization_backend = "pyannote"
            else:
                self.diarization_backend = "none"

    def _get_device(self) -> str:
        if not self.use_gpu:
            return "cpu"
        if torch.cuda.is_available():
            return "cuda"
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def get_device_info(self) -> str:
        if self.device == "cuda" and torch.cuda.is_available():
            return f"CUDA ({torch.cuda.get_device_name(0)})"
        elif self.device == "mps":
            return "MPS (Apple Silicon)"
        return "CPU"

    def get_whisper_backend_info(self) -> str:
        if FASTER_WHISPER_AVAILABLE:
            return "faster-whisper (CTranslate2)"
        elif OPENAI_WHISPER_AVAILABLE:
            return "openai-whisper (PyTorch)"
        return "없음"

    def get_diarization_backend_info(self) -> str:
        return DIARIZATION_BACKENDS.get(self.diarization_backend, "없음")

    def load_models(self) -> None:
        """Load Whisper and speaker diarization models."""
        # Load Whisper
        if self.whisper is None:
            if STREAMLIT_AVAILABLE:
                backend = self.get_whisper_backend_info()
                st.info(f"Whisper 모델 로딩 중... ({self.whisper_model_name}, {backend}, {self.device})")

            if FASTER_WHISPER_AVAILABLE:
                compute_type = "float16" if self.device == "cuda" else "int8"
                self.whisper = WhisperModel(
                    self.whisper_model_name,
                    device=self.device if self.device != "mps" else "cpu",
                    compute_type=compute_type
                )
            elif OPENAI_WHISPER_AVAILABLE:
                self.whisper = whisper.load_model(self.whisper_model_name, device=self.device)

        # Load diarization
        if self.diarization_pipeline is None:
            self._load_diarization_model()

    def _load_diarization_model(self) -> None:
        """Load the selected diarization backend."""
        if self.diarization_backend == "wespeaker":
            try:
                if STREAMLIT_AVAILABLE:
                    st.info("WeSpeaker 화자분리 모델 로딩 중...")
                model = wespeaker.load_model('english')
                if self.device == "cuda":
                    model.set_device('cuda:0')
                self.diarization_pipeline = ("wespeaker", model)
            except Exception as e:
                if STREAMLIT_AVAILABLE:
                    st.warning(f"WeSpeaker 로드 실패: {e}")

        elif self.diarization_backend == "simple":
            try:
                if STREAMLIT_AVAILABLE:
                    st.info("Simple Diarizer 모델 로딩 중...")
                diar = Diarizer(embed_model='ecapa', cluster_method='sc')
                self.diarization_pipeline = ("simple", diar)
            except Exception as e:
                if STREAMLIT_AVAILABLE:
                    st.warning(f"Simple Diarizer 로드 실패: {e}")

        elif self.diarization_backend == "pyannote" and PYANNOTE_AVAILABLE and self.hf_token:
            try:
                if STREAMLIT_AVAILABLE:
                    st.info("Pyannote 화자분리 모델 로딩 중...")
                pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=self.hf_token
                )
                if self.use_gpu and torch.cuda.is_available():
                    pipeline = pipeline.to(torch.device("cuda"))
                self.diarization_pipeline = ("pyannote", pipeline)
            except Exception as e:
                if STREAMLIT_AVAILABLE:
                    st.warning(f"Pyannote 로드 실패: {e}")

    def extract_audio(self, video_path: str, audio_path: str) -> Tuple[bool, str]:
        """Extract audio from video file."""
        try:
            (
                ffmpeg
                .input(video_path)
                .output(audio_path, acodec='pcm_s16le', ac=1, ar='16000')
                .overwrite_output()
                .run(quiet=True)
            )
            return True, "오디오 추출 완료"
        except Exception as e:
            return False, f"오디오 추출 실패: {str(e)}"

    def perform_diarization(self, audio_path: str, num_speakers: Optional[int] = None) -> Optional[List[Dict]]:
        """
        Perform speaker diarization on audio file.
        Returns normalized list of segments: [{'start': float, 'end': float, 'speaker': str}, ...]
        """
        if self.diarization_pipeline is None:
            return None

        backend_type, model = self.diarization_pipeline

        try:
            if backend_type == "wespeaker":
                return self._diarize_wespeaker(model, audio_path)
            elif backend_type == "simple":
                return self._diarize_simple(model, audio_path, num_speakers)
            elif backend_type == "pyannote":
                return self._diarize_pyannote(model, audio_path, num_speakers)
        except Exception as e:
            if STREAMLIT_AVAILABLE:
                st.warning(f"화자분리 실패: {str(e)}")
            return None

    def _diarize_wespeaker(self, model, audio_path: str) -> Optional[List[Dict]]:
        """Diarize using WeSpeaker."""
        if STREAMLIT_AVAILABLE:
            st.info("WeSpeaker 화자분리 진행 중...")

        result = model.diarize(audio_path, 'utterance')
        if not result:
            return None

        # WeSpeaker returns list of (start, end, speaker) tuples
        segments = []
        for item in result:
            if len(item) >= 3:
                segments.append({
                    'start': float(item[0]),
                    'end': float(item[1]),
                    'speaker': str(item[2])
                })

        speakers = set(s['speaker'] for s in segments)
        if STREAMLIT_AVAILABLE:
            st.info(f"화자분리 완료 - 감지된 화자 수: {len(speakers)}")

        return segments

    def _diarize_simple(self, diar, audio_path: str,
                        num_speakers: Optional[int] = None) -> Optional[List[Dict]]:
        """Diarize using simple-diarizer."""
        if STREAMLIT_AVAILABLE:
            st.info("Simple Diarizer 화자분리 진행 중...")

        kwargs = {}
        if num_speakers:
            kwargs['num_speakers'] = num_speakers

        result = diar.diarize(audio_path, **kwargs)

        segments = []
        for seg in result:
            segments.append({
                'start': float(seg['start']),
                'end': float(seg['end']),
                'speaker': str(seg.get('label', 'UNKNOWN'))
            })

        speakers = set(s['speaker'] for s in segments)
        if STREAMLIT_AVAILABLE:
            st.info(f"화자분리 완료 - 감지된 화자 수: {len(speakers)}")

        return segments

    def _diarize_pyannote(self, pipeline, audio_path: str,
                          num_speakers: Optional[int] = None) -> Optional[List[Dict]]:
        """Diarize using pyannote."""
        if STREAMLIT_AVAILABLE:
            st.info("Pyannote 화자분리 진행 중...")

        kwargs = {'min_speakers': 1}
        if num_speakers:
            kwargs['num_speakers'] = num_speakers

        diarization = pipeline(audio_path, **kwargs)

        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append({
                'start': turn.start,
                'end': turn.end,
                'speaker': speaker
            })

        speakers = set(s['speaker'] for s in segments)
        if STREAMLIT_AVAILABLE:
            st.info(f"화자분리 완료 - 감지된 화자 수: {len(speakers)}")

        return segments

    def transcribe_with_whisper(self, audio_path: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Transcribe audio using Whisper. Returns normalized result dict."""
        try:
            if FASTER_WHISPER_AVAILABLE and isinstance(self.whisper, WhisperModel):
                return self._transcribe_faster_whisper(audio_path)
            elif OPENAI_WHISPER_AVAILABLE:
                return self._transcribe_openai_whisper(audio_path)
            else:
                return None, "Whisper 모델이 로드되지 않았습니다."
        except Exception as e:
            return None, f"음성인식 실패: {str(e)}"

    def _transcribe_faster_whisper(self, audio_path: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Transcribe using faster-whisper."""
        segments_gen, info = self.whisper.transcribe(
            audio_path,
            language="ko",
            beam_size=5,
            vad_filter=True
        )

        # Convert generator to list and normalize to openai-whisper format
        segments = []
        full_text_parts = []
        for seg in segments_gen:
            segments.append({
                'start': seg.start,
                'end': seg.end,
                'text': seg.text
            })
            full_text_parts.append(seg.text.strip())

        result = {
            'segments': segments,
            'text': ' '.join(full_text_parts),
            'language': info.language
        }
        return result, None

    def _transcribe_openai_whisper(self, audio_path: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Transcribe using openai-whisper (fallback)."""
        transcribe_options = {
            "language": "ko",
            "fp16": self.device == "cuda"
        }
        result = self.whisper.transcribe(audio_path, **transcribe_options)
        return result, None

    def create_transcript(self, whisper_result: Dict[str, Any],
                          diarization: Optional[List[Dict]] = None) -> str:
        """Create formatted transcript from Whisper results and optional diarization."""
        segments = whisper_result['segments']

        if diarization is None:
            transcript = []
            for segment in segments:
                start_time = format_time(segment['start'])
                end_time = format_time(segment['end'])
                text = segment['text'].strip()
                transcript.append(f"[{start_time} - {end_time}] {text}")
            return "\n".join(transcript)

        # Transcript with speaker diarization
        speaker_mapping = {}
        next_speaker_id = 1

        transcript = []
        for segment in segments:
            start_time = segment['start']
            end_time = segment['end']
            text = segment['text'].strip()

            raw_speaker = self._find_speaker_at_time(diarization, start_time, end_time)

            if raw_speaker not in speaker_mapping:
                speaker_mapping[raw_speaker] = f"화자{next_speaker_id}"
                next_speaker_id += 1

            speaker = speaker_mapping[raw_speaker]
            start_time_str = format_time(start_time)
            end_time_str = format_time(end_time)
            transcript.append(f"[{start_time_str} - {end_time_str}] {speaker}: {text}")

        if STREAMLIT_AVAILABLE:
            st.info(f"화자 매핑: {len(speaker_mapping)}명 ({', '.join(speaker_mapping.values())})")

        return "\n".join(transcript)

    def _find_speaker_at_time(self, diarization: List[Dict],
                              start_time: float, end_time: float) -> str:
        """Find the most likely speaker for a given time segment."""
        best_overlap = 0
        best_speaker = "UNKNOWN"

        for seg in diarization:
            overlap_start = max(seg['start'], start_time)
            overlap_end = min(seg['end'], end_time)
            overlap = max(0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = seg['speaker']

        return best_speaker

    def create_srt_transcript(self, whisper_result: Dict[str, Any],
                              diarization: Optional[List[Dict]] = None) -> str:
        """Create SRT format transcript."""
        segments = whisper_result['segments']
        srt_content = []

        speaker_mapping = {}
        next_speaker_id = 1

        for i, segment in enumerate(segments, 1):
            start_time = segment['start']
            end_time = segment['end']
            text = segment['text'].strip()

            if diarization:
                raw_speaker = self._find_speaker_at_time(diarization, start_time, end_time)
                if raw_speaker not in speaker_mapping:
                    speaker_mapping[raw_speaker] = f"화자{next_speaker_id}"
                    next_speaker_id += 1
                speaker = speaker_mapping[raw_speaker]
                text = f"{speaker}: {text}"

            start_srt = self._seconds_to_srt_time(start_time)
            end_srt = self._seconds_to_srt_time(end_time)

            srt_content.append(f"{i}")
            srt_content.append(f"{start_srt} --> {end_srt}")
            srt_content.append(text)
            srt_content.append("")

        return "\n".join(srt_content)

    def _seconds_to_srt_time(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

    def is_diarization_available(self) -> bool:
        """Check if speaker diarization is available."""
        if self.diarization_backend in ("wespeaker", "simple"):
            return True
        if self.diarization_backend == "pyannote":
            return PYANNOTE_AVAILABLE and bool(self.hf_token)
        return False
