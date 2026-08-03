"""
Python SDK for Universal Social Media Downloader API
"""

from .client import SocialDownloaderClient
from .async_client import AsyncSocialDownloaderClient

__version__ = '2.0.0'
__all__ = [
    'SocialDownloaderClient',
    'AsyncSocialDownloaderClient',
    '__version__'
]
