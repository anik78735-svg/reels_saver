"""
Async Python SDK Client for Universal Social Media Downloader API
"""

import aiohttp
import asyncio
from typing import Optional, Dict, Any, List, Union
from urllib.parse import urljoin

class AsyncSocialDownloaderClient:
    """
    Async Python client for Universal Social Media Downloader API
    
    Usage:
        client = AsyncSocialDownloaderClient(
            api_key="your-api-key",
            base_url="https://your-app.onrender.com/api"
        )
        
        # Download video (async)
        result = await client.download("https://www.tiktok.com/@user/video/123456789")
        
        # Bulk download (async)
        results = await client.bulk_download([
            "https://www.tiktok.com/@user/video/123456789",
            "https://www.youtube.com/watch?v=abc123"
        ])
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.socialdownloader.com",
        timeout: int = 60,
        max_retries: int = 3
    ):
        """
        Initialize the async SDK client
        
        Args:
            api_key: Your API key
            base_url: API base URL
            timeout: Request timeout in seconds
            max_retries: Number of retries for failed requests
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={
                    'X-API-Key': self.api_key,
                    'Content-Type': 'application/json',
                    'User-Agent': f'SocialDownloaderSDK/2.0.0 (Async)'
                },
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make an async API request with retries
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            data: Request body
            params: Query parameters
            
        Returns:
            API response as dict
        """
        url = urljoin(self.base_url, endpoint)
        session = await self._get_session()
        
        for attempt in range(self.max_retries):
            try:
                async with session.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params
                ) as response:
                    if response.status >= 400:
                        error_text = await response.text()
                        raise Exception(f"API Error {response.status}: {error_text}")
                    
                    return await response.json()
                    
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt == self.max_retries - 1:
                    raise e
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        raise Exception("Max retries exceeded")
    
    async def close(self):
        """Close the aiohttp session"""
        if self._session:
            await self._session.close()
            self._session = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    # ============================================
    # CORE METHODS (Async)
    # ============================================
    
    async def download(
        self,
        url: str,
        save_to: str = 'local',
        quality: str = 'best',
        format: str = 'mp4'
    ) -> Dict[str, Any]:
        """Async download a video"""
        return await self._request(
            method='POST',
            endpoint='/download',
            data={
                'url': url,
                'save_to': save_to,
                'quality': quality,
                'format': format
            }
        )
    
    async def preview(self, url: str) -> Dict[str, Any]:
        """Async get video preview"""
        return await self._request(
            method='POST',
            endpoint='/preview',
            data={'url': url}
        )
    
    async def bulk_download(
        self,
        urls: List[str],
        save_to: str = 'local',
        quality: str = 'best'
    ) -> Dict[str, Any]:
        """Async bulk download"""
        return await self._request(
            method='POST',
            endpoint='/bulk',
            data={
                'urls': urls,
                'save_to': save_to,
                'quality': quality
            }
        )
    
    # ============================================
    # DRIVE METHODS (Async)
    # ============================================
    
    async def drive_status(self) -> Dict[str, Any]:
        """Async check drive status"""
        return await self._request(
            method='POST',
            endpoint='/drive/auth',
            data={'action': 'status'}
        )
    
    async def drive_connect(self) -> Dict[str, Any]:
        """Async get drive auth URL"""
        return await self._request(
            method='POST',
            endpoint='/drive/auth',
            data={'action': 'connect'}
        )
    
    async def drive_authenticate(self, code: str) -> Dict[str, Any]:
        """Async complete drive authentication"""
        return await self._request(
            method='POST',
            endpoint='/drive/auth',
            data={
                'action': 'connect',
                'code': code
            }
        )
    
    async def drive_list_folders(self) -> Dict[str, Any]:
        """Async list drive folders"""
        return await self._request(
            method='GET',
            endpoint='/drive/folders'
        )
    
    async def drive_select_folder(self, folder_id: str, folder_name: str = '') -> Dict[str, Any]:
        """Async select drive folder"""
        return await self._request(
            method='POST',
            endpoint='/drive/folders',
            data={
                'action': 'select',
                'folder_id': folder_id,
                'folder_name': folder_name
            }
        )
    
    async def drive_create_folder(self, folder_name: str) -> Dict[str, Any]:
        """Async create drive folder"""
        return await self._request(
            method='POST',
            endpoint='/drive/folders',
            data={
                'action': 'create',
                'folder_name': folder_name
            }
        )
    
    async def drive_upload(self, filename: str, folder_id: Optional[str] = None) -> Dict[str, Any]:
        """Async upload to drive"""
        return await self._request(
            method='POST',
            endpoint='/drive/upload',
            data={
                'filename': filename,
                'folder_id': folder_id
            }
        )
