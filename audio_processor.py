"""
Audio processing module for transcription and speaker diarization.
"""
import ffmpeg
import whisper
import torch
import time
from typing import Optional, Tuple, Dict, Any, List
from utils import format_time

try:
    from pyannote.audio import Pipeline
    PYANNOTE_AVAILABLE = True
except ImportError:
    PYANNOTE_AVAILABLE = False

try:
    import streamlit as st
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False


class AudioProcessor:
    """Handles audio extraction, transcription, and speaker diarization."""
    
    def __init__(self, whisper_model: str = "base", hf_token: Optional[str] = None, use_gpu: bool = True):
        """
        Initialize audio processor.
        
        Args:
            whisper_model: Whisper model name
            hf_token: HuggingFace token for speaker diarization
            use_gpu: Whether to use GPU acceleration
        """
        self.whisper_model = whisper_model
        self.hf_token = hf_token
        self.use_gpu = use_gpu
        self.device = self._get_device()
        self.whisper = None
        self.diarization_pipeline = None

    def _get_device(self) -> str:
        """
        Determine the best available device for processing.
        
        Returns:
            Device string ('cuda', 'mps', or 'cpu')
        """
        if not self.use_gpu:
            return "cpu"
        
        if torch.cuda.is_available():
            return "cuda"
        elif torch.backends.mps.is_available():  # Apple Silicon Mac
            return "mps"
        else:
            return "cpu"

    def get_device_info(self) -> str:
        """
        Get device information string for display.
        
        Returns:
            Device information string
        """
        if self.device == "cuda" and torch.cuda.is_available():
            return f"CUDA ({torch.cuda.get_device_name(0)})"
        elif self.device == "mps":
            return "MPS (Apple Silicon)"
        else:
            return "CPU"

    def load_models(self) -> None:
        """Load Whisper and speaker diarization models."""
        # Load Whisper model
        if self.whisper is None:
            if STREAMLIT_AVAILABLE:
                st.info(f"Whisper 모델 로딩 중... (디바이스: {self.device})")
            
            self.whisper = whisper.load_model(self.whisper_model, device=self.device)
        
        # Load speaker diarization model if token provided
        if self.diarization_pipeline is None and self.hf_token and PYANNOTE_AVAILABLE:
            try:
                if STREAMLIT_AVAILABLE:
                    st.info(f"화자분리 모델 로딩 중... (디바이스: {self.device})")
                
                self.diarization_pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=self.hf_token
                )
                
                # Move to GPU if available
                if self.use_gpu and torch.cuda.is_available():
                    self.diarization_pipeline = self.diarization_pipeline.to(torch.device("cuda"))
                    
            except Exception as e:
                if STREAMLIT_AVAILABLE:
                    st.warning(f"화자분리 모델 로드 실패: {str(e)}")

    def extract_audio(self, video_path: str, audio_path: str) -> Tuple[bool, str]:
        """
        Extract audio from video file.
        
        Args:
            video_path: Path to input video file
            audio_path: Path to output audio file
            
        Returns:
            Tuple of (success, message)
        """
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

    def perform_diarization(self, audio_path: str) -> Optional[Any]:
        """
        Perform speaker diarization on audio file.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Diarization result or None if failed
        """
        if not self.diarization_pipeline or not PYANNOTE_AVAILABLE:
            return None
        
        try:
            # Check audio file
            try:
                import torchaudio
                waveform, sample_rate = torchaudio.load(audio_path)
                duration = waveform.shape[1] / sample_rate
                
                if STREAMLIT_AVAILABLE:
                    st.info(f"화자분리 시작 - 길이: {duration:.1f}초, 샘플레이트: {sample_rate}Hz")
            except ImportError:
                if STREAMLIT_AVAILABLE:
                    st.info("화자분리 시작...")
            
            # Perform diarization with optimized parameters
            diarization = self.diarization_pipeline(
                audio_path,
                min_speakers=1  # Only set minimum speakers
            )
            
            # Log results
            speakers = set()
            for _, _, speaker in diarization.itertracks(yield_label=True):
                speakers.add(speaker)
            
            if STREAMLIT_AVAILABLE:
                st.info(f"화자분리 완료 - 감지된 화자 수: {len(speakers)}")
            
            return diarization
            
        except Exception as e:
            if STREAMLIT_AVAILABLE:
                st.warning(f"화자분리 실패: {str(e)}")
            return None

    def transcribe_with_whisper(self, audio_path: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Transcribe audio using Whisper.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Tuple of (transcription_result, error_message)
        """
        try:
            # Configure transcription options
            transcribe_options = {
                "language": "ko",
                "fp16": self.device == "cuda"  # Use FP16 for CUDA acceleration
            }
            
            result = self.whisper.transcribe(audio_path, **transcribe_options)
            return result, None
            
        except Exception as e:
            return None, f"음성인식 실패: {str(e)}"

    def create_transcript(self, whisper_result: Dict[str, Any], diarization: Optional[Any] = None) -> str:
        """
        Create formatted transcript from Whisper results and optional diarization.
        
        Args:
            whisper_result: Whisper transcription result
            diarization: Speaker diarization result (optional)
            
        Returns:
            Formatted transcript string
        """
        segments = whisper_result['segments']
        
        if diarization is None:
            # Basic transcript without speaker diarization
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
            
            # Find speaker for this time segment
            raw_speaker = self._find_speaker_at_time(diarization, start_time, end_time)
            
            # Map speaker to friendly name
            if raw_speaker not in speaker_mapping:
                speaker_mapping[raw_speaker] = f"화자{next_speaker_id}"
                next_speaker_id += 1
            
            speaker = speaker_mapping[raw_speaker]
            
            start_time_str = format_time(start_time)
            end_time_str = format_time(end_time)
            transcript.append(f"[{start_time_str} - {end_time_str}] {speaker}: {text}")
        
        # Log speaker mapping
        if STREAMLIT_AVAILABLE:
            st.info(f"화자 매핑: {len(speaker_mapping)}명 ({', '.join(speaker_mapping.values())})")
        
        return "\n".join(transcript)

    def _find_speaker_at_time(self, diarization: Any, start_time: float, end_time: float) -> str:
        """
        Find the most likely speaker for a given time segment.
        
        Args:
            diarization: Diarization result
            start_time: Segment start time
            end_time: Segment end time
            
        Returns:
            Speaker identifier
        """
        best_overlap = 0
        best_speaker = "UNKNOWN"
        
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            # Calculate overlap
            overlap_start = max(turn.start, start_time)
            overlap_end = min(turn.end, end_time)
            overlap = max(0, overlap_end - overlap_start)
            
            # Select speaker with most overlap
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = speaker
        
        return best_speaker

    def create_srt_transcript(self, whisper_result: Dict[str, Any], diarization: Optional[Any] = None) -> str:
        """
        Create SRT format transcript.
        
        Args:
            whisper_result: Whisper transcription result
            diarization: Speaker diarization result (optional)
            
        Returns:
            SRT formatted transcript string
        """
        segments = whisper_result['segments']
        srt_content = []
        
        # Speaker mapping for diarization
        speaker_mapping = {}
        next_speaker_id = 1
        
        for i, segment in enumerate(segments, 1):
            start_time = segment['start']
            end_time = segment['end']
            text = segment['text'].strip()
            
            # Add speaker prefix if diarization is available
            if diarization:
                raw_speaker = self._find_speaker_at_time(diarization, start_time, end_time)
                if raw_speaker not in speaker_mapping:
                    speaker_mapping[raw_speaker] = f"화자{next_speaker_id}"
                    next_speaker_id += 1
                speaker = speaker_mapping[raw_speaker]
                text = f"{speaker}: {text}"
            
            # Format timestamps for SRT
            start_srt = self._seconds_to_srt_time(start_time)
            end_srt = self._seconds_to_srt_time(end_time)
            
            srt_content.append(f"{i}")
            srt_content.append(f"{start_srt} --> {end_srt}")
            srt_content.append(text)
            srt_content.append("")  # Empty line between entries
        
        return "\n".join(srt_content)

    def _seconds_to_srt_time(self, seconds: float) -> str:
        """
        Convert seconds to SRT time format (HH:MM:SS,mmm).
        
        Args:
            seconds: Time in seconds
            
        Returns:
            SRT formatted time string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

    def is_diarization_available(self) -> bool:
        """
        Check if speaker diarization is available.
        
        Returns:
            True if diarization can be performed
        """
        return PYANNOTE_AVAILABLE and bool(self.hf_token)