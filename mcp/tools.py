"""
MCP Tools for Universal Social Media Downloader
"""

import json
from typing import Dict, Any, List, Optional

class DownloadTools:
    """
    MCP Tools for social media downloading
    
    These tools can be used by AI models through MCP protocol
    """
    
    @staticmethod
    def download_video(url: str, save_to: str = 'local') -> Dict[str, Any]:
        """
        Download a video from any supported platform
        
        Args:
            url: Video URL
            save_to: Where to save (local, gallery, drive)
            
        Returns:
            Download result
        """
        from app import downloader, DOWNLOAD_DIR
        result = downloader.download_content(url, DOWNLOAD_DIR)
        return result
    
    @staticmethod
    def preview_video(url: str) -> Dict[str, Any]:
        """
        Get video preview information
        
        Args:
            url: Video URL
            
        Returns:
            Preview data
        """
        from video_preview import preview
        return preview.get_video_info(url)
    
    @staticmethod
    def bulk_download(urls: List[str], save_to: str = 'local') -> List[Dict[str, Any]]:
        """
        Download multiple videos
        
        Args:
            urls: List of video URLs
            save_to: Where to save
            
        Returns:
            List of results
        """
        from app import downloader, DOWNLOAD_DIR
        results = []
        for url in urls:
            result = downloader.download_content(url, DOWNLOAD_DIR)
            results.append(result)
        return results
    
    @staticmethod
    def get_supported_platforms() -> List[Dict[str, str]]:
        """
        Get list of supported platforms
        
        Returns:
            List of platforms with details
        """
        return [
            {'id': 'tiktok', 'name': 'TikTok', 'icon': '🎵'},
            {'id': 'youtube', 'name': 'YouTube', 'icon': '▶️'},
            {'id': 'instagram', 'name': 'Instagram', 'icon': '📸'},
            {'id': 'twitter', 'name': 'Twitter/X', 'icon': '🐦'},
            {'id': 'facebook', 'name': 'Facebook', 'icon': '📘'},
            {'id': 'reddit', 'name': 'Reddit', 'icon': '🔴'},
            {'id': 'vimeo', 'name': 'Vimeo', 'icon': '🎬'},
            {'id': 'twitch', 'name': 'Twitch', 'icon': '📺'},
            {'id': 'dailymotion', 'name': 'Dailymotion', 'icon': '🎥'}
        ]
