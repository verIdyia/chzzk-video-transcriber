"""
Parallel download + transcription for Chzzk videos.
Splits the time range into segments, downloads in parallel, then transcribes.
"""
import os
import sys
import time
import subprocess
import concurrent.futures
from pathlib import Path

from chzzk_downloader import ChzzkDownloader
from audio_processor import AudioProcessor
from utils import (
    validate_time_range,
    generate_filename,
    ensure_directory,
    safe_file_removal,
    format_time,
    clean_filename,
)


def download_segment(args):
    """Download a single segment using ffmpeg subprocess directly."""
    base_url, output_path, start_sec, duration, segment_idx, user_agent = args
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-t", str(duration),
        "-user_agent", user_agent,
        "-headers", f"Referer: https://chzzk.naver.com/\r\nUser-Agent: {user_agent}\r\n",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-i", base_url,
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        "-fflags", "+genpts",
        "-loglevel", "warning",
        output_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            return segment_idx, True, f"OK ({size_mb:.1f}MB)"
        else:
            err = result.stderr[-200:] if result.stderr else "unknown error"
            return segment_idx, False, f"FFmpeg error (rc={result.returncode}): {err}"
    except subprocess.TimeoutExpired:
        return segment_idx, False, "Timeout"
    except Exception as e:
        return segment_idx, False, str(e)


def concat_segments(segment_paths, output_path):
    """Concatenate video segments using ffmpeg concat demuxer."""
    list_file = output_path + ".list.txt"
    with open(list_file, "w") as f:
        for p in segment_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        "-loglevel", "warning",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    os.remove(list_file)

    if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return True, f"Concat OK ({os.path.getsize(output_path) / 1024 / 1024:.1f}MB)"
    return False, f"Concat failed: {result.stderr[-200:]}"


def run(
    video_url,
    start_time="00:00:00",
    end_time="03:30:00",
    quality="worst",
    whisper_model="large-v3-turbo",
    output_dir="./output",
    output_format="txt",
    segment_duration_min=30,
    max_workers=7,
):
    ensure_directory(output_dir)

    start_seconds, end_seconds, error = validate_time_range(start_time, end_time)
    if error:
        print(f"[ERROR] {error}")
        return

    total_duration = end_seconds - start_seconds
    segment_duration = segment_duration_min * 60

    # 1) Get video info
    print("[1/6] Getting video info...")
    video_no, error = ChzzkDownloader.extract_video_info(video_url)
    if error:
        print(f"[ERROR] {error}")
        return

    stream_data, error = ChzzkDownloader.get_video_streams(video_no)
    if error:
        print(f"[ERROR] {error}")
        return

    selected_stream = ChzzkDownloader.get_stream_by_quality(stream_data["stream_qualities"], quality)
    if not selected_stream:
        print("[ERROR] No stream found")
        return

    print(f"  Title: {stream_data['title']}")
    print(f"  Quality: {selected_stream['quality_label']} ({selected_stream['resolution']})")
    print(f"  Total duration: {total_duration}s ({total_duration/3600:.1f}h)")

    base_url = selected_stream["base_url"]
    ua = ChzzkDownloader.USER_AGENT

    # 2) Create segment download tasks
    segments = []
    seg_start = start_seconds
    seg_idx = 0
    while seg_start < end_seconds:
        seg_dur = min(segment_duration, end_seconds - seg_start)
        seg_path = os.path.join(output_dir, f"_seg_{seg_idx:03d}.mp4")
        segments.append((base_url, seg_path, seg_start, seg_dur, seg_idx, ua))
        seg_start += seg_dur
        seg_idx += 1

    print(f"\n[2/6] Downloading {len(segments)} segments in parallel (max {max_workers} workers)...")
    t0 = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_segment, seg): seg[4] for seg in segments}
        results = {}
        for future in concurrent.futures.as_completed(futures):
            idx, success, msg = future.result()
            results[idx] = (success, msg)
            status = "OK" if success else "FAIL"
            seg = segments[idx]
            start_h = seg[2] // 3600
            start_m = (seg[2] % 3600) // 60
            print(f"  Segment {idx} ({start_h}:{start_m:02d}:00): {status} - {msg}")

    # Check all succeeded
    failed = [i for i, (s, m) in results.items() if not s]
    if failed:
        print(f"\n[ERROR] {len(failed)} segments failed: {failed}")
        # Retry failed segments sequentially
        print("Retrying failed segments...")
        for idx in failed:
            seg = segments[idx]
            idx2, success, msg = download_segment(seg)
            results[idx2] = (success, msg)
            print(f"  Retry segment {idx2}: {'OK' if success else 'FAIL'} - {msg}")

    failed = [i for i, (s, m) in results.items() if not s]
    if failed:
        print(f"\n[ERROR] Still {len(failed)} failed segments. Aborting.")
        return

    dt = time.time() - t0
    print(f"  All downloads done in {dt:.0f}s ({dt/60:.1f}min)")

    # 3) Concat segments
    print("\n[3/6] Concatenating segments...")
    quality_suffix = selected_stream["quality_label"]
    title_clean = clean_filename(stream_data["title"]) or "video"
    video_path = os.path.join(output_dir, f"{title_clean}_{quality_suffix}_full.mp4")

    seg_paths = [segments[i][1] for i in range(len(segments))]
    success, msg = concat_segments(seg_paths, video_path)
    if not success:
        print(f"[ERROR] {msg}")
        return
    print(f"  {msg}")

    # Clean segment files
    for p in seg_paths:
        safe_file_removal(p)

    # 4) Extract audio
    print("\n[4/6] Extracting audio...")
    audio_path = os.path.join(output_dir, f"{title_clean}_{quality_suffix}_full.wav")
    processor = AudioProcessor(
        whisper_model=whisper_model,
        diarization_backend="none",
        use_gpu=True,
    )
    success, msg = processor.extract_audio(video_path, audio_path)
    if not success:
        print(f"[ERROR] {msg}")
        safe_file_removal(video_path)
        return
    print(f"  Audio extracted: {os.path.getsize(audio_path) / 1024 / 1024:.1f}MB")

    # 5) Transcribe
    print(f"\n[5/6] Loading Whisper ({whisper_model}) on {processor.device}...")
    processor.load_models()

    print("  Transcribing...")
    t0 = time.time()
    whisper_result, error = processor.transcribe_with_whisper(audio_path)
    dt = time.time() - t0
    if error:
        print(f"[ERROR] {error}")
        safe_file_removal(video_path, audio_path)
        return
    print(f"  Transcription done in {dt:.1f}s ({len(whisper_result['segments'])} segments)")

    # 6) Generate transcript
    print("\n[6/6] Generating transcript...")
    if output_format == "srt":
        transcript = processor.create_srt_transcript(whisper_result)
    else:
        transcript = processor.create_transcript(whisper_result)

    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    transcript_path = os.path.join(output_dir, f"{title_clean}_{quality_suffix}_{ts}.{output_format}")
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(transcript)

    # Cleanup
    safe_file_removal(video_path, audio_path)

    print(f"\n=== DONE ===")
    print(f"Transcript: {transcript_path}")
    print(f"Lines: {len(transcript.splitlines())}")
    print(f"\n--- Preview (first 30 lines) ---")
    for line in transcript.split("\n")[:30]:
        print(line)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parallel Chzzk Transcriber")
    parser.add_argument("url", help="Chzzk video URL")
    parser.add_argument("--start", default="00:00:00")
    parser.add_argument("--end", default="03:30:00")
    parser.add_argument("--quality", default="worst")
    parser.add_argument("--model", default="large-v3-turbo")
    parser.add_argument("--output-dir", default="./output")
    parser.add_argument("--format", default="txt", choices=["txt", "srt"])
    parser.add_argument("--segment-min", type=int, default=30, help="Segment duration in minutes")
    parser.add_argument("--workers", type=int, default=7, help="Max parallel downloads")
    args = parser.parse_args()

    run(
        video_url=args.url,
        start_time=args.start,
        end_time=args.end,
        quality=args.quality,
        whisper_model=args.model,
        output_dir=args.output_dir,
        output_format=args.format,
        segment_duration_min=args.segment_min,
        max_workers=args.workers,
    )
