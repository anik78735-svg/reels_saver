"""
Python SDK Client for Universal Social Media Downloader API
"""

import os
import json
import requests
from typing import Optional, Dict, Any, List, Union
from urllib.parse import urljoin

class SocialDownloaderClient:
    """
    Python client for Universal Social Media Downloader API
    
    Usage:
        client = SocialDownloaderClient(
            api_key="your-api-key",
            base_url="https://your-app.onrender.com/api"
        )
        
        # Download video
        result = client.download("https://www.tiktok.com/@user/video/123456789")
        
        # Preview video
        preview = client.preview("https://www.youtube.com/watch?v=abc123")
        
        # Bulk download
        results = client.bulk_download([
            "https://www.tiktok.com/@user/video/123456789",
            "https://www.youtube.com/watch?v=abc123"
        ])
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.socialdownloader.com",
        timeout: int = 60,
        retry_count: int = 3
    ):
        """
        Initialize the SDK client
        
        Args:
            api_key: Your API key
            base_url: API base URL
            timeout: Request timeout in seconds
            retry_count: Number of retries for failed requests
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.retry_count = retry_count
        self.session = requests.Session()
        self.session.headers.update({
            'X-API-Key': api_key,
            'Content-Type': 'application/json',
            'User-Agent': f'SocialDownloaderSDK/2.0.0'
        })
    
    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make an API request with retries
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            data: Request body
            params: Query parameters
            
        Returns:
            API response as dict
        """
        url = urljoin(self.base_url, endpoint)
        
        for attempt in range(self.retry_count):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    timeout=self.timeout
                )
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                if attempt == self.retry_count - 1:
                    raise e
                continue
        
        raise Exception("Max retries exceeded")
    
    # ============================================
    # CORE METHODS
    # ============================================
    
    def download(
        self,
        url: str,
        save_to: str = 'local',
        quality: str = 'best',
        format: str = 'mp4'
    ) -> Dict[str, Any]:
        """
        Download a video
        
        Args:
            url: Video URL
            save_to: Save destination (local, gallery, drive)
            quality: Video quality (best, high, medium, low)
            format: Output format (mp4, webm)
            
        Returns:
            Download result
        """
        return self._request(
            method='POST',
            endpoint='/download',
            data={
                'url': url,
                'save_to': save_to,
                'quality': quality,
                'format': format
            }
        )
    
    def preview(self, url: str) -> Dict[str, Any]:
        """
        Get video preview information
        
        Args:
            url: Video URL
            
        Returns:
            Preview data (title, uploader, thumbnail, etc.)
        """
        return self._request(
            method='POST',
            endpoint='/preview',
            data={'url': url}
        )
    
    def bulk_download(
        self,
        urls: List[str],
        save_to: str = 'local',
        quality: str = 'best'
    ) -> Dict[str, Any]:
        """
        Download multiple videos
        
        Args:
            urls: List of video URLs
            save_to: Save destination
            quality: Video quality
            
        Returns:
            Bulk download results
        """
        return self._request(
            method='POST',
            endpoint='/bulk',
            data={
                'urls': urls,
                'save_to': save_to,
                'quality': quality
            }
        )
    
    # ============================================
    # DRIVE METHODS
    # ============================================
    
    def drive_status(self) -> Dict[str, Any]:
        """
        Check Google Drive connection status
        
        Returns:
            Connection status
        """
        return self._request(
            method='POST',
            endpoint='/drive/auth',
            data={'action': 'status'}
        )
    
    def drive_connect(self) -> Dict[str, Any]:
        """
        Get Google Drive authentication URL
        
        Returns:
            Auth URL for user to visit
        """
        return self._request(
            method='POST',
            endpoint='/drive/auth',
            data={'action': 'connect'}
        )
    
    def drive_authenticate(self, code: str) -> Dict[str, Any]:
        """
        Complete Google Drive authentication with authorization code
        
        Args:
            code: OAuth authorization code
            
        Returns:
            Authentication result
        """
        return self._request(
            method='POST',
            endpoint='/drive/auth',
            data={
                'action': 'connect',
                'code': code
            }
        )
    
    def drive_list_folders(self) -> Dict[str, Any]:
        """
        List Google Drive folders
        
        Returns:
            List of folders
        """
        return self._request(
            method='GET',
            endpoint='/drive/folders'
        )
    
    def drive_select_folder(self, folder_id: str, folder_name: str = '') -> Dict[str, Any]:
        """
        Select a folder for uploads
        
        Args:
            folder_id: Folder ID
            folder_name: Folder name (optional)
            
        Returns:
            Selection result
        """
        return self._request(
            method='POST',
            endpoint='/drive/folders',
            data={
                'action': 'select',
                'folder_id': folder_id,
                'folder_name': folder_name
            }
        )
    
    def drive_create_folder(self, folder_name: str) -> Dict[str, Any]:
        """
        Create a new folder in Google Drive
        
        Args:
            folder_name: Folder
