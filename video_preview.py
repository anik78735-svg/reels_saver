import os
import re
import requests
from urllib.parse import urlparse
import yt_dlp

class VideoPreview:
    def __init__(self):
        self.preview_cache = {}
    
    def get_video_info(self, url):
        """Get video information without downloading"""
        platform = self.detect_platform(url)
        
        try:
            # For TikTok, use TikWM API
            if platform == 'tiktok':
                return self.get_tiktok_info(url)
            
            # For other platforms, use yt-dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'format': 'best',
                'ignoreerrors': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    return {
                        'status': 'success',
                        'title': info.get('title', 'Unknown'),
                        'uploader': info.get('uploader', 'Unknown'),
                        'duration': info.get('duration', 0),
                        'thumbnail': info.get('thumbnail', ''),
                        'views': info.get('view_count', 0),
                        'likes': info.get('like_count', 0),
                        'description': info.get('description', '')[:200],
                        'platform': platform,
                        'url': url
                    }
            
            return {'status': 'error', 'message': 'Could not get video info'}
            
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def get_tiktok_info(self, url):
        """Get TikTok video info using TikWM API"""
        try:
            response = requests.get(
                'https://www.tikwm.com/api/',
                params={'url': url, 'hd': 1},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    video_data = data['data']
                    return {
                        'status': 'success',
                        'title': video_data.get('title', 'TikTok Video'),
                        'uploader': video_data.get('author', {}).get('unique_id', 'Unknown'),
                        'duration': video_data.get('duration', 0),
                        'thumbnail': video_data.get('cover', ''),
                        'views': video_data.get('play_count', 0),
                        'likes': video_data.get('digg_count', 0),
                        'comments': video_data.get('comment_count', 0),
                        'shares': video_data.get('share_count', 0),
                        'platform': 'tiktok',
                        'url': url,
                        'video_url': video_data.get('play', '')
                    }
            
            return {'status': 'error', 'message': 'Failed to get TikTok info'}
            
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def detect_platform(self, url):
        """Detect platform from URL"""
        url = url.lower()
        if 'tiktok.com' in url:
            return 'tiktok'
        elif 'youtube.com' in url or 'youtu.be' in url:
            return 'youtube'
        elif 'instagram.com' in url:
            return 'instagram'
        elif 'twitter.com' in url or 'x.com' in url:
            return 'twitter'
        elif 'facebook.com' in url:
            return 'facebook'
        elif 'reddit.com' in url:
            return 'reddit'
        else:
            return 'other'

preview = VideoPreview()
