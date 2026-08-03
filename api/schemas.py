
"""
API Request/Response Schemas - Using dataclasses instead of pydantic
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

# ============================================
# REQUEST SCHEMAS
# ============================================

@dataclass
class DownloadRequest:
    """Download request schema"""
    url: str
    save_to: str = 'local'
    platform: Optional[str] = None
    quality: str = 'best'
    format: str = 'mp4'
    extract: bool = False
    
    def validate(self):
        if not self.url:
            raise ValueError('URL is required')
        if self.save_to not in ['local', 'gallery', 'drive']:
            raise ValueError('save_to must be local, gallery, or drive')
        if self.quality not in ['best', 'high', 'medium', 'low']:
            raise ValueError('quality must be best, high, medium, or low')
        return True
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            url=data.get('url', ''),
            save_to=data.get('save_to', 'local'),
            platform=data.get('platform'),
            quality=data.get('quality', 'best'),
            format=data.get('format', 'mp4'),
            extract=data.get('extract', False)
        )

@dataclass
class BulkDownloadRequest:
    """Bulk download request schema"""
    urls: List[str]
    save_to: str = 'local'
    quality: str = 'best'
    
    def validate(self):
        if not self.urls:
            raise ValueError('URLs list is required')
        if len(self.urls) > 50:
            raise ValueError('Maximum 50 URLs allowed')
        if self.save_to not in ['local', 'gallery', 'drive']:
            raise ValueError('save_to must be local, gallery, or drive')
        return True
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            urls=data.get('urls', []),
            save_to=data.get('save_to', 'local'),
            quality=data.get('quality', 'best')
        )

@dataclass
class PreviewRequest:
    """Preview request schema"""
    url: str
    
    def validate(self):
        if not self.url:
            raise ValueError('URL is required')
        return True
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(url=data.get('url', ''))

@dataclass
class DriveAuthRequest:
    """Google Drive authentication request"""
    action: str = 'connect'
    code: Optional[str] = None
    
    def validate(self):
        if self.action not in ['connect', 'status']:
            raise ValueError('action must be connect or status')
        return True
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            action=data.get('action', 'connect'),
            code=data.get('code')
        )

@dataclass
class DriveFolderRequest:
    """Google Drive folder request"""
    action: str = 'list'
    folder_id: Optional[str] = None
    folder_name: Optional[str] = None
    
    def validate(self):
        if self.action not in ['list', 'select', 'create']:
            raise ValueError('action must be list, select, or create')
        if self.action == 'select' and not self.folder_id:
            raise ValueError('folder_id required for select action')
        if self.action == 'create' and not self.folder_name:
            raise ValueError('folder_name required for create action')
        return True
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            action=data.get('action', 'list'),
            folder_id=data.get('folder_id'),
            folder_name=data.get('folder_name')
        )

@dataclass
class ExtractRequest:
    """Extraction request schema"""
    filename: str
    extract_type: str = 'all'
    
    def validate(self):
        if not self.filename:
            raise ValueError('Filename required')
        if self.extract_type not in ['all', 'audio', 'thumbnail', 'subtitles', 'metadata']:
            raise ValueError('Invalid extract_type')
        return True
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            filename=data.get('filename', ''),
            extract_type=data.get('extract_type', 'all')
        )

# ============================================
# RESPONSE SCHEMAS
# ============================================

@dataclass
class BaseResponse:
    """Base response schema"""
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self):
        result = {
            'status': self.status,
            'message': self.message,
            'timestamp': self.timestamp
        }
        if self.data is not None:
            result['data'] = self.data
        return result

@dataclass
class ErrorResponse:
    """Error response schema"""
    status: str = 'error'
    message: str = ''
    code: int = 400
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self):
        result = {
            'status': self.status,
            'message': self.message,
            'code': self.code
        }
        if self.details is not None:
            result['details'] = self.details
        return result

@dataclass
class DownloadResponse(BaseResponse):
    pass

@dataclass
class PreviewResponse(BaseResponse):
    pass

@dataclass
class BulkDownloadResponse(BaseResponse):
    pass

@dataclass
class DriveResponse(BaseResponse):
    pass
