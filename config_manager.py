"""
Configuration management for the video transcriber application.
"""
import json
import os
from typing import Dict, Any, Optional

try:
    import streamlit as st
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False


class ConfigManager:
    """Manages application configuration with file persistence."""
    
    DEFAULT_CONFIG = {
        "download_path": "./downloads",
        "whisper_model": "base",
        "huggingface_token": "",
        "naver_cookies": "",
        "output_format": "txt",
        "default_quality": "best",
        "use_gpu": True
    }
    
    def __init__(self, config_file: str = "./config/config.json"):
        """
        Initialize configuration manager.
        
        Args:
            config_file: Path to configuration file
        """
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """
        Load configuration from file or return defaults.
        
        Returns:
            Configuration dictionary
        """
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    return {**self.DEFAULT_CONFIG, **loaded_config}
            except (json.JSONDecodeError, IOError):
                return self.DEFAULT_CONFIG.copy()
        return self.DEFAULT_CONFIG.copy()
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """
        Save configuration to file.
        
        Args:
            config: Configuration dictionary to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure config directory exists
            config_dir = os.path.dirname(self.config_file)
            if config_dir:
                os.makedirs(config_dir, exist_ok=True)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            self.config = config
            return True
            
        except Exception as e:
            if STREAMLIT_AVAILABLE:
                st.error(f"설정 저장 실패: {str(e)}")
            
            # Update in-memory config even if file save fails
            self.config = config
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value in memory.
        
        Args:
            key: Configuration key
            value: Value to set
        """
        self.config[key] = value
    
    def update(self, updates: Dict[str, Any]) -> None:
        """
        Update multiple configuration values.
        
        Args:
            updates: Dictionary of key-value pairs to update
        """
        self.config.update(updates)
    
    def get_whisper_models(self) -> list:
        """Get list of available Whisper models."""
        return ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]
    
    def get_output_formats(self) -> list:
        """Get list of available output formats."""
        return ["txt", "srt"]
    
    def get_quality_options(self) -> list:
        """Get list of available quality options."""
        return ["best", "1080p", "720p", "480p", "360p", "worst"]
    
    def validate_config(self) -> Dict[str, str]:
        """
        Validate current configuration.
        
        Returns:
            Dictionary of validation errors (empty if valid)
        """
        errors = {}
        
        # Validate download path
        download_path = self.get("download_path")
        if not download_path:
            errors["download_path"] = "다운로드 경로가 설정되지 않았습니다."
        
        # Validate whisper model
        whisper_model = self.get("whisper_model")
        if whisper_model not in self.get_whisper_models():
            errors["whisper_model"] = f"지원하지 않는 Whisper 모델: {whisper_model}"
        
        # Validate output format
        output_format = self.get("output_format")
        if output_format not in self.get_output_formats():
            errors["output_format"] = f"지원하지 않는 출력 형식: {output_format}"
        
        # Validate quality
        default_quality = self.get("default_quality")
        if default_quality not in self.get_quality_options():
            errors["default_quality"] = f"지원하지 않는 화질 설정: {default_quality}"
        
        return errors