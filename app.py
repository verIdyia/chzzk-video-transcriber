"""
Main Streamlit application for video transcription.
"""
import streamlit as st
import os
import torch
import requests
import json
import time
from typing import Optional, Dict, Any, List

# Import our modules
from config_manager import ConfigManager
from chzzk_downloader import ChzzkDownloader
from audio_processor import AudioProcessor
from utils import (
    validate_time_range, 
    generate_filename, 
    ensure_directory, 
    safe_file_removal
)


class TranscriptionApp:
    """Main application class for video transcription."""
    
    def __init__(self):
        """Initialize the application."""
        self.config_manager = ConfigManager()
        self.setup_page_config()
    
    # ==========================
    # 채팅 크롤링 관련 메서드들
    # ==========================
    
    def milliseconds_to_timestamp(self, ms: int) -> str:
        """밀리초를 [HH:MM:SS] 형식으로 변환"""
        seconds = ms // 1000
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    
    def timestamp_to_milliseconds(self, time_str: str) -> int:
        """시간 문자열을 밀리초로 변환"""
        time_str = time_str.strip()
        
        if time_str.isdigit():
            return int(time_str) * 1000
        
        parts = time_str.split(':')
        if len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
            total_seconds = hours * 3600 + minutes * 60 + seconds
        elif len(parts) == 2:
            minutes, seconds = map(int, parts)
            total_seconds = minutes * 60 + seconds
        else:
            raise ValueError("잘못된 시간 형식입니다. HH:MM:SS, MM:SS, 또는 초 단위로 입력하세요.")
        
        return total_seconds * 1000
    
    def extract_chat_message(self, chat: Dict) -> str:
        """채팅 메시지를 포맷된 문자열로 추출"""
        try:
            profile_data = json.loads(chat.get("profile", "{}"))
            nickname = profile_data.get("nickname", "Unknown")
            content = chat.get("content", "")
            player_time = chat.get("playerMessageTime", 0)
            timestamp = self.milliseconds_to_timestamp(player_time)

            if chat.get("messageTypeCode") == 10:
                return f"{timestamp} [도네이션] [{nickname}] : {content}"
            else:
                return f"{timestamp} [{nickname}] : {content}"
        except Exception as e:
            return f"[ERROR] 채팅 파싱 실패: {str(e)}"
    
    def collect_chzzk_video_chats(self, video_id: str, auth_cookies: Optional[str] = None,
                                 start_time_ms: Optional[int] = None, 
                                 end_time_ms: Optional[int] = None) -> List[str]:
        """지정된 시간 구간의 채팅 수집"""
        base_url = f"https://api.chzzk.naver.com/service/v1/videos/{video_id}/chats"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": f"https://chzzk.naver.com/video/{video_id}",
        }
        if auth_cookies:
            headers["Cookie"] = auth_cookies

        all_chats: List[tuple[int, str]] = []
        current_time = start_time_ms if start_time_ms is not None else 0
        previous_size = 50
        max_requests = 1000
        request_count = 0

        while request_count < max_requests:
            params = {
                "playerMessageTime": current_time,
                "previousVideoChatSize": previous_size,
            }

            try:
                response = requests.get(base_url, headers=headers, params=params)
            except requests.exceptions.RequestException:
                break

            if response.status_code != 200:
                break

            data = response.json()
            if data.get("code") != 200:
                break

            content = data.get("content", {})
            prev_chats = content.get("previousVideoChats", [])
            video_chats = content.get("videoChats", [])
            batch = prev_chats + video_chats

            if not batch:
                break

            # 시간 범위 필터링
            for chat in batch:
                player_time = chat.get("playerMessageTime", 0)
                
                if start_time_ms is not None and player_time < start_time_ms:
                    continue
                    
                if end_time_ms is not None and player_time > end_time_ms:
                    continue
                    
                chat_message = self.extract_chat_message(chat)
                all_chats.append((player_time, chat_message))

            next_time = content.get("nextPlayerMessageTime")
            if next_time is None or next_time <= current_time:
                break
                
            if end_time_ms is not None and next_time > end_time_ms:
                break

            current_time = next_time
            request_count += 1
            time.sleep(0.3)

        # 중복 제거 및 시간순 정렬
        unique_chats = list({(t, msg) for t, msg in all_chats})
        unique_chats.sort(key=lambda x: x[0])
        chat_messages = [msg for _, msg in unique_chats]
        return chat_messages
        
    def setup_page_config(self):
        """Configure Streamlit page settings."""
        st.set_page_config(
            page_title="영상 트랜스크립트 생성기", 
            page_icon="🎬",
            layout="wide"
        )
        
        st.title("🎬 영상 트랜스크립트 생성기")
        st.markdown("치지직 다시보기 영상의 구간을 다운로드하고 음성인식으로 트랜스크립트를 생성합니다.")

    def render_sidebar(self) -> Dict[str, Any]:
        """
        Render sidebar configuration panel.
        
        Returns:
            Dictionary of current configuration values
        """
        with st.sidebar:
            st.header("⚙️ 설정")
            
            # Download path
            download_path = st.text_input(
                "다운로드 경로", 
                value=self.config_manager.get("download_path")
            )
            
            # Whisper model selection
            whisper_models = self.config_manager.get_whisper_models()
            current_model = self.config_manager.get("whisper_model")
            whisper_model = st.selectbox(
                "Whisper 모델",
                whisper_models,
                index=whisper_models.index(current_model) if current_model in whisper_models else 1
            )
            
            # HuggingFace token
            hf_token = st.text_input(
                "HuggingFace 토큰 (화자분리용)",
                value=self.config_manager.get("huggingface_token"),
                type="password",
                help="화자분리 기능을 사용하려면 HuggingFace 토큰이 필요합니다."
            )
            
            # Naver cookies
            cookies_input = st.text_area(
                "네이버 쿠키 (성인 인증용)",
                value=self.config_manager.get("naver_cookies"),
                height=100,
                help="""성인 인증이 필요한 영상 접근을 위해 네이버 로그인 쿠키를 입력하세요.
필요한 쿠키: NID_AUT, NID_SES (주로 필요)
형식 예시:
- NID_AUT=값; NID_SES=값;
- 또는 한 줄에 하나씩:
  NID_AUT=값
  NID_SES=값

브라우저 개발자 도구 → Application → Cookies → chzzk.naver.com에서 확인 가능"""
            )
            
            # Output format
            output_formats = self.config_manager.get_output_formats()
            current_format = self.config_manager.get("output_format")
            output_format = st.selectbox(
                "출력 형식",
                output_formats,
                index=output_formats.index(current_format) if current_format in output_formats else 0
            )
            
            # Default quality
            quality_options = self.config_manager.get_quality_options()
            current_quality = self.config_manager.get("default_quality")
            default_quality = st.selectbox(
                "기본 화질",
                quality_options,
                index=quality_options.index(current_quality) if current_quality in quality_options else 0
            )
            
            # GPU usage
            use_gpu = st.checkbox(
                "GPU 사용 (CUDA/MPS)",
                value=self.config_manager.get("use_gpu"),
                help="GPU가 사용 가능한 경우 음성인식 속도를 크게 향상시킵니다."
            )
            
            # GPU status display
            self._display_gpu_status(use_gpu)
            
            # Save configuration
            if st.button("설정 저장"):
                new_config = {
                    "download_path": download_path,
                    "whisper_model": whisper_model,
                    "huggingface_token": hf_token,
                    "naver_cookies": cookies_input,
                    "output_format": output_format,
                    "default_quality": default_quality,
                    "use_gpu": use_gpu
                }
                if self.config_manager.save_config(new_config):
                    st.success("설정이 저장되었습니다!")
                else:
                    st.warning("설정 저장에 실패했지만 세션에서는 적용됩니다.")
            
            return {
                "download_path": download_path,
                "whisper_model": whisper_model,
                "hf_token": hf_token,
                "cookies_input": cookies_input,
                "output_format": output_format,
                "default_quality": default_quality,
                "use_gpu": use_gpu
            }

    def _display_gpu_status(self, use_gpu: bool):
        """Display GPU availability status."""
        if use_gpu:
            if torch.cuda.is_available():
                gpu_info = f"CUDA 사용 가능 ({torch.cuda.get_device_name(0)})"
                st.success(gpu_info)
            elif torch.backends.mps.is_available():
                st.success("MPS (Apple Silicon) 사용 가능")
            else:
                st.warning("GPU를 찾을 수 없습니다. CPU를 사용합니다.")
        else:
            st.info("CPU 모드로 설정됨")

    def render_main_interface(self, config: Dict[str, Any]):
        """
        Render main video processing interface.
        
        Args:
            config: Current configuration dictionary
        """
        col1, col2 = st.columns([2, 1])
        
        with col1:
            self._render_video_info_panel(config)
        
        with col2:
            self._render_execution_panel(config)

    def _render_video_info_panel(self, config: Dict[str, Any]):
        """Render video information and quality selection panel."""
        st.header("📹 영상 정보")
        
        # Video URL input
        video_url = st.text_input(
            "치지직 다시보기 URL",
            placeholder="https://chzzk.naver.com/video/12345"
        )
        
        # Time range inputs
        col_time1, col_time2 = st.columns(2)
        with col_time1:
            start_time = st.text_input("시작 시간 (HH:MM:SS)", value="00:00:00")
        with col_time2:
            end_time = st.text_input("종료 시간 (HH:MM:SS)", value="00:01:00")
        
        # Speaker diarization option
        enable_diarization = st.checkbox(
            "화자분리 사용", 
            value=bool(config["hf_token"]),
            disabled=not bool(config["hf_token"]),
            help="HuggingFace 토큰이 필요합니다."
        )
        
        # Chat collection option
        enable_chat_collection = st.checkbox(
            "채팅 수집 포함",
            value=True,
            help="해당 구간의 채팅도 함께 수집하여 트랜스크립트에 포함합니다."
        )
        
        # Quality management
        self._handle_quality_selection(video_url, config)
        
        # Store values in session state for access by execution panel
        st.session_state.video_url = video_url
        st.session_state.start_time = start_time
        st.session_state.end_time = end_time
        st.session_state.enable_diarization = enable_diarization
        st.session_state.enable_chat_collection = enable_chat_collection

    def _handle_quality_selection(self, video_url: str, config: Dict[str, Any]):
        """Handle video quality detection and selection."""
        # Initialize session state
        if 'available_qualities' not in st.session_state:
            st.session_state.available_qualities = []
        if 'selected_quality' not in st.session_state:
            st.session_state.selected_quality = config["default_quality"]
        
        # Quality check button
        if st.button("📊 사용 가능한 화질 확인"):
            if video_url:
                self._check_video_qualities(video_url, config)
            else:
                st.warning("먼저 영상 URL을 입력해주세요.")
        
        # Display available qualities
        if st.session_state.available_qualities:
            self._display_quality_options()
        else:
            # Default quality when no qualities checked
            st.session_state.selected_quality = config["default_quality"]

    def _check_video_qualities(self, video_url: str, config: Dict[str, Any]):
        """Check and store available video qualities."""
        video_no, error = ChzzkDownloader.extract_video_info(video_url)
        if error:
            st.error(error)
            return
        
        cookies = config["cookies_input"] if config["cookies_input"].strip() else None
        stream_data, error = ChzzkDownloader.get_video_streams(video_no, cookies)
        if error:
            st.error(error)
            return
        
        st.session_state.available_qualities = stream_data['stream_qualities']
        st.session_state.stream_data = stream_data
        
        if stream_data.get('adult'):
            st.info("🔞 성인 인증 영상입니다.")
        
        st.success("화질 정보를 가져왔습니다!")

    def _display_quality_options(self):
        """Display and handle quality selection."""
        st.subheader("📊 사용 가능한 화질")
        
        quality_options = []
        for quality in st.session_state.available_qualities:
            if quality['quality_label'] == 'auto':
                quality_options.append("auto (자동)")
            else:
                quality_options.append(f"{quality['quality_label']} ({quality['resolution']})")
        
        if quality_options:
            selected_idx = st.selectbox(
                "화질 선택",
                range(len(quality_options)),
                format_func=lambda x: quality_options[x],
                index=0
            )
            st.session_state.selected_quality = st.session_state.available_qualities[selected_idx]
            
            # Display selected quality info
            selected_stream = st.session_state.selected_quality
            if selected_stream['quality_label'] != 'auto':
                st.info(f"선택된 화질: {selected_stream['quality_label']} ({selected_stream['resolution']}) - 대역폭: {selected_stream['bandwidth']:,} bps")
            else:
                st.info("선택된 화질: 자동")

    def _render_execution_panel(self, config: Dict[str, Any]):
        """Render execution panel with transcription button."""
        st.header("🚀 실행")
        
        if st.button("트랜스크립트 생성", type="primary", use_container_width=True):
            self._process_video_transcription(config)

    def _process_video_transcription(self, config: Dict[str, Any]):
        """Process video transcription with full pipeline."""
        # Validate inputs
        video_url = st.session_state.get('video_url', '')
        start_time = st.session_state.get('start_time', '00:00:00')
        end_time = st.session_state.get('end_time', '00:01:00')
        enable_diarization = st.session_state.get('enable_diarization', False)
        enable_chat_collection = st.session_state.get('enable_chat_collection', False)
        
        if not video_url:
            st.error("영상 URL을 입력해주세요.")
            return
        
        # Validate time range
        start_seconds, end_seconds, error = validate_time_range(start_time, end_time)
        if error:
            st.error(error)
            return
        
        # Setup progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            self._run_transcription_pipeline(
                config, video_url, start_seconds, end_seconds, 
                enable_diarization, enable_chat_collection, progress_bar, status_text
            )
        except Exception as e:
            st.error(f"처리 중 오류가 발생했습니다: {str(e)}")

    def _run_transcription_pipeline(self, config: Dict[str, Any], video_url: str, 
                                  start_seconds: int, end_seconds: int, 
                                  enable_diarization: bool, enable_chat_collection: bool,
                                  progress_bar, status_text):
        """Run the complete transcription pipeline."""
        download_path = config["download_path"]
        ensure_directory(download_path)
        
        # Step 1: Get video information
        status_text.text("📋 비디오 정보를 가져오는 중...")
        progress_bar.progress(10)
        
        video_no, error = ChzzkDownloader.extract_video_info(video_url)
        if error:
            st.error(error)
            return
        
        cookies = config["cookies_input"] if config["cookies_input"].strip() else None
        stream_data, error = ChzzkDownloader.get_video_streams(video_no, cookies)
        if error:
            st.error(error)
            return
        
        # Step 2: Select stream quality
        selected_stream = self._get_selected_stream(stream_data, config)
        if not selected_stream:
            st.error("선택된 화질의 스트림을 찾을 수 없습니다.")
            return
        
        # Step 3: Generate file paths
        video_path, audio_path, transcript_path, chat_path = self._generate_file_paths(
            stream_data, selected_stream, download_path, config["output_format"], enable_chat_collection
        )
        
        # Step 4: Download video
        status_text.text("📥 비디오를 다운로드하는 중...")
        
        def update_download_progress(progress):
            progress_bar.progress(10 + int(progress * 0.4))
        
        success, message = ChzzkDownloader.download_video_segment(
            selected_stream['base_url'], video_path, 
            start_seconds, end_seconds, update_download_progress
        )
        
        if not success:
            st.error(message)
            return
        
        # Step 5: Process audio and transcription
        self._process_audio_transcription(
            video_path, audio_path, transcript_path, chat_path, config, 
            enable_diarization, enable_chat_collection, stream_data, 
            start_seconds, end_seconds, progress_bar, status_text
        )
        
        # Cleanup temporary files
        safe_file_removal(video_path, audio_path)

    def _get_selected_stream(self, stream_data: Dict[str, Any], config: Dict[str, Any]):
        """Get the selected stream quality."""
        if isinstance(st.session_state.get('selected_quality'), dict):
            return st.session_state.selected_quality
        else:
            return ChzzkDownloader.get_stream_by_quality(
                stream_data['stream_qualities'], 
                st.session_state.get('selected_quality', config["default_quality"])
            )

    def _generate_file_paths(self, stream_data: Dict[str, Any], selected_stream: Dict[str, Any], 
                           download_path: str, output_format: str, enable_chat_collection: bool = False):
        """Generate file paths for video, audio, transcript, and chat."""
        quality_suffix = selected_stream['quality_label'] if selected_stream['quality_label'] != 'auto' else 'auto'
        
        video_filename = generate_filename(stream_data['title'], quality_suffix, 'mp4')
        audio_filename = generate_filename(stream_data['title'], quality_suffix, 'wav')
        transcript_filename = generate_filename(stream_data['title'], quality_suffix, output_format)
        
        paths = [
            os.path.join(download_path, video_filename),
            os.path.join(download_path, audio_filename),
            os.path.join(download_path, transcript_filename)
        ]
        
        if enable_chat_collection:
            chat_filename = generate_filename(stream_data['title'], quality_suffix, 'txt')
            chat_filename = chat_filename.replace('.txt', '_chat.txt')
            paths.append(os.path.join(download_path, chat_filename))
        else:
            paths.append(None)
        
        return tuple(paths)

    def _process_audio_transcription(self, video_path: str, audio_path: str, 
                                   transcript_path: str, chat_path: Optional[str], config: Dict[str, Any], 
                                   enable_diarization: bool, enable_chat_collection: bool, 
                                   stream_data: Dict[str, Any], start_seconds: int, end_seconds: int,
                                   progress_bar, status_text):
        """Process audio extraction and transcription."""
        # Step 5: Extract audio
        status_text.text("🎵 오디오를 추출하는 중...")
        progress_bar.progress(50)
        
        audio_processor = AudioProcessor(
            config["whisper_model"],
            config["hf_token"] if enable_diarization else None,
            config["use_gpu"]
        )
        
        success, message = audio_processor.extract_audio(video_path, audio_path)
        if not success:
            st.error(message)
            return
        
        # Step 6: Load models
        status_text.text("🤖 AI 모델을 로드하는 중...")
        progress_bar.progress(60)
        audio_processor.load_models()
        
        # Step 7: Speaker diarization (optional)
        diarization = None
        if enable_diarization:
            status_text.text("👥 화자분리를 수행하는 중...")
            progress_bar.progress(70)
            diarization = audio_processor.perform_diarization(audio_path)
        
        # Step 7.5: Collect chat (if enabled)
        chat_messages = []
        if enable_chat_collection and chat_path:
            status_text.text("💬 채팅을 수집하는 중...")
            progress_bar.progress(75)
            
            # Extract video ID from URL
            video_no, error = ChzzkDownloader.extract_video_info(st.session_state.get('video_url', ''))
            if not error:
                start_time_ms = start_seconds * 1000
                end_time_ms = end_seconds * 1000
                cookies = config["cookies_input"] if config["cookies_input"].strip() else None
                
                chat_messages = self.collect_chzzk_video_chats(
                    video_no, cookies, start_time_ms, end_time_ms
                )
                
                if chat_messages:
                    with open(chat_path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(chat_messages))

        # Step 8: Speech recognition
        status_text.text("🎙️ 음성인식을 수행하는 중...")
        progress_bar.progress(80)
        
        whisper_result, error = audio_processor.transcribe_with_whisper(audio_path)
        if error:
            st.error(error)
            return
        
        # Step 9: Generate transcript
        status_text.text("📝 트랜스크립트를 생성하는 중...")
        progress_bar.progress(90)
        
        if config["output_format"] == "srt":
            transcript = audio_processor.create_srt_transcript(whisper_result, diarization)
        else:
            transcript = audio_processor.create_transcript(whisper_result, diarization)
        
        # Add chat messages to transcript if available
        if enable_chat_collection and chat_messages:
            transcript += "\n\n" + "="*50 + "\n"
            transcript += "📋 채팅 로그\n"
            transcript += "="*50 + "\n\n"
            transcript += '\n'.join(chat_messages)
        
        # Save transcript
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write(transcript)
        
        # Complete
        progress_bar.progress(100)
        status_text.text("✅ 완료!")
        
        # Display results
        self._display_results(stream_data, transcript, transcript_path, chat_path,
                            st.session_state.get('start_time'), st.session_state.get('end_time'), 
                            enable_chat_collection, len(chat_messages) if chat_messages else 0)

    def _display_results(self, stream_data: Dict[str, Any], transcript: str, 
                        transcript_path: str, chat_path: Optional[str], start_time: str, end_time: str,
                        enable_chat_collection: bool, chat_count: int):
        """Display processing results."""
        st.success("트랜스크립트 생성이 완료되었습니다!")
        
        # Video information
        with st.expander("📋 비디오 정보", expanded=True):
            st.write(f"**제목:** {stream_data['title']}")
            st.write(f"**작성자:** {stream_data['author']}")
            st.write(f"**구간:** {start_time} - {end_time}")
            if enable_chat_collection:
                st.write(f"**수집된 채팅:** {chat_count}개")
        
        # Transcript display
        with st.expander("📝 트랜스크립트", expanded=True):
            st.text_area("", transcript, height=400)
        
        # Download buttons
        col1, col2 = st.columns(2)
        
        with col1:
            with open(transcript_path, 'rb') as f:
                st.download_button(
                    label="📄 트랜스크립트 다운로드",
                    data=f.read(),
                    file_name=os.path.basename(transcript_path),
                    mime="text/plain"
                )
        
        with col2:
            if enable_chat_collection and chat_path and os.path.exists(chat_path):
                with open(chat_path, 'rb') as f:
                    st.download_button(
                        label="💬 채팅 로그 다운로드",
                        data=f.read(),
                        file_name=os.path.basename(chat_path),
                        mime="text/plain"
                    )

    def run(self):
        """Run the main application."""
        # Render sidebar and get configuration
        config = self.render_sidebar()
        
        # Render main interface
        self.render_main_interface(config)


def main():
    """Main entry point."""
    app = TranscriptionApp()
    app.run()


if __name__ == "__main__":
    main()