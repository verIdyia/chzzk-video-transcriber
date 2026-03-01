"""Standalone chat collector for Chzzk videos - minimal headers approach."""
import requests
import json
import time
import os


def collect_chats(video_no, start_ms=0, end_ms=None, cookies=None, output_path=None):
    """Collect chats using minimal headers (proven working approach)."""
    base_url = f"https://api.chzzk.naver.com/service/v1/videos/{video_no}/chats"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": f"https://chzzk.naver.com/video/{video_no}",
    }
    if cookies:
        headers["Cookie"] = cookies

    all_chats = []
    current_time = start_ms if start_ms is not None else 0
    previous_size = 50
    max_requests = 10000
    request_count = 0

    while request_count < max_requests:
        params = {
            "playerMessageTime": current_time,
            "previousVideoChatSize": previous_size,
        }

        try:
            response = requests.get(base_url, headers=headers, params=params, timeout=15)
        except requests.exceptions.RequestException as e:
            print(f"Network error at req {request_count}: {e}")
            time.sleep(2)
            continue

        if response.status_code != 200:
            print(f"HTTP {response.status_code} at req {request_count}")
            if response.status_code == 403:
                print("403: Auth cookies may be needed.")
            break

        try:
            data = response.json()
        except (ValueError, KeyError):
            print("JSON parse failed")
            break

        if data.get("code") != 200:
            print(f"API error: {data.get('message', 'Unknown')}")
            break

        content = data.get("content", {})
        prev_chats = content.get("previousVideoChats", [])
        video_chats = content.get("videoChats", [])
        batch = prev_chats + video_chats

        if not batch:
            break

        for chat in batch:
            player_time = chat.get("playerMessageTime", 0)
            if start_ms is not None and player_time < start_ms:
                continue
            if end_ms is not None and player_time > end_ms:
                continue

            try:
                profile_data = json.loads(chat.get("profile", "{}"))
                nickname = profile_data.get("nickname", "Unknown")
            except Exception:
                nickname = "Unknown"
            text = chat.get("content", "")
            ms = player_time
            seconds = ms // 1000
            h = seconds // 3600
            m = (seconds % 3600) // 60
            s = seconds % 60
            ts = f"[{h:02d}:{m:02d}:{s:02d}]"

            prefix = "[도네이션] " if chat.get("messageTypeCode") == 10 else ""
            all_chats.append((player_time, f"{ts} {prefix}[{nickname}] : {text}"))

        next_time = content.get("nextPlayerMessageTime")
        if next_time is None or next_time <= current_time:
            break
        if end_ms is not None and next_time > end_ms:
            break

        current_time = next_time
        request_count += 1

        if request_count % 100 == 0:
            elapsed_s = current_time // 1000
            h, m, s = elapsed_s // 3600, (elapsed_s % 3600) // 60, elapsed_s % 60
            print(f"  {request_count} requests, {len(all_chats)} chats, at {h:02d}:{m:02d}:{s:02d}")

        time.sleep(0.3)

    # Deduplicate and sort
    unique_chats = sorted(set(all_chats), key=lambda x: x[0])
    chat_messages = [msg for _, msg in unique_chats]

    print(f"Chat collection done: {len(chat_messages)} messages ({request_count} requests)")

    if output_path and chat_messages:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(chat_messages))
        print(f"Saved to {output_path}")

    return chat_messages


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("video_no", help="Chzzk video number")
    parser.add_argument("--start", default="00:00:00", help="Start time HH:MM:SS")
    parser.add_argument("--end", default="00:05:00", help="End time HH:MM:SS")
    parser.add_argument("--output", default=None, help="Output file path")
    parser.add_argument("--cookies", default=None, help="Auth cookies")
    args = parser.parse_args()

    def to_ms(t):
        parts = t.split(":")
        if len(parts) == 3:
            return (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])) * 1000
        elif len(parts) == 2:
            return (int(parts[0]) * 60 + int(parts[1])) * 1000
        return int(parts[0]) * 1000

    start = to_ms(args.start)
    end = to_ms(args.end)
    out = args.output or f"./output/chat_{args.video_no}.txt"

    collect_chats(args.video_no, start, end, cookies=args.cookies, output_path=out)
