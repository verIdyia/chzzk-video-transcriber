"""
CLI runner for chzzk-video-transcriber - no Streamlit needed.
"""
import os
import sys
import time

from chzzk_downloader import ChzzkDownloader
from audio_processor import AudioProcessor
from utils import (
    validate_time_range,
    generate_filename,
    ensure_directory,
    safe_file_removal,
    format_time,
)


def run(
    video_url: str,
    start_time: str = "00:00:00",
    end_time: str = "00:00:42",
    quality: str = "worst",
    whisper_model: str = "large-v3-turbo",
    output_dir: str = "./output",
    output_format: str = "txt",
    use_gpu: bool = True,
    enable_diarization: bool = False,
    cookies: str = None,
):
    ensure_directory(output_dir)

    # 1) Validate time range
    start_seconds, end_seconds, error = validate_time_range(start_time, end_time)
    if error:
        print(f"[ERROR] {error}")
        return

    # 2) Extract video info
    print("[1/7] Extracting video info...")
    video_no, error = ChzzkDownloader.extract_video_info(video_url)
    if error:
        print(f"[ERROR] {error}")
        return

    stream_data, error = ChzzkDownloader.get_video_streams(video_no, cookies)
    if error:
        print(f"[ERROR] {error}")
        return

    print(f"  Title : {stream_data['title']}")
    print(f"  Author: {stream_data['author']}")
    print(f"  Duration: {stream_data['duration']}ms")

    # 3) Select quality
    selected_stream = ChzzkDownloader.get_stream_by_quality(
        stream_data["stream_qualities"], quality
    )
    if not selected_stream:
        print("[ERROR] No stream found for requested quality")
        return
    print(
        f"  Quality: {selected_stream['quality_label']} ({selected_stream['resolution']})"
    )

    # 4) Generate paths
    quality_suffix = selected_stream["quality_label"]
    video_path = os.path.join(output_dir, generate_filename(stream_data["title"], quality_suffix, "mp4"))
    audio_path = os.path.join(output_dir, generate_filename(stream_data["title"], quality_suffix, "wav"))
    transcript_path = os.path.join(output_dir, generate_filename(stream_data["title"], quality_suffix, output_format))

    # 5) Download
    print("[2/7] Downloading video segment...")
    t0 = time.time()

    def progress_cb(pct):
        print(f"\r  Download: {pct:.1f}%", end="", flush=True)

    success, message = ChzzkDownloader.download_video_segment(
        selected_stream["base_url"],
        video_path,
        start_seconds,
        end_seconds,
        progress_cb,
    )
    print()
    if not success:
        print(f"[ERROR] {message}")
        return
    dt = time.time() - t0
    sz = os.path.getsize(video_path) / (1024 * 1024)
    print(f"  Done in {dt:.1f}s ({sz:.1f} MB)")

    # 6) Extract audio
    print("[3/7] Extracting audio...")
    processor = AudioProcessor(
        whisper_model=whisper_model,
        diarization_backend="none" if not enable_diarization else "auto",
        use_gpu=use_gpu,
    )
    success, message = processor.extract_audio(video_path, audio_path)
    if not success:
        print(f"[ERROR] {message}")
        safe_file_removal(video_path)
        return

    # 7) Load models
    print(f"[4/7] Loading Whisper model ({whisper_model}) on {processor.device}...")
    processor.load_models()

    # 8) Diarization (optional)
    diarization = None
    if enable_diarization:
        print("[5/7] Performing speaker diarization...")
        diarization = processor.perform_diarization(audio_path)

    # 9) Transcribe
    print("[5/7] Transcribing audio..." if not enable_diarization else "[6/7] Transcribing audio...")
    t0 = time.time()
    whisper_result, error = processor.transcribe_with_whisper(audio_path)
    dt = time.time() - t0
    if error:
        print(f"[ERROR] {error}")
        safe_file_removal(video_path, audio_path)
        return
    print(f"  Transcription done in {dt:.1f}s")

    # 10) Generate transcript
    step = "6/7" if not enable_diarization else "7/7"
    print(f"[{step}] Generating transcript...")
    if output_format == "srt":
        transcript = processor.create_srt_transcript(whisper_result, diarization)
    else:
        transcript = processor.create_transcript(whisper_result, diarization)

    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(transcript)

    # 11) Cleanup
    print("[7/7] Cleaning up...")
    safe_file_removal(video_path, audio_path)

    print(f"\n=== DONE ===")
    print(f"Transcript saved to: {transcript_path}")
    print(f"\n--- Transcript Preview ---")
    for line in transcript.split("\n")[:20]:
        print(line)
    if len(transcript.split("\n")) > 20:
        print(f"... ({len(transcript.split(chr(10)))} lines total)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CHZZK Video Transcriber CLI")
    parser.add_argument("url", help="Chzzk video URL")
    parser.add_argument("--start", default="00:00:00", help="Start time (HH:MM:SS)")
    parser.add_argument("--end", default="00:01:00", help="End time (HH:MM:SS)")
    parser.add_argument("--quality", default="worst", help="Quality: best, worst, 720p, etc.")
    parser.add_argument("--model", default="large-v3-turbo", help="Whisper model name")
    parser.add_argument("--output-dir", default="./output", help="Output directory")
    parser.add_argument("--format", default="txt", choices=["txt", "srt"], help="Output format")
    parser.add_argument("--no-gpu", action="store_true", help="Disable GPU")
    parser.add_argument("--diarization", action="store_true", help="Enable speaker diarization")
    parser.add_argument("--cookies", default=None, help="Naver cookies string")

    args = parser.parse_args()

    run(
        video_url=args.url,
        start_time=args.start,
        end_time=args.end,
        quality=args.quality,
        whisper_model=args.model,
        output_dir=args.output_dir,
        output_format=args.format,
        use_gpu=not args.no_gpu,
        enable_diarization=args.diarization,
        cookies=args.cookies,
    )
