"""
Utility functions for the video transcriber application.
"""
import re
import os
from datetime import datetime
from typing import Optional, Tuple


def convert_time_to_seconds(time_str: str) -> Optional[int]:
    """
    Convert time string to seconds.
    
    Args:
        time_str: Time in format "HH:MM:SS", "MM:SS", or "SS"
        
    Returns:
        Seconds as integer, or None if invalid format
    """
    try:
        parts = time_str.split(':')
        if len(parts) == 3:
            h, m, s = map(int, parts)
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m, s = map(int, parts)
            return m * 60 + s
        else:
            return int(parts[0])
    except ValueError:
        return None


def clean_filename(filename: str) -> str:
    """
    Clean filename by removing invalid characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Cleaned filename safe for filesystem
    """
    # Remove special characters that are problematic in filenames
    import re
    # Remove common unicode special characters one by one to avoid regex issues
    chars_to_remove = ['♥', '♡', 'ღ', '⭐', '㉦', '✧', '》', '《', '♠', '♦', '❤️', '♣', '✿', 'ꈍ', 'ᴗ', '★']
    cleaned = filename
    for char in chars_to_remove:
        cleaned = cleaned.replace(char, '')
    
    # Then handle ASCII special characters
    cleaned = re.sub(r'[/@!~*\[\]#$%^&()\-_=+<>?;:\'"]', '', cleaned)
    return cleaned


def format_time(seconds: float) -> str:
    """
    Format seconds to HH:MM:SS string.
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted time string
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def generate_filename(title: str, quality: str, extension: str) -> str:
    """
    Generate filename with timestamp and quality.
    
    Args:
        title: Video title
        quality: Quality label
        extension: File extension (without dot)
        
    Returns:
        Generated filename
    """
    clean_title = clean_filename(title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{clean_title}_{quality}_{timestamp}.{extension}"


def ensure_directory(path: str) -> None:
    """
    Ensure directory exists, create if it doesn't.
    
    Args:
        path: Directory path
    """
    os.makedirs(path, exist_ok=True)


def validate_time_range(start_time: str, end_time: str) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """
    Validate and convert time range.
    
    Args:
        start_time: Start time string
        end_time: End time string
        
    Returns:
        Tuple of (start_seconds, end_seconds, error_message)
    """
    start_seconds = convert_time_to_seconds(start_time)
    end_seconds = convert_time_to_seconds(end_time)
    
    if start_seconds is None or end_seconds is None:
        return None, None, "올바른 시간 형식을 입력해주세요. (HH:MM:SS)"
    
    if start_seconds >= end_seconds:
        return None, None, "종료 시간이 시작 시간보다 늦어야 합니다."
    
    return start_seconds, end_seconds, None


def safe_file_removal(*file_paths: str) -> None:
    """
    Safely remove files without raising exceptions.
    
    Args:
        *file_paths: Variable number of file paths to remove
    """
    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass  # Ignore errors during cleanup