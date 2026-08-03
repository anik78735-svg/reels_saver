"""
API Routes - Using dataclasses instead of pydantic
"""

import os
import json
from flask import Blueprint, request, jsonify, g
from datetime import datetime

from .schemas import (
    DownloadRequest, BulkDownloadRequest, PreviewRequest,
    DriveAuthRequest, DriveFolderRequest, ExtractRequest,
    DownloadResponse, PreviewResponse, BulkDownloadResponse, DriveResponse, ErrorResponse
)
from .middleware import APIKeyMiddleware, RateLimitMiddleware, log_request

# Import core functionality
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import downloader, drive_manager, preview, GallerySaver, extractor, DOWNLOAD_DIR, EXTRACT_DIR

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
    return jsonify({
        'version': '2.0.0',
        'name': 'Universal Social Media Downloader API',
        'features': {
            'download': True,
            'preview': True,
            'bulk': True,
            'gallery_save': True,
            'google_drive': True,
            'extraction': True,
            'platforms': ['tiktok', 'youtube', 'instagram', 'twitter', 'facebook', 'reddit', 'vimeo', 'twitch', 'dailymotion']
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
    try:
        data = request.get_json()
        if not data:
            return jsonify(ErrorResponse(message='Invalid request body', code=400).to_dict()), 400
        
        try:
            req = DownloadRequest.from_dict(data)
            req.validate()
        except ValueError as e:
            return jsonify(ErrorResponse(message=str(e), code=400).to_dict()), 400
        
        # Download content
        result = downloader.download_content(req.url, DOWNLOAD_DIR)
        
        if result.get('status') == 'success':
            if 'filepath' in result:
                filepath = result['filepath']
                filename = result.get('filename', os.path.basename(filepath))
                
                if req.save_to == 'gallery':
                    gallery_result = GallerySaver.save_to_gallery(filepath, filename)
                    result['gallery'] = gallery_result
                
                if req.save_to == 'drive':
                    drive_result = drive_manager.upload_file(filepath, filename)
                    result['drive'] = drive_result
                
                if req.extract:
                    extraction_result = extractor.extract_all(filepath, EXTRACT_DIR)
                    result['extraction'] = extraction_result
            
            return jsonify(DownloadResponse(
                status='success',
                message=result.get('message', 'Download successful'),
                data=result
            ).to_dict()), 200
        else:
            return jsonify(ErrorResponse(
                message=result.get('message', 'Download failed'),
                code=400,
                details=result
            ).to_dict()), 400
            
    except Exception as e:
        return jsonify(ErrorResponse(message=str(e), code=500).to_dict()), 500

# ============================================
# PREVIEW ENDPOINT
# ============================================

@api_bp.route('/preview', methods=['POST'])
@api_key_middleware.authenticate
@rate_limit_middleware.limit(window=60)
@log_request
def preview():
    try:
        data = request.get_json()
        if not data:
            return jsonify(ErrorResponse(message='Invalid request body', code=400).to_dict()), 400
        
        try:
            req = PreviewRequest.from_dict(data)
            req.validate()
        except ValueError as e:
            return jsonify(ErrorResponse(message=str(e), code=400).to_dict()), 400
        
        result = preview.get_video_info(req.url)
        
        if result.get('status') == 'success':
            return jsonify(PreviewResponse(
                status='success',
                message='Preview loaded',
                data=result
            ).to_dict()), 200
        else:
            return jsonify(ErrorResponse(
                message=result.get('message', 'Preview failed'),
                code=400
            ).to_dict()), 400
            
    except Exception as e:
        return jsonify(ErrorResponse(message=str(e), code=500).to_dict()), 500

# ============================================
# BULK DOWNLOAD ENDPOINT
# ============================================

@api_bp.route('/bulk', methods=['POST'])
@api_key_middleware.authenticate
@rate_limit_middleware.limit(window=120)
@log_request
def bulk_download():
    try:
        data = request.get_json()
        if not data:
            return jsonify(ErrorResponse(message='Invalid request body', code=400).to_dict()), 400
        
        try:
            req = BulkDownloadRequest.from_dict(data)
            req.validate()
        except ValueError as e:
            return jsonify(ErrorResponse(message=str(e), code=400).to_dict()), 400
        
        results = []
        successful = 0
        failed = 0
        
        for url in req.urls:
            result = downloader.download_content(url, DOWNLOAD_DIR)
            
            if result.get('status') == 'success':
                successful += 1
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
                'url': url,
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
        ).to_dict()), 200
            
    except Exception as e:
        return jsonify(ErrorResponse(message=str(e), code=500).to_dict()), 500

# ============================================
# EXTRACTION ENDPOINT
# ============================================

@api_bp.route('/extract', methods=['POST'])
@api_key_middleware.authenticate
@rate_limit_middleware.limit(window=30)
@log_request
def extract():
    try:
        data = request.get_json()
        if not data:
            return jsonify(ErrorResponse(message='Invalid request body', code=400).to_dict()), 400
        
        try:
            req = ExtractRequest.from_dict(data)
            req.validate()
        except ValueError as e:
            return jsonify(ErrorResponse(message=str(e), code=400).to_dict()), 400
        
        # Find the file
        file_path = None
        for root, dirs, files in os.walk(DOWNLOAD_DIR):
            if req.filename in files:
                file_path = os.path.join(root, req.filename)
                break
        
        if not file_path:
            return jsonify(ErrorResponse(message='File not found', code=404).to_dict()), 404
        
        if req.extract_type == 'all':
            result = extractor.extract_all(file_path, EXTRACT_DIR)
        elif req.extract_type == 'audio':
            result = extractor.extract_audio(file_path, EXTRACT_DIR)
        elif req.extract_type == 'thumbnail':
            result = extractor.extract_thumbnail(file_path, EXTRACT_DIR)
        elif req.extract_type == 'subtitles':
            result = extractor.extract_subtitles(file_path, EXTRACT_DIR)
        elif req.extract_type == 'metadata':
            result = extractor.extract_metadata(file_path)
        else:
            return jsonify(ErrorResponse(message='Invalid extract_type', code=400).to_dict()), 400
        
        return jsonify(DownloadResponse(
            status='success',
            message='Extraction completed',
            data=result
        ).to_dict()), 200
        
    except Exception as e:
        return jsonify(ErrorResponse(message=str(e), code=500).to_dict()), 500

# ============================================
# GOOGLE DRIVE ENDPOINTS
# ============================================

@api_bp.route('/drive/auth', methods=['POST'])
@api_key_middleware.authenticate
@rate_limit_middleware.limit(window=30)
@log_request
def drive_auth():
    try:
        data = request.get_json() or {}
        try:
            req = DriveAuthRequest.from_dict(data)
            req.validate()
        except ValueError as e:
            return jsonify(ErrorResponse(message=str(e), code=400).to_dict()), 400
        
        if req.action == 'status':
            if drive_manager.service:
                user_info = drive_manager.service.about().get(fields='user').execute()
                return jsonify(DriveResponse(
                    status='success',
                    message='Connected',
                    data={
                        'connected': True,
                        'email': user_info['user']['emailAddress']
                    }
                ).to_dict()), 200
            else:
                return jsonify(DriveResponse(
                    status='success',
                    message='Not connected',
                    data={'connected': False}
                ).to_dict()), 200
        
        elif req.action == 'connect':
            if req.code:
                result = drive_manager.authenticate_with_code(req.code)
                if result.get('status') == 'success':
                    return jsonify(DriveResponse(
                        status='success',
                        message=result.get('message'),
                        data={
                            'connected': True,
                            'email': result.get('email')
                        }
                    ).to_dict()), 200
                else:
                    return jsonify(ErrorResponse(
                        message=result.get('message', 'Authentication failed'),
                        code=400
                    ).to_dict()), 400
            else:
                result = drive_manager.get_auth_url()
                if result.get('status') == 'success':
                    return jsonify(DriveResponse(
                        status='success',
                        message='Please visit the auth URL',
                        data={
                            'auth_url': result.get('auth_url'),
                            'connected': False
                        }
                    ).to_dict()), 200
                else:
                    return jsonify(ErrorResponse(
                        message=result.get('message', 'Failed to get auth URL'),
                        code=400
                    ).to_dict()), 400
        
        return jsonify(ErrorResponse(message='Invalid action', code=400).to_dict()), 400
            
    except Exception as e:
        return jsonify(ErrorResponse(message=str(e), code=500).to_dict()), 500

@api_bp.route('/drive/folders', methods=['GET', 'POST'])
@api_key_middleware.authenticate
@rate_limit_middleware.limit(window=30)
@log_request
def drive_folders():
    try:
        if request.method == 'GET':
            result = drive_manager.list_folders()
            if result.get('status') == 'success':
                return jsonify(DriveResponse(
                    status='success',
                    message='Folders loaded',
                    data={'folders': result.get('folders', [])}
                ).to_dict()), 200
            else:
                return jsonify(ErrorResponse(
                    message=result.get('message', 'Failed to load folders'),
                    code=400
                ).to_dict()), 400
        
        else:
            data = request.get_json() or {}
            try:
                req = DriveFolderRequest.from_dict(data)
                req.validate()
            except ValueError as e:
                return jsonify(ErrorResponse(message=str(e), code=400).to_dict()), 400
            
            if req.action == 'list':
                result = drive_manager.list_folders()
                if result.get('status') == 'success':
                    return jsonify(DriveResponse(
                        status='success',
                        message='Folders loaded',
                        data={'folders': result.get('folders', [])}
                    ).to_dict()), 200
            
            elif req.action == 'select':
                result = drive_manager.select_folder(req.folder_id, req.folder_name or '')
                if result.get('status') == 'success':
                    return jsonify(DriveResponse(
                        status='success',
                        message=result.get('message'),
                        data={'selected': True}
                    ).to_dict()), 200
            
            elif req.action == 'create':
                result = drive_manager.create_folder(req.folder_name)
                if result.get('status') == 'success':
                    return jsonify(DriveResponse(
                        status='success',
                        message=f"Folder created: {result.get('folder_name')}",
                        data={
                            'folder_id': result.get('folder_id'),
                            'folder_name': result.get('folder_name')
                        }
                    ).to_dict()), 200
            
            return jsonify(ErrorResponse(message='Invalid action', code=400).to_dict()), 400
            
    except Exception as e:
        return jsonify(ErrorResponse(message=str(e), code=500).to_dict()), 500

@api_bp.route('/drive/upload', methods=['POST'])
@api_key_middleware.authenticate
@rate_limit_middleware.limit(window=30)
@log_request
def drive_upload():
    try:
        data = request.get_json()
        if not data:
            return jsonify(ErrorResponse(message='Invalid request body', code=400).to_dict()), 400
        
        filename = data.get('filename')
        if not filename:
            return jsonify(ErrorResponse(message='filename required', code=400).to_dict()), 400
        
        file_path = None
        for root, dirs, files in os.walk(DOWNLOAD_DIR):
            if filename in files:
                file_path = os.path.join(root, filename)
                break
        
        if not file_path:
            return jsonify(ErrorResponse(message='File not found', code=404).to_dict()), 404
        
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
            ).to_dict()), 200
        else:
            return jsonify(ErrorResponse(
                message=result.get('message', 'Upload failed'),
                code=400
            ).to_dict()), 400
            
    except Exception as e:
        return jsonify(ErrorResponse(message=str(e), code=500).to_dict()), 500

# ============================================
# PLATFORMS ENDPOINT
# ============================================

@api_bp.route('/platforms', methods=['GET'])
@api_key_middleware.authenticate
@log_request
def get_platforms():
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
