"""
CHZZK video downloader with enhanced features for various video formats and cookie support.
"""
import re
import time
import requests
import xml.etree.ElementTree as ET
import os
from typing import Dict, List, Optional, Tuple, Union, Callable, Any
from utils import clean_filename

try:
    import ffmpeg
    FFMPEG_AVAILABLE = True
except ImportError:
    FFMPEG_AVAILABLE = False


class ChzzkDownloader:
    """Enhanced CHZZK video downloader with cookie support for age-restricted content."""
    
    # API endpoints
    VOD_URL = "https://apis.naver.com/neonplayer/vodplay/v2/playback/{video_id}?key={in_key}"
    VOD_INFO = "https://api.chzzk.naver.com/service/v2/videos/{video_no}"
    
    # Enhanced User-Agent for better compatibility
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    @staticmethod
    def parse_cookies(cookie_string: str) -> Dict[str, str]:
        """Parse cookie string into dictionary format."""
        if not cookie_string:
            return {}
        
        cookies = {}
        try:
            cookie_string = cookie_string.strip()
            
            # Format 1: "key1=value1; key2=value2"
            if ';' in cookie_string:
                for cookie in cookie_string.split(';'):
                    if '=' in cookie:
                        key, value = cookie.strip().split('=', 1)
                        cookies[key.strip()] = value.strip()
            # Format 2: "key1=value1\nkey2=value2" or single cookie
            else:
                for line in cookie_string.split('\n'):
                    line = line.strip()
                    if '=' in line:
                        key, value = line.split('=', 1)
                        cookies[key.strip()] = value.strip()
        except Exception:
            pass
        
        return cookies

    @staticmethod
    def extract_video_info(link: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract video number from CHZZK URL."""
        patterns = [
            r'https?://chzzk\.naver\.com/video/(?P<video_no>\d+)(?:\?.*)?$',
            r'https?://chzzk\.naver\.com/(?:video/(?P<video_no>\d+)|live/(?P<channel_id>[^/?]+))(?:\?.*)?$',
            r'https?://m\.chzzk\.naver\.com/video/(?P<video_no>\d+)(?:\?.*)?$'
        ]
        
        for pattern in patterns:
            match = re.match(pattern, link.strip())
            if match:
                video_no = match.group("video_no")
                if video_no:
                    return video_no, None
        
        return None, "올바르지 않은 링크입니다. 치지직 비디오 URL을 확인해주세요."

    @staticmethod
    def get_video_streams(video_no: str, cookies: Optional[Union[str, Dict[str, str]]] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Get video stream information from CHZZK API."""
        api_url = ChzzkDownloader.VOD_INFO.format(video_no=video_no)
        headers = {
            "User-Agent": ChzzkDownloader.USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://chzzk.naver.com/",
            "Origin": "https://chzzk.naver.com"
        }
        
        # Setup session with cookies if provided
        session = requests.Session()
        if cookies:
            if isinstance(cookies, str):
                cookies = ChzzkDownloader.parse_cookies(cookies)
            session.cookies.update(cookies)
        
        # Retry mechanism for better reliability
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = session.get(api_url, headers=headers, timeout=30)
                response.raise_for_status()
                break
            except requests.RequestException as e:
                if attempt == max_retries - 1:
                    return None, f"비디오 정보를 가져오는데 실패했습니다 (시도 {max_retries}회): {str(e)}"
                time.sleep(1)

        # Handle HTTP status codes
        if response.status_code == 404:
            return None, "비디오를 찾을 수 없습니다."
        elif response.status_code == 403:
            return None, "비디오에 접근할 권한이 없습니다. 성인 인증이 필요한 경우 쿠키를 설정해주세요."

        try:
            json_data = response.json()
            if json_data.get('code') == 403:
                return None, "성인 인증이 필요한 영상입니다. 네이버 로그인 쿠키를 입력해주세요."
            elif json_data.get('code') != 200:
                return None, f"API 오류: {json_data.get('message', '알 수 없는 오류')}"
            
            content = json_data.get('content', {})
            video_id = content.get('videoId')
            in_key = content.get('inKey')
            
            # Check for adult content status
            adult_status = content.get('adult', False)
            
            if video_id is None or in_key is None:
                if adult_status and not cookies:
                    return None, "성인 인증이 필요한 영상입니다. 네이버 로그인 쿠키를 입력해주세요."
                else:
                    return None, "로그인이 필요한 비디오이거나 비공개 비디오입니다."

            video_url = ChzzkDownloader.VOD_URL.format(video_id=video_id, in_key=in_key)
            author = content.get('channel', {}).get('channelName', 'Unknown')
            title = content.get('videoTitle', 'Unknown Title')
            duration = content.get('duration', 0)
            
            # Get stream qualities with cookie support
            stream_qualities = ChzzkDownloader._parse_dash_manifest(video_url, cookies)
            if not stream_qualities:
                stream_qualities = ChzzkDownloader._get_fallback_streams(video_url, cookies)
                if not stream_qualities:
                    return None, "스트림 URL을 가져올 수 없습니다."
            
            return {
                'author': author,
                'title': title,
                'video_id': video_id,
                'video_no': video_no,
                'duration': duration,
                'adult': adult_status,
                'stream_qualities': stream_qualities
            }, None
            
        except Exception as e:
            return None, f"예상치 못한 오류: {str(e)}"

    @staticmethod
    def _parse_dash_manifest(video_url: str, cookies: Optional[Union[str, Dict[str, str]]] = None) -> Optional[List[Dict[str, Any]]]:
        """Parse DASH manifest to extract stream quality information."""
        headers = {
            "User-Agent": ChzzkDownloader.USER_AGENT,
            "Accept": "application/dash+xml, application/xml, text/xml, */*",
            "Referer": "https://chzzk.naver.com/"
        }
        
        session = requests.Session()
        if cookies:
            if isinstance(cookies, str):
                cookies = ChzzkDownloader.parse_cookies(cookies)
            session.cookies.update(cookies)
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = session.get(video_url, headers=headers, timeout=30)
                response.raise_for_status()
                
                # Check content type
                content_type = response.headers.get('content-type', '').lower()
                if 'xml' not in content_type and 'dash' not in content_type:
                    continue
                
                root = ET.fromstring(response.text)
                ns = {"mpd": "urn:mpeg:dash:schema:mpd:2011"}
                
                stream_qualities = []
                processed_qualities = set()  # Avoid duplicates
                
                # Process AdaptationSets
                for adaptation_set in root.findall(".//mpd:AdaptationSet", namespaces=ns):
                    mime_type = adaptation_set.get('mimeType', '')
                    
                    # Process video streams
                    if 'video' in mime_type:
                        # Get base URL
                        adaptation_base_url = None
                        base_url_element = adaptation_set.find(".//mpd:BaseURL", namespaces=ns)
                        if base_url_element is None:
                            base_url_element = root.find(".//mpd:BaseURL", namespaces=ns)
                        if base_url_element is not None:
                            adaptation_base_url = base_url_element.text
                        
                        # Process each representation
                        for representation in adaptation_set.findall(".//mpd:Representation", namespaces=ns):
                            width = representation.get('width')
                            height = representation.get('height')
                            bandwidth = representation.get('bandwidth')
                            rep_id = representation.get('id', '')
                            
                            # Get representation-specific base URL
                            rep_base_url_element = representation.find(".//mpd:BaseURL", namespaces=ns)
                            base_url = rep_base_url_element.text if rep_base_url_element is not None else adaptation_base_url
                            
                            if width and height and base_url:
                                quality_key = f"{width}x{height}_{mime_type}"
                                if quality_key not in processed_qualities:
                                    processed_qualities.add(quality_key)
                                    
                                    quality_info = {
                                        'resolution': f"{width}x{height}",
                                        'width': int(width),
                                        'height': int(height),
                                        'bandwidth': int(bandwidth) if bandwidth else 0,
                                        'base_url': base_url,
                                        'id': rep_id,
                                        'mime_type': mime_type,
                                        'quality_label': ChzzkDownloader._get_quality_label(int(height))
                                    }
                                    stream_qualities.append(quality_info)
                
                if stream_qualities:
                    # Test stream accessibility and filter out broken ones
                    valid_streams = ChzzkDownloader._filter_valid_streams(stream_qualities)
                    if valid_streams:
                        # Sort by resolution and bandwidth
                        valid_streams.sort(key=lambda x: (x['height'], x['bandwidth']), reverse=True)
                        return valid_streams
                    else:
                        # If no streams are valid, return original list and let download methods handle it
                        stream_qualities.sort(key=lambda x: (x['height'], x['bandwidth']), reverse=True)
                        return stream_qualities
                
            except Exception as e:
                if attempt == max_retries - 1:
                    pass  # Will try fallback method
                else:
                    time.sleep(0.5)
        
        return None

    @staticmethod
    def _filter_valid_streams(stream_qualities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out streams that are not accessible"""
        valid_streams = []
        
        for stream in stream_qualities:
            if ChzzkDownloader._test_stream_access(stream['base_url']):
                valid_streams.append(stream)
        
        return valid_streams
    
    @staticmethod
    def _test_stream_access(stream_url: str) -> bool:
        """Test if a stream URL is accessible"""
        headers = {
            'User-Agent': ChzzkDownloader.USER_AGENT,
            'Referer': 'https://chzzk.naver.com/',
            'Range': 'bytes=0-1023'  # Test with small range
        }
        
        try:
            response = requests.get(stream_url, headers=headers, timeout=5)
            # Accept both 200 (full content) and 206 (partial content) as valid
            return response.status_code in [200, 206]
        except:
            return False

    @staticmethod
    def _get_fallback_streams(video_url: str, cookies: Optional[Union[str, Dict[str, str]]] = None) -> Optional[List[Dict[str, Any]]]:
        """Fallback stream extraction method."""
        single_url = ChzzkDownloader._get_single_stream_url(video_url, cookies)
        if single_url:
            return [{
                'quality_label': 'auto',
                'resolution': 'auto',
                'base_url': single_url,
                'bandwidth': 0,
                'width': 0,
                'height': 0,
                'mime_type': 'video/mp4'
            }]
        
        return None
    
    @staticmethod
    def _get_single_stream_url(video_url: str, cookies: Optional[Union[str, Dict[str, str]]] = None) -> Optional[str]:
        """Extract single stream URL from manifest."""
        headers = {
            "User-Agent": ChzzkDownloader.USER_AGENT,
            "Accept": "application/dash+xml, application/xml, text/xml, */*"
        }
        
        session = requests.Session()
        if cookies:
            if isinstance(cookies, str):
                cookies = ChzzkDownloader.parse_cookies(cookies)
            session.cookies.update(cookies)
        
        try:
            response = session.get(video_url, headers=headers, timeout=15)
            response.raise_for_status()
            
            root = ET.fromstring(response.text)
            ns = {"mpd": "urn:mpeg:dash:schema:mpd:2011"}
            
            base_url_element = root.find(".//mpd:BaseURL", namespaces=ns)
            if base_url_element is not None:
                return base_url_element.text
                
        except Exception:
            pass
        
        return None

    @staticmethod
    def _get_quality_label(height: int) -> str:
        """Get quality label based on video height."""
        if height >= 2160:
            return "4K"
        elif height >= 1440:
            return "1440p"
        elif height >= 1080:
            return "1080p"
        elif height >= 720:
            return "720p"
        elif height >= 480:
            return "480p"
        elif height >= 360:
            return "360p"
        else:
            return f"{height}p"

    @staticmethod
    def get_stream_by_quality(stream_qualities: List[Dict[str, Any]], preferred_quality: str = "best") -> Optional[Dict[str, Any]]:
        """Select stream by preferred quality."""
        if not stream_qualities:
            return None
        
        if preferred_quality == "best":
            return stream_qualities[0]  # Already sorted by quality
        elif preferred_quality == "worst":
            return stream_qualities[-1]
        else:
            # Find specific quality
            for stream in stream_qualities:
                if (preferred_quality.lower() in stream['quality_label'].lower() or
                    preferred_quality in stream['resolution']):
                    return stream
            
            # Find closest quality if exact match not found
            target_height = ChzzkDownloader._parse_quality_to_height(preferred_quality)
            if target_height:
                return min(stream_qualities, key=lambda x: abs(x['height'] - target_height))
        
        return stream_qualities[0]  # Default: best quality

    @staticmethod
    def _parse_quality_to_height(quality_str: str) -> Optional[int]:
        """Parse quality string to height value."""
        match = re.search(r'(\d+)p?', quality_str)
        return int(match.group(1)) if match else None

    @staticmethod
    def download_video_segment(base_url: str, output_path: str, start_time: int, end_time: int, 
                             progress_callback: Optional[Callable[[float], None]] = None) -> Tuple[bool, str]:
        """Download video segment using FFmpeg with improved reliability."""
        if not FFMPEG_AVAILABLE:
            return False, "FFmpeg 라이브러리가 설치되지 않았습니다."
        
        try:
            total_duration = end_time - start_time
            if total_duration <= 0:
                return False, "잘못된 구간입니다."

            # Try multiple FFmpeg approaches for better compatibility
            methods = [
                ChzzkDownloader._download_method_1,
                ChzzkDownloader._download_method_2,
                ChzzkDownloader._download_method_3,
                ChzzkDownloader._download_method_4
            ]
            
            last_error = None
            for i, method in enumerate(methods):
                try:
                    success, message = method(base_url, output_path, start_time, total_duration, progress_callback)
                    if success:
                        return True, message
                    else:
                        last_error = f"Method {i+1}: {message}"
                except Exception as e:
                    last_error = f"Method {i+1} exception: {str(e)}"
                    continue
            
            return False, f"모든 다운로드 방법 실패. 마지막 오류: {last_error}"
            
        except Exception as e:
            return False, f"다운로드 중 오류 발생: {str(e)}"

    @staticmethod
    def _download_method_1(base_url: str, output_path: str, start_time: int, total_duration: int, 
                          progress_callback: Optional[Callable[[float], None]] = None) -> Tuple[bool, str]:
        """Method 1: Standard FFmpeg with enhanced headers"""
        input_options = {
            'ss': start_time,
            't': total_duration,
            'user_agent': ChzzkDownloader.USER_AGENT,
            'headers': f'Referer: https://chzzk.naver.com/\r\nUser-Agent: {ChzzkDownloader.USER_AGENT}',
            'reconnect': 1,
            'reconnect_streamed': 1,
            'reconnect_delay_max': 5
        }
        
        output_options = {
            'c': 'copy',
            'avoid_negative_ts': 'make_zero',
            'fflags': '+genpts',
            'movflags': '+faststart'
        }

        process = (
            ffmpeg
            .input(base_url, **input_options)
            .output(output_path, **output_options)
            .global_args('-progress', 'pipe:2')
            .global_args('-nostats')
            .global_args('-loglevel', 'warning')
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )

        return ChzzkDownloader._monitor_ffmpeg_process(process, total_duration, progress_callback, output_path)

    @staticmethod
    def _download_method_2(base_url: str, output_path: str, start_time: int, total_duration: int, 
                          progress_callback: Optional[Callable[[float], None]] = None) -> Tuple[bool, str]:
        """Method 2: Simplified options"""
        input_options = {
            'user_agent': ChzzkDownloader.USER_AGENT,
            'headers': f'Referer: https://chzzk.naver.com/\r\nUser-Agent: {ChzzkDownloader.USER_AGENT}',
            'reconnect': 1,
            'reconnect_streamed': 1
        }
        
        output_options = {
            'ss': start_time,
            't': total_duration,
            'c': 'copy',
            'avoid_negative_ts': 'make_zero'
        }

        process = (
            ffmpeg
            .input(base_url, **input_options)
            .output(output_path, **output_options)
            .global_args('-progress', 'pipe:2')
            .global_args('-nostats')
            .global_args('-loglevel', 'warning')
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )

        return ChzzkDownloader._monitor_ffmpeg_process(process, total_duration, progress_callback, output_path)

    @staticmethod
    def _download_method_3(base_url: str, output_path: str, start_time: int, total_duration: int, 
                          progress_callback: Optional[Callable[[float], None]] = None) -> Tuple[bool, str]:
        """Method 3: Basic options with re-encoding if needed"""
        process = (
            ffmpeg
            .input(base_url, 
                   ss=start_time,
                   t=total_duration,
                   headers=f'User-Agent: {ChzzkDownloader.USER_AGENT}')
            .output(output_path, 
                   vcodec='libx264',
                   acodec='aac',
                   preset='fast',
                   crf=23)
            .global_args('-progress', 'pipe:2')
            .global_args('-nostats')
            .global_args('-loglevel', 'error')
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )

        return ChzzkDownloader._monitor_ffmpeg_process(process, total_duration, progress_callback, output_path)

    @staticmethod
    def _monitor_ffmpeg_process(process, total_duration: int, 
                               progress_callback: Optional[Callable[[float], None]] = None,
                               output_path: str = None) -> Tuple[bool, str]:
        """Monitor FFmpeg process and handle progress/errors"""
        last_progress = 0
        stderr_lines = []
        
        while True:
            if process.poll() is not None:
                break

            line = process.stderr.readline()
            if not line:
                time.sleep(0.1)
                continue

            decoded_line = line.decode('utf-8', errors='replace').strip()
            stderr_lines.append(decoded_line)
            
            # Keep only last 20 lines for error reporting
            if len(stderr_lines) > 20:
                stderr_lines = stderr_lines[-20:]
            
            # Enhanced progress tracking
            if progress_callback:
                if 'out_time_ms=' in decoded_line:
                    match = re.search(r'out_time_ms=(\d+)', decoded_line)
                    if match:
                        current_time_ms = int(match.group(1))
                        current_time = current_time_ms / 1_000_000
                        if current_time > total_duration:
                            current_time = total_duration
                        progress = (current_time / total_duration) * 100
                        if progress > last_progress:
                            progress_callback(progress)
                            last_progress = progress
                elif 'out_time=' in decoded_line:
                    match = re.search(r'out_time=(\d+):(\d+):(\d+)\.(\d+)', decoded_line)
                    if match:
                        h, m, s, ms = map(int, match.groups())
                        current_time = h * 3600 + m * 60 + s + ms / 1000
                        if current_time > total_duration:
                            current_time = total_duration
                        progress = (current_time / total_duration) * 100
                        if progress > last_progress:
                            progress_callback(progress)
                            last_progress = progress

        return_code = process.wait()
        
        if return_code == 0:
            # Verify output file
            if output_path and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True, "다운로드 완료"
            else:
                return False, "다운로드 완료했지만 파일이 비어있습니다."
        else:
            # Extract meaningful error from stderr
            error_lines = [line for line in stderr_lines if any(keyword in line.lower() 
                          for keyword in ['error', 'failed', 'invalid', 'not found', 'forbidden', 'http'])]
            
            if error_lines:
                error_info = '; '.join(error_lines[-3:])  # Last 3 error lines
            else:
                error_info = '; '.join(stderr_lines[-3:]) if stderr_lines else "알 수 없는 오류"
            
            return False, f"다운로드 실패 (코드: {return_code}): {error_info}"

    @staticmethod
    def _download_method_4(base_url: str, output_path: str, start_time: int, total_duration: int, 
                          progress_callback: Optional[Callable[[float], None]] = None) -> Tuple[bool, str]:
        """Method 4: Direct HTTP download with Python requests"""
        try:
            headers = {
                'User-Agent': ChzzkDownloader.USER_AGENT,
                'Referer': 'https://chzzk.naver.com/',
                'Range': f'bytes={start_time * 1000000}-{(start_time + total_duration) * 1000000 + 1000000}'  # Rough byte range
            }
            
            # Try HTTP range request first
            response = requests.get(base_url, headers=headers, stream=True, timeout=30)
            
            if response.status_code not in [200, 206]:
                # If range request fails, try without range
                headers.pop('Range', None)
                response = requests.get(base_url, headers=headers, stream=True, timeout=30)
                
                if response.status_code != 200:
                    return False, f"HTTP 오류: {response.status_code}"
            
            # Download to file
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_callback and total_size > 0:
                            progress = (downloaded / total_size) * 100
                            progress_callback(min(progress, 100))
            
            # Verify file was created and has content
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                # If we downloaded the full file without range, extract the segment
                if 'Range' not in headers:
                    return ChzzkDownloader._extract_segment_post_download(output_path, start_time, total_duration)
                else:
                    return True, "다운로드 완료 (HTTP 방식)"
            else:
                return False, "다운로드된 파일이 비어있습니다"
                
        except Exception as e:
            return False, f"HTTP 다운로드 오류: {str(e)}"
    
    @staticmethod
    def _extract_segment_post_download(file_path: str, start_time: int, total_duration: int) -> Tuple[bool, str]:
        """Extract segment from downloaded file using FFmpeg"""
        temp_path = file_path + ".temp"
        
        try:
            # Move original to temp
            os.rename(file_path, temp_path)
            
            # Extract segment
            process = (
                ffmpeg
                .input(temp_path, ss=start_time, t=total_duration)
                .output(file_path, c='copy')
                .global_args('-loglevel', 'error')
                .run_async(pipe_stdout=True, pipe_stderr=True)
            )
            
            return_code = process.wait()
            
            # Cleanup temp file
            try:
                os.remove(temp_path)
            except:
                pass
            
            if return_code == 0 and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                return True, "다운로드 완료 (HTTP + 세그먼트 추출)"
            else:
                return False, f"세그먼트 추출 실패 (코드: {return_code})"
                
        except Exception as e:
            # Restore original file if possible
            try:
                if os.path.exists(temp_path):
                    os.rename(temp_path, file_path)
            except:
                pass
            return False, f"세그먼트 추출 오류: {str(e)}"