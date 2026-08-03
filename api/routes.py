"""
API Routes - RESTful endpoints for developers
"""

import os
import json
from flask import Blueprint, request, jsonify, g
from typing import Dict, Any

from .schemas import (
    DownloadRequest, BulkDownloadRequest, PreviewRequest,
    DriveAuthRequest, DriveFolderRequest,
    DownloadResponse, PreviewResponse, BulkDownloadResponse, DriveResponse, ErrorResponse
)
from .middleware import APIKeyMiddleware, RateLimitMiddleware, log_request

# Import core functionality
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import downloader, drive_manager, preview, GallerySaver, DOWNLOAD_DIR

# Initialize middleware
api_key_middleware = APIKeyMiddleware()
rate_limit_middleware = RateLimitMiddleware()

# Create blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

# ============================================
# HEALTH CHECK
# ============================================

@api_bp.route('/health', methods=['GET'])
def health_check():
    """API health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'version': '2.0.0',
        'timestamp': datetime.now().isoformat(),
        'platforms': ['tiktok', 'youtube', 'instagram', 'twitter', 'facebook', 'reddit', 'vimeo', 'twitch', 'dailymotion']
    })

# ============================================
# VERSION INFO
# ============================================

@api_bp.route('/version', methods=['GET'])
def version_info():
    """Get API version and features"""
    return jsonify({
        'version': '2.0.0',
        'name': 'Universal Social Media Downloader API',
        'features': {
            'download': True,
            'preview': True,
            'bulk': True,
            'gallery_save': True,
            'google_drive': True,
            'platforms': ['tiktok', 'youtube', 'instagram', 'twitter', 'facebook', 'reddit', 'vimeo', 'twitch', 'dailymotion']
        },
        'rate_limit': {
            'default': 100,
            'window': 60
        }
    })

# ============================================
# DOWNLOAD ENDPOINT
# ============================================

@api_bp.route('/download', methods=['POST'])
@api_key_middleware.authenticate
@rate_limit_middleware.limit(window=60)
@log_request
def download():
    """
    Download a video from any supported platform
    
    Request body:
    {
        "url": "https://www.tiktok.com/@user/video/123456789",
        "save_to": "local",  // local, gallery, drive
        "quality": "best",    // best, high, medium, low
        "format": "mp4"       // mp4, webm
    }
    
    Response:
    {
        "status": "success",
        "message": "Video downloaded successfully!",
        "data": {
            "filename": "video.mp4",
            "filepath": "/path/to/video.mp4",
            "title": "Video Title",
            "uploader": "Username",
            "platform": "tiktok",
            "size": 1048576
        }
    }
    """
    try:
        # Validate request
        data = request.get_json()
        if not data:
            return jsonify(ErrorResponse(
                message='Invalid request body',
                code=400
            ).dict()), 400
        
        # Parse request
        req = DownloadRequest(**data)
        
        # Download content
        result = downloader.download_content(str(req.url), DOWNLOAD_DIR)
        
        if result.get('status') == 'success':
            # Handle save options
            if req.save_to == 'gallery' and 'filepath' in result:
                gallery_result = GallerySaver.save_to_gallery(
                    result['filepath'],
                    result.get('filename', os.path.basename(result['filepath']))
                )
                result['gallery'] = gallery_result
            
            if req.save_to == 'drive' and 'filepath' in result:
                drive_result = drive_manager.upload_file(
                    result['filepath'],
                    result.get('filename', os.path.basename(result['filepath']))
                )
                result['drive'] = drive_result
            
            return jsonify(DownloadResponse(
                status='success',
                message=result.get('message', 'Download successful'),
                data=result
            ).dict()), 200
        else:
            return jsonify(ErrorResponse(
                message=result.get('message', 'Download failed'),
                code=400,
                details=result
            ).dict()), 400
            
    except Exception as e:
        return jsonify(ErrorResponse(
            message=str(e),
            code=500
        ).dict()), 500

# ============================================
# PREVIEW ENDPOINT
# ============================================

@api_bp.route('/preview', methods=['POST'])
@api_key_middleware.authenticate
@rate_limit_middleware.limit(window=60)
@log_request
def preview():
    """
    Get video preview information
    
    Request body:
    {
        "url": "https://www.tiktok.com/@user/video/123456789"
    }
    
    Response:
    {
        "status": "success",
        "message": "Preview loaded",
        "data": {
            "title": "Video Title",
            "uploader": "Username",
            "duration": 60,
            "thumbnail": "https://...",
            "views": 1000,
            "likes": 100,
            "platform": "tiktok"
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify(ErrorResponse(
                message='Invalid request body',
                code=400
            ).dict()), 400
        
        req = PreviewRequest(**data)
        
        # Get preview
        result = preview.get_video_info(str(req.url))
        
        if result.get('status') == 'success':
            return jsonify(PreviewResponse(
                status='success',
                message='Preview loaded',
                data=result
            ).dict()), 200
        else:
            return jsonify(ErrorResponse(
                message=result.get('message', 'Preview failed'),
                code=400
            ).dict()), 400
            
    except Exception as e:
        return jsonify(ErrorResponse(
            message=str(e),
            code=500
        ).dict()), 500

# ============================================
# BULK DOWNLOAD ENDPOINT
# ============================================

@api_bp.route('/bulk', methods=['POST'])
@api_key_middleware.authenticate
@rate_limit_middleware.limit(window=120)
@log_request
def bulk_download():
    """
    Download multiple videos
    
    Request body:
    {
        "urls": [
            "https://www.tiktok.com/@user/video/123456789",
            "https://www.youtube.com/watch?v=abc123"
        ],
        "save_to": "local",
        "quality": "best"
    }
    
    Response:
    {
        "status": "success",
        "message": "Processed 2 URLs",
        "data": {
            "total": 2,
            "successful": 2,
            "failed": 0,
            "results": [...]
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify(ErrorResponse(
                message='Invalid request body',
                code=400
            ).dict()), 400
        
        req = BulkDownloadRequest(**data)
        
        results = []
        successful = 0
        failed = 0
        
        for url in req.urls:
            result = downloader.download_content(str(url), DOWNLOAD_DIR)
            
            if result.get('status') == 'success':
                successful += 1
                # Handle save options
                if req.save_to == 'gallery' and 'filepath' in result:
                    gallery_result = GallerySaver.save_to_gallery(
                        result['filepath'],
                        result.get('filename', os.path.basename(result['filepath']))
                    )
                    result['gallery'] = gallery_result
                
                if req.save_to == 'drive' and 'filepath' in result:
                    drive_result = drive_manager.upload_file(
                        result['filepath'],
                        result.get('filename', os.path.basename(result['filepath']))
                    )
                    result['drive'] = drive_result
            else:
                failed += 1
            
            results.append({
                'url': str(url),
                'status': result.get('status'),
                'message': result.get('message', 'Unknown'),
                'data': result if result.get('status') == 'success' else None
            })
        
        return jsonify(BulkDownloadResponse(
            status='success',
            message=f'Processed {len(req.urls)} URLs',
            data={
                'total': len(req.urls),
                'successful': successful,
                'failed': failed,
                'results': results
            }
        ).dict()), 200
            
    except Exception as e:
        return jsonify(ErrorResponse(
            message=str(e),
            code=500
        ).dict()), 500

# ============================================
# GOOGLE DRIVE ENDPOINTS
# ============================================

@api_bp.route('/drive/auth', methods=['POST'])
@api_key_middleware.authenticate
@rate_limit_middleware.limit(window=30)
@log_request
def drive_auth():
    """
    Authenticate with Google Drive
    
    Request body:
    {
        "action": "connect",  // connect, status
        "code": "auth_code"   // Optional, for callback
    }
    
    Response:
    {
        "status": "success",
        "message": "Connected to user@email.com",
        "data": {
            "connected": true,
            "email": "user@email.com"
        }
    }
    """
    try:
        data = request.get_json() or {}
        req = DriveAuthRequest(**data)
        
        if req.action == 'status':
            # Check connection status
            if drive_manager.service:
                user_info = drive_manager.service.about().get(fields='user').execute()
                return jsonify(DriveResponse(
                    status='success',
                    message='Connected',
                    data={
                        'connected': True,
                        'email': user_info['user']['emailAddress']
                    }
                ).dict()), 200
            else:
                return jsonify(DriveResponse(
                    status='success',
                    message='Not connected',
                    data={'connected': False}
                ).dict()), 200
        
        elif req.action == 'connect':
            if req.code:
                # Authenticate with code
                result = drive_manager.authenticate_with_code(req.code)
                if result.get('status') == 'success':
                    return jsonify(DriveResponse(
                        status='success',
                        message=result.get('message'),
                        data={
                            'connected': True,
                            'email': result.get('email')
                        }
                    ).dict()), 200
                else:
                    return jsonify(ErrorResponse(
                        message=result.get('message', 'Authentication failed'),
                        code=400
                    ).dict()), 400
            else:
                # Get auth URL
                result = drive_manager.get_auth_url()
                if result.get('status') == 'success':
                    return jsonify(DriveResponse(
                        status='success',
                        message='Please visit the auth URL',
                        data={
                            'auth_url': result.get('auth_url'),
                            'connected': False
                        }
                    ).dict()), 200
                else:
                    return jsonify(ErrorResponse(
                        message=result.get('message', 'Failed to get auth URL'),
                        code=400
                    ).dict()), 400
        
        return jsonify(ErrorResponse(
            message='Invalid action',
            code=400
        ).dict()), 400
            
    except Exception as e:
        return jsonify(ErrorResponse(
            message=str(e),
            code=500
        ).dict()), 500

@api_bp.route('/drive/folders', methods=['GET', 'POST'])
@api_key_middleware.authenticate
@rate_limit_middleware.limit(window=30)
@log_request
def drive_folders():
    """
    Manage Google Drive folders
    
    GET: List folders
    POST: Create or select folder
    
    Request body (POST):
    {
        "action": "list",  // list, select, create
        "folder_id": "folder_id",  // For select
        "folder_name": "folder_name"  // For create
    }
    
    Response:
    {
        "status": "success",
        "message": "Folders loaded",
        "data": {
            "folders": [...]
        }
    }
    """
    try:
        if request.method == 'GET':
            # List folders
            result = drive_manager.list_folders()
            if result.get('status') == 'success':
                return jsonify(DriveResponse(
                    status='success',
                    message='Folders loaded',
                    data={'folders': result.get('folders', [])}
                ).dict()), 200
            else:
                return jsonify(ErrorResponse(
                    message=result.get('message', 'Failed to load folders'),
                    code=400
                ).dict()), 400
        
        else:  # POST
            data = request.get_json() or {}
            req = DriveFolderRequest(**data)
            
            if req.action == 'list':
                result = drive_manager.list_folders()
                if result.get('status') == 'success':
                    return jsonify(DriveResponse(
                        status='success',
                        message='Folders loaded',
                        data={'folders': result.get('folders', [])}
                    ).dict()), 200
            
            elif req.action == 'select':
                if not req.folder_id:
                    return jsonify(ErrorResponse(
                        message='folder_id required for select action',
                        code=400
                    ).dict()), 400
                
                result = drive_manager.select_folder(req.folder_id, req.folder_name or '')
                if result.get('status') == 'success':
                    return jsonify(DriveResponse(
                        status='success',
                        message=result.get('message'),
                        data={'selected': True}
                    ).dict()), 200
            
            elif req.action == 'create':
                if not req.folder_name:
                    return jsonify(ErrorResponse(
                        message='folder_name required for create action',
                        code=400
                    ).dict()), 400
                
                result = drive_manager.create_folder(req.folder_name)
                if result.get('status') == 'success':
                    return jsonify(DriveResponse(
                        status='success',
                        message=f"Folder created: {result.get('folder_name')}",
                        data={
                            'folder_id': result.get('folder_id'),
                            'folder_name': result.get('folder_name')
                        }
                    ).dict()), 200
            
            return jsonify(ErrorResponse(
                message='Invalid action',
                code=400
            ).dict()), 400
            
    except Exception as e:
        return jsonify(ErrorResponse(
            message=str(e),
            code=500
        ).dict()), 500

@api_bp.route('/drive/upload', methods=['POST'])
@api_key_middleware.authenticate
@rate_limit_middleware.limit(window=30)
@log_request
def drive_upload():
    """
    Upload a file to Google Drive
    
    Request body:
    {
        "filename": "video.mp4",
        "folder_id": "folder_id"  // Optional, uses selected folder if not provided
    }
    
    Response:
    {
        "status": "success",
        "message": "Uploaded to Drive: video.mp4",
        "data": {
            "file_id": "file_id",
            "web_link": "https://drive.google.com/..."
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify(ErrorResponse(
                message='Invalid request body',
                code=400
            ).dict()), 400
        
        filename = data.get('filename')
        if not filename:
            return jsonify(ErrorResponse(
                message='filename required',
                code=400
            ).dict()), 400
        
        # Find file in downloads
        file_path = None
        for root, dirs, files in os.walk(DOWNLOAD_DIR):
            if filename in files:
                file_path = os.path.join(root, filename)
                break
        
        if not file_path:
            return jsonify(ErrorResponse(
                message='File not found',
                code=404
            ).dict()), 404
        
        folder_id = data.get('folder_id')
        result = drive_manager.upload_file(file_path, filename, folder_id)
        
        if result.get('status') == 'success':
            return jsonify(DriveResponse(
                status='success',
                message=result.get('message'),
                data={
                    'file_id': result.get('file_id'),
                    'web_link': result.get('web_link')
                }
            ).dict()), 200
        else:
            return jsonify(ErrorResponse(
                message=result.get('message', 'Upload failed'),
                code=400
            ).dict()), 400
            
    except Exception as e:
        return jsonify(ErrorResponse(
            message=str(e),
            code=500
        ).dict()), 500

# ============================================
# PLATFORMS ENDPOINT
# ============================================

@api_bp.route('/platforms', methods=['GET'])
@api_key_middleware.authenticate
@log_request
def get_platforms():
    """Get list of supported platforms"""
    return jsonify({
        'status': 'success',
        'data': {
            'platforms': [
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
        }
    })
