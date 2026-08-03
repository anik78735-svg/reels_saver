import os
import pickle
import json
import re
import time
import shutil
import tempfile
import zipfile
import http.client
from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from urllib.parse import urlparse

# Flask imports
from flask import Flask, request, render_template, jsonify, send_file, session

# Google Drive imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Third party imports
import yt_dlp
import instaloader
import requests
from werkzeug.utils import secure_filename

# ============================================
# APP INITIALIZATION
# ============================================

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-this')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['SESSION_TYPE'] = 'filesystem'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# Create directories
DOWNLOAD_DIR = os.path.join(os.getcwd(), 'downloads')
TEMP_DIR = os.path.join(os.getcwd(), 'temp')
EXTRACT_DIR = os.path.join(os.getcwd(), 'extractions')

for directory in [DOWNLOAD_DIR, TEMP_DIR, EXTRACT_DIR]:
    os.makedirs(directory, exist_ok=True)

# ============================================
# RAPIDAPI CONFIGURATION
# ============================================

RAPIDAPI_KEY = os.environ.get('RAPIDAPI_KEY', 'e7e2b4ac57mshf5be36f57ac2478p1511dbjsne2dce6703f94')

# ============================================
# GOOGLE DRIVE MANAGER
# ============================================

SCOPES = ['https://www.googleapis.com/auth/drive.file']

class GoogleDriveManager:
    def __init__(self):
        self.creds = None
        self.service = None
        self.token_file = 'token.pickle'
        self.selected_folder_id = None
        self.selected_folder_name = None
        self._flow = None
        
        self.client_id = os.environ.get('GOOGLE_CLIENT_ID')
        self.client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
        self.project_id = os.environ.get('GOOGLE_PROJECT_ID')
        self.auth_uri = os.environ.get('GOOGLE_AUTH_URI', 'https://accounts.google.com/o/oauth2/auth')
        self.token_uri = os.environ.get('GOOGLE_TOKEN_URI', 'https://oauth2.googleapis.com/token')
        self.auth_provider_cert_url = os.environ.get('GOOGLE_AUTH_PROVIDER_CERT_URL', 'https://www.googleapis.com/oauth2/v1/certs')
        self.redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:5000/drive/callback')
        
        self._load_token()
    
    def _load_token(self):
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, 'rb') as token:
                    self.creds = pickle.load(token)
                return True
        except Exception as e:
            print(f"⚠️ Could not load token: {e}")
        return False
    
    def _save_token(self):
        try:
            with open(self.token_file, 'wb') as token:
                pickle.dump(self.creds, token)
            return True
        except Exception as e:
            print(f"⚠️ Could not save token: {e}")
        return False
    
    def get_credentials_config(self):
        return {
            "web": {
                "client_id": self.client_id,
                "project_id": self.project_id,
                "auth_uri": self.auth_uri,
                "token_uri": self.token_uri,
                "auth_provider_x509_cert_url": self.auth_provider_cert_url,
                "client_secret": self.client_secret,
                "redirect_uris": [self.redirect_uri]
            }
        }
    
    def get_auth_url(self):
        if not self.client_id or not self.client_secret:
            return {
                'status': 'error',
                'message': 'Google Drive credentials not configured. Please set environment variables.'
            }
        
        try:
            config = self.get_credentials_config()
            flow = InstalledAppFlow.from_client_config(config, SCOPES)
            flow.redirect_uri = self.redirect_uri
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            self._flow = flow
            return {
                'status': 'success',
                'auth_url': auth_url,
                'message': 'Please visit the URL to authorize the application'
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def authenticate_with_code(self, auth_code):
        try:
            if not hasattr(self, '_flow') or not self._flow:
                return {'status': 'error', 'message': 'No authentication flow initialized. Please call get_auth_url first.'}
            
            self._flow.fetch_token(code=auth_code)
            self.creds = self._flow.credentials
            self._save_token()
            self.service = build('drive', 'v3', credentials=self.creds)
            user_info = self.service.about().get(fields='user').execute()
            user_email = user_info['user']['emailAddress']
            return {
                'status': 'success',
                'message': f'Connected to {user_email}',
                'email': user_email
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def authenticate(self):
        try:
            if self.creds and self.creds.valid:
                if self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                    self._save_token()
                self.service = build('drive', 'v3', credentials=self.creds)
                user_info = self.service.about().get(fields='user').execute()
                user_email = user_info['user']['emailAddress']
                return {
                    'status': 'success',
                    'message': f'Already connected to {user_email}',
                    'email': user_email,
                    'connected': True
                }
            
            if self.creds and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                    self._save_token()
                    self.service = build('drive', 'v3', credentials=self.creds)
                    user_info = self.service.about().get(fields='user').execute()
                    user_email = user_info['user']['emailAddress']
                    return {
                        'status': 'success',
                        'message': f'Reconnected to {user_email}',
                        'email': user_email,
                        'connected': True
                    }
                except Exception as e:
                    print(f"⚠️ Refresh failed: {e}")
            
            return self.get_auth_url()
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def list_folders(self):
        if not self.service:
            return {'status': 'error', 'message': 'Not authenticated'}
        try:
            results = self.service.files().list(
                q="mimeType='application/vnd.google-apps.folder'",
                fields="files(id, name, createdTime)",
                orderBy="createdTime desc"
            ).execute()
            folders = results.get('files', [])
            return {'status': 'success', 'folders': folders}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def create_folder(self, folder_name):
        if not self.service:
            return {'status': 'error', 'message': 'Not authenticated'}
        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            file = self.service.files().create(body=file_metadata, fields='id, name').execute()
            return {
                'status': 'success',
                'folder_id': file.get('id'),
                'folder_name': file.get('name')
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def select_folder(self, folder_id, folder_name):
        self.selected_folder_id = folder_id
        self.selected_folder_name = folder_name
        return {'status': 'success', 'message': f'Selected folder: {folder_name}'}
    
    def upload_file(self, file_path, file_name, folder_id=None):
        if not self.service:
            return {'status': 'error', 'message': 'Not authenticated'}
        if not folder_id:
            folder_id = self.selected_folder_id
        if not folder_id:
            return {'status': 'error', 'message': 'No folder selected'}
        try:
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True)
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink'
            ).execute()
            return {
                'status': 'success',
                'message': f'Uploaded to Drive: {file.get("name")}',
                'file_id': file.get('id'),
                'web_link': file.get('webViewLink')
            }
        except HttpError as error:
            return {'status': 'error', 'message': f'Drive error: {error}'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def get_upload_url(self, file_id):
        if not self.service:
            return None
        try:
            file = self.service.files().get(fileId=file_id, fields='webViewLink').execute()
            return file.get('webViewLink')
        except Exception:
            return None

drive_manager = GoogleDriveManager()

# ============================================
# TIKTOK DOWNLOADER
# ============================================

class TikTokDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def download(self, url):
        try:
            response = self.session.get(
                'https://www.tikwm.com/api/',
                params={'url': url, 'hd': 1},
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 0:
                    video_data = result['data']
                    video_url = video_data.get('play', '')
                    if video_url:
                        return {
                            'video_url': video_url,
                            'title': video_data.get('title', 'TikTok Video'),
                            'author': video_data.get('author', {}).get('unique_id', 'Unknown'),
                            'duration': video_data.get('duration', 0),
                            'views': video_data.get('play_count', 0),
                            'likes': video_data.get('digg_count', 0),
                            'comments': video_data.get('comment_count', 0),
                            'thumbnail': video_data.get('cover', '')
                        }
        except Exception as e:
            print(f"❌ TikTok error: {e}")
        return None

tiktok_downloader = TikTokDownloader()

# ============================================
# YOUTUBE DOWNLOADER - FIXED WITH MULTIPLE APIS
# ============================================

def extract_youtube_id(url):
    """Extract YouTube video ID from URL"""
    patterns = [
        r'(?:youtube\.com\/watch\?v=)([\w-]+)',
        r'(?:youtu\.be\/)([\w-]+)',
        r'(?:youtube\.com\/embed\/)([\w-]+)',
        r'(?:youtube\.com\/v\/)([\w-]+)',
        r'(?:youtube\.com\/shorts\/)([\w-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def call_youtube_api(video_id):
    """Call YouTube RapidAPI to get video details"""
    
    print(f"🎯 Fetching YouTube video: {video_id}")
    
    # Method 1: YouTube138 API with POST
    try:
        conn = http.client.HTTPSConnection("youtube138.p.rapidapi.com")
        headers = {
            'x-rapidapi-key': RAPIDAPI_KEY,
            'x-rapidapi-host': "youtube138.p.rapidapi.com",
            'Content-Type': "application/json"
        }
        
        payload = json.dumps({"id": video_id, "hl": "en", "gl": "US"})
        
        print("🔄 Trying YouTube138 API (POST)...")
        conn.request("POST", "/video/details/", payload, headers)
        res = conn.getresponse()
        data = res.read().decode("utf-8")
        
        if res.status == 200:
            result = json.loads(data)
            print("✅ YouTube138 POST success!")
            
            video_url = None
            title = "YouTube Video"
            uploader = "Unknown"
            
            if 'data' in result:
                data_obj = result['data']
                if 'video' in data_obj:
                    video_url = data_obj['video']
                if 'title' in data_obj:
                    title = data_obj['title']
                if 'author' in data_obj:
                    uploader = data_obj['author']
                elif 'channelTitle' in data_obj:
                    uploader = data_obj['channelTitle']
            
            if video_url:
                return {
                    'status': 'success',
                    'video_url': video_url,
                    'title': title,
                    'uploader': uploader,
                    'api': 'youtube138_post'
                }
        else:
            print(f"❌ POST failed: {res.status}")
            
    except Exception as e:
        print(f"❌ YouTube138 POST error: {str(e)}")
    
    # Method 2: YouTube138 API with GET
    try:
        conn = http.client.HTTPSConnection("youtube138.p.rapidapi.com")
        headers = {
            'x-rapidapi-key': RAPIDAPI_KEY,
            'x-rapidapi-host': "youtube138.p.rapidapi.com",
        }
        
        endpoints = [f"/video/details/?id={video_id}", f"/video/?id={video_id}"]
        
        for endpoint in endpoints:
            try:
                print(f"🔄 Trying YouTube138 GET: {endpoint}")
                conn.request("GET", endpoint, headers=headers)
                res = conn.getresponse()
                data = res.read().decode("utf-8")
                
                if res.status == 200:
                    result = json.loads(data)
                    print("✅ YouTube138 GET success!")
                    
                    video_url = None
                    title = "YouTube Video"
                    uploader = "Unknown"
                    
                    if 'data' in result:
                        data_obj = result['data']
                        if 'video' in data_obj:
                            video_url = data_obj['video']
                        elif 'download' in data_obj:
                            video_url = data_obj['download']
                        if 'title' in data_obj:
                            title = data_obj['title']
                        if 'author' in data_obj:
                            uploader = data_obj['author']
                    
                    if video_url:
                        return {
                            'status': 'success',
                            'video_url': video_url,
                            'title': title,
                            'uploader': uploader,
                            'api': 'youtube138_get'
                        }
            except Exception as e:
                print(f"❌ Error: {str(e)}")
                
    except Exception as e:
        print(f"❌ Connection error: {str(e)}")
    
    # Method 3: YouTube Media Downloader
    try:
        conn = http.client.HTTPSConnection("youtube-media-downloader.p.rapidapi.com")
        headers = {
            'x-rapidapi-key': RAPIDAPI_KEY,
            'x-rapidapi-host': "youtube-media-downloader.p.rapidapi.com",
        }
        
        endpoints = [
            f"/v2/video/info?id={video_id}",
            f"/v2/video/download?id={video_id}",
            f"/video/info?id={video_id}",
        ]
        
        for endpoint in endpoints:
            try:
                print(f"🔄 Trying Media Downloader: {endpoint}")
                conn.request("GET", endpoint, headers=headers)
                res = conn.getresponse()
                data = res.read().decode("utf-8")
                
                if res.status == 200:
                    result = json.loads(data)
                    print("✅ Media Downloader success!")
                    
                    video_url = None
                    title = "YouTube Video"
                    uploader = "Unknown"
                    
                    if 'data' in result:
                        data_obj = result['data']
                        if 'video' in data_obj:
                            video_url = data_obj['video']
                        elif 'download' in data_obj:
                            video_url = data_obj['download']
                        if 'title' in data_obj:
                            title = data_obj['title']
                        if 'author' in data_obj:
                            uploader = data_obj['author']
                    
                    if video_url:
                        return {
                            'status': 'success',
                            'video_url': video_url,
                            'title': title,
                            'uploader': uploader,
                            'api': 'media_downloader'
                        }
            except Exception as e:
                print(f"❌ Error: {str(e)}")
                
    except Exception as e:
        print(f"❌ Connection error: {str(e)}")
    
    return {'status': 'error', 'message': 'All YouTube APIs failed'}

def download_youtube_video(url, path):
    """Download YouTube video using RapidAPI"""
    video_id = extract_youtube_id(url)
    if not video_id:
        return {'status': 'error', 'message': 'Invalid YouTube URL'}
    
    result = call_youtube_api(video_id)
    
    if result.get('status') == 'success' and result.get('video_url'):
        video_url = result['video_url']
        title = result.get('title', 'YouTube Video')
        uploader = result.get('uploader', 'Unknown')
        
        try:
            safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
            filename = f"YouTube_{uploader}_{safe_title[:50]}_{int(time.time())}.mp4"
            filepath = os.path.join(path, filename)
            
            print(f"📥 Downloading video...")
            print(f"   Title: {title}")
            print(f"   Uploader: {uploader}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.youtube.com/',
                'Accept': 'video/*',
            }
            
            response = requests.get(video_url, headers=headers, stream=True, timeout=60)
            
            if response.status_code == 200:
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                if int(progress) % 10 == 0:
                                    print(f"   Progress: {progress:.1f}%")
                
                file_size = os.path.getsize(filepath)
                print(f"✅ Downloaded: {filename} ({file_size / 1024:.1f} KB)")
                
                return {
                    'status': 'success',
                    'message': 'YouTube video downloaded!',
                    'title': title,
                    'uploader': uploader,
                    'filename': filename,
                    'filepath': filepath,
                    'size': file_size
                }
            else:
                return {'status': 'error', 'message': f'Download failed: HTTP {response.status_code}'}
                
        except Exception as e:
            return {'status': 'error', 'message': f'Download error: {str(e)}'}
    
    # Fallback to yt-dlp
    print("🔄 Fallback to yt-dlp...")
    return download_youtube_fallback(url, path)

def download_youtube_fallback(url, path):
    """Fallback to yt-dlp for YouTube"""
    try:
        ydl_opts = {
            'outtmpl': os.path.join(path, '%(uploader)s - %(title)s.%(ext)s'),
            'format': 'best[ext=mp4]/best',
            'quiet': True,
            'ignoreerrors': True,
            'retries': 5,
            'timeout': 60,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = f"{info.get('uploader', 'Unknown')} - {info.get('title', 'video')}.mp4"
            filepath = os.path.join(path, filename)
            return {
                'status': 'success',
                'message': 'YouTube video downloaded! (fallback)',
                'title': info.get('title', 'Unknown'),
                'uploader': info.get('uploader', 'Unknown'),
                'duration': info.get('duration', 0),
                'views': info.get('view_count', 0),
                'filename': filename,
                'filepath': filepath,
                'size': os.path.getsize(filepath) if os.path.exists(filepath) else 0
            }
    except Exception as e:
        return {'status': 'error', 'message': f'YouTube error: {str(e)}'}

def get_youtube_info(url):
    """Get YouTube video info"""
    video_id = extract_youtube_id(url)
    if not video_id:
        return {'status': 'error', 'message': 'Invalid YouTube URL'}
    
    result = call_youtube_api(video_id)
    if result.get('status') == 'success':
        return {
            'status': 'success',
            'title': result.get('title', 'YouTube Video'),
            'uploader': result.get('uploader', 'Unknown'),
            'platform': 'youtube',
            'url': url,
            'video_url': result.get('video_url')
        }
    
    return {'status': 'error', 'message': 'Could not get YouTube info'}

# ============================================
# INSTAGRAM DOWNLOADER
# ============================================

class InstagramDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
    
    def download(self, url):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(TEMP_DIR, 'instagram_%(id)s.%(ext)s'),
                'format': 'best[ext=mp4]/best',
                'quiet': True,
                'ignoreerrors': True,
                'retries': 5,
                'timeout': 60,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    filename = ydl.prepare_filename(info)
                    if os.path.exists(filename):
                        return {
                            'status': 'success',
                            'message': 'Instagram video downloaded!',
                            'title': info.get('title', 'Instagram Video'),
                            'uploader': info.get('uploader', 'Unknown'),
                            'filename': os.path.basename(filename),
                            'filepath': filename,
                            'size': os.path.getsize(filename)
                        }
        except Exception as e:
            print(f"⚠️ Instagram error: {e}")
        
        return {'status': 'error', 'message': 'Could not download Instagram video. Instagram has strict rate limiting. Please try again in a few minutes.'}
    
    def get_preview(self, url):
        try:
            shortcode = re.search(r'/p/([^/?]+)', url) or re.search(r'/reel/([^/?]+)', url)
            if not shortcode:
                return {'status': 'error', 'message': 'Invalid Instagram URL'}
            
            loader = instaloader.Instaloader()
            post = instaloader.Post.from_shortcode(loader.context, shortcode.group(1))
            
            return {
                'status': 'success',
                'title': post.caption[:100] if post.caption else 'Instagram Post',
                'uploader': post.owner_username,
                'duration': post.video_duration if post.is_video else 0,
                'thumbnail': post.url,
                'views': post.video_view_count if post.is_video else 0,
                'likes': post.likes,
                'comments': post.comments,
                'platform': 'instagram',
                'url': url
            }
        except Exception as e:
            return {'status': 'error', 'message': f'Could not get Instagram preview: {str(e)}'}

instagram_downloader = InstagramDownloader()

# ============================================
# VIDEO EXTRACTOR
# ============================================

class VideoExtractor:
    @staticmethod
    def extract_metadata(filepath):
        try:
            ydl_opts = {'quiet': True, 'no_warnings': True, 'timeout': 30}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(filepath, download=False)
                return {
                    'title': info.get('title', 'Unknown'),
                    'uploader': info.get('uploader', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'view_count': info.get('view_count', 0),
                    'like_count': info.get('like_count', 0),
                    'comment_count': info.get('comment_count', 0),
                    'upload_date': info.get('upload_date', ''),
                    'description': info.get('description', '')[:500]
                }
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def extract_audio(filepath, output_dir=TEMP_DIR):
        try:
            filename = os.path.basename(filepath)
            name_without_ext = os.path.splitext(filename)[0]
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(output_dir, name_without_ext),
                'quiet': True,
                'no_warnings': True,
                'timeout': 60,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([filepath])
            
            for f in os.listdir(output_dir):
                if f.startswith(name_without_ext) and f.endswith('.mp3'):
                    return {'status': 'success', 'audio_path': os.path.join(output_dir, f)}
            return {'status': 'error', 'message': 'Audio extraction failed'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    @staticmethod
    def extract_thumbnail(filepath, output_dir=TEMP_DIR):
        try:
            filename = os.path.basename(filepath)
            name_without_ext = os.path.splitext(filename)[0]
            thumb_path = os.path.join(output_dir, f"{name_without_ext}_thumb.jpg")
            
            ydl_opts = {'quiet': True, 'no_warnings': True, 'timeout': 30}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(filepath, download=False)
                if info.get('thumbnail'):
                    response = requests.get(info['thumbnail'], stream=True, timeout=30)
                    if response.status_code == 200:
                        with open(thumb_path, 'wb') as f:
                            for chunk in response.iter_content(8192):
                                f.write(chunk)
                        return {'status': 'success', 'thumbnail_path': thumb_path}
            return {'status': 'error', 'message': 'Could not extract thumbnail'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    @staticmethod
    def extract_subtitles(filepath, output_dir=TEMP_DIR):
        try:
            filename = os.path.basename(filepath)
            name_without_ext = os.path.splitext(filename)[0]
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'timeout': 60,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['en'],
                'subtitlesformat': 'vtt',
                'outtmpl': os.path.join(output_dir, name_without_ext),
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([filepath])
            
            for f in os.listdir(output_dir):
                if f.startswith(name_without_ext) and f.endswith('.vtt'):
                    return {'status': 'success', 'subtitle_path': os.path.join(output_dir, f)}
            return {'status': 'error', 'message': 'No subtitles found'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    @staticmethod
    def extract_all(filepath, output_dir=TEMP_DIR):
        return {
            'metadata': VideoExtractor.extract_metadata(filepath),
            'audio': VideoExtractor.extract_audio(filepath, output_dir),
            'thumbnail': VideoExtractor.extract_thumbnail(filepath, output_dir),
            'subtitles': VideoExtractor.extract_subtitles(filepath, output_dir),
        }

extractor = VideoExtractor()

# ============================================
# GALLERY SAVER
# ============================================

class GallerySaver:
    @staticmethod
    def save_to_gallery(file_path, filename):
        try:
            system = os.name
            if system == 'nt':
                videos_folder = os.path.join(os.environ['USERPROFILE'], 'Videos')
                downloads_folder = os.path.join(os.environ['USERPROFILE'], 'Downloads')
                destination = os.path.join(videos_folder, filename)
                shutil.copy2(file_path, destination)
                shutil.copy2(file_path, os.path.join(downloads_folder, filename))
                return {'status': 'success', 'message': 'Saved to Videos and Downloads', 'path': destination}
            elif system == 'posix':
                videos_folder = os.path.expanduser('~/Videos') or os.path.expanduser('~/Downloads')
                destination = os.path.join(videos_folder, filename)
                shutil.copy2(file_path, destination)
                return {'status': 'success', 'message': 'Saved to Videos folder', 'path': destination}
            return {'status': 'info', 'message': 'File saved in downloads', 'path': file_path}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

# ============================================
# VIDEO PREVIEW
# ============================================

class VideoPreview:
    def get_video_info(self, url):
        platform = self.detect_platform(url)
        try:
            if platform == 'tiktok':
                return self.get_tiktok_info(url)
            elif platform == 'instagram':
                return instagram_downloader.get_preview(url)
            elif platform == 'youtube':
                return get_youtube_info(url)
            else:
                return self.get_generic_info(url)
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def get_tiktok_info(self, url):
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
                        'platform': 'tiktok',
                        'url': url,
                        'video_url': video_data.get('play', '')
                    }
            return {'status': 'error', 'message': 'Failed to get TikTok info'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def get_generic_info(self, url):
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'format': 'best',
                'ignoreerrors': True,
                'timeout': 30,
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
                        'platform': self.detect_platform(url),
                        'url': url
                    }
            return {'status': 'error', 'message': 'Could not get video info'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def detect_platform(self, url):
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
            return 'generic'

preview = VideoPreview()

# ============================================
# UNIVERSAL DOWNLOADER
# ============================================

class UniversalDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def detect_platform(self, url):
        url = url.lower()
        if 'tiktok.com' in url:
            return 'tiktok'
        elif 'youtube.com' in url or 'youtu.be' in url:
            return 'youtube'
        elif 'instagram.com' in url:
            return 'instagram'
        elif 'twitter.com' in url or 'x.com' in url:
            return 'twitter'
        elif 'facebook.com' in url or 'fb.watch' in url:
            return 'facebook'
        elif 'reddit.com' in url:
            return 'reddit'
        elif 'vimeo.com' in url:
            return 'vimeo'
        elif 'dailymotion.com' in url:
            return 'dailymotion'
        elif 'twitch.tv' in url:
            return 'twitch'
        else:
            return 'generic'
    
    def download_content(self, url, path):
        platform = self.detect_platform(url)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        download_folder = os.path.join(path, f"{platform}_{timestamp}")
        os.makedirs(download_folder, exist_ok=True)
        
        if platform == 'tiktok':
            return self.download_tiktok(url, download_folder)
        elif platform == 'instagram':
            return self.download_instagram(url, download_folder)
        elif platform == 'youtube':
            return download_youtube_video(url, download_folder)
        elif platform == 'twitter':
            return self.download_twitter(url, download_folder)
        elif platform == 'facebook':
            return self.download_facebook(url, download_folder)
        elif platform == 'reddit':
            return self.download_reddit(url, download_folder)
        elif platform == 'vimeo':
            return self.download_vimeo(url, download_folder)
        elif platform == 'dailymotion':
            return self.download_dailymotion(url, download_folder)
        elif platform == 'twitch':
            return self.download_twitch(url, download_folder)
        else:
            return self.download_generic(url, download_folder)
    
    def download_tiktok(self, url, path):
        result = tiktok_downloader.download(url)
        if result and result.get('video_url'):
            return self._download_video(
                result['video_url'],
                path,
                f"TikTok_{result.get('author', 'Unknown')}_{result.get('title', 'video')}",
                result
            )
        return {'status': 'error', 'message': 'Failed to download TikTok video'}
    
    def download_instagram(self, url, path):
        result = instagram_downloader.download(url)
        if result.get('status') == 'success' and 'filepath' in result:
            if os.path.exists(result['filepath']):
                filename = result.get('filename', os.path.basename(result['filepath']))
                new_path = os.path.join(path, filename)
                shutil.move(result['filepath'], new_path)
                result['filepath'] = new_path
                result['size'] = os.path.getsize(new_path)
                result['filename'] = filename
        return result
    
    def _download_video(self, video_url, path, base_name, metadata=None):
        try:
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', base_name)
            filename = f"{safe_name[:50]}_{int(time.time())}.mp4"
            filepath = os.path.join(path, filename)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.tiktok.com/',
                'Accept': 'video/*',
            }
            
            response = requests.get(video_url, headers=headers, stream=True, timeout=60)
            if response.status_code == 200:
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0 and int(downloaded / total_size * 100) % 10 == 0:
                                print(f"   Progress: {(downloaded/total_size)*100:.1f}%")
                
                file_size = os.path.getsize(filepath)
                return {
                    'status': 'success',
                    'message': 'Video downloaded successfully! 🎉',
                    'filename': filename,
                    'filepath': filepath,
                    'size': file_size,
                    'metadata': metadata or {}
                }
            return {'status': 'error', 'message': f'Download failed: HTTP {response.status_code}'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def download_twitter(self, url, path):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Twitter_%(uploader)s_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'ignoreerrors': True,
                'retries': 5,
                'timeout': 60,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = f"Twitter_{info.get('uploader', 'Unknown')}_{info.get('title', 'tweet')}.mp4"
                filepath = os.path.join(path, filename)
                return {
                    'status': 'success',
                    'message': 'Twitter content downloaded!',
                    'title': info.get('title', 'Tweet'),
                    'uploader': info.get('uploader', 'Unknown'),
                    'likes': info.get('like_count', 0),
                    'retweets': info.get('retweet_count', 0),
                    'filename': filename,
                    'filepath': filepath
                }
        except Exception as e:
            return {'status': 'error', 'message': f'Twitter error: {str(e)}'}
    
    def download_facebook(self, url, path):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Facebook_%(title)s.%(ext)s'),
                'format': 'best[ext=mp4]/best',
                'quiet': True,
                'ignoreerrors': True,
                'retries': 5,
                'timeout': 60,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = f"Facebook_{info.get('title', 'video')}.mp4"
                filepath = os.path.join(path, filename)
                return {
                    'status': 'success',
                    'message': 'Facebook video downloaded!',
                    'title': info.get('title', 'Facebook Video'),
                    'duration': info.get('duration', 0),
                    'filename': filename,
                    'filepath': filepath
                }
        except Exception as e:
            return {'status': 'error', 'message': f'Facebook error: {str(e)}'}
    
    def download_reddit(self, url, path):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Reddit_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'ignoreerrors': True,
                'retries': 5,
                'timeout': 60,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = f"Reddit_{info.get('title', 'post')}.mp4"
                filepath = os.path.join(path, filename)
                return {
                    'status': 'success',
                    'message': 'Reddit content downloaded!',
                    'title': info.get('title', 'Reddit Post'),
                    'ups': info.get('like_count', 0),
                    'comments': info.get('comment_count', 0),
                    'filename': filename,
                    'filepath': filepath
                }
        except Exception as e:
            return {'status': 'error', 'message': f'Reddit error: {str(e)}'}
    
    def download_vimeo(self, url, path):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Vimeo_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'ignoreerrors': True,
                'retries': 5,
                'timeout': 60,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = f"Vimeo_{info.get('title', 'video')}.mp4"
                filepath = os.path.join(path, filename)
                return {
                    'status': 'success',
                    'message': 'Vimeo video downloaded!',
                    'title': info.get('title', 'Vimeo Video'),
                    'duration': info.get('duration', 0),
                    'filename': filename,
                    'filepath': filepath
                }
        except Exception as e:
            return {'status': 'error', 'message': f'Vimeo error: {str(e)}'}
    
    def download_dailymotion(self, url, path):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Dailymotion_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'ignoreerrors': True,
                'retries': 5,
                'timeout': 60,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = f"Dailymotion_{info.get('title', 'video')}.mp4"
                filepath = os.path.join(path, filename)
                return {
                    'status': 'success',
                    'message': 'Dailymotion video downloaded!',
                    'title': info.get('title', 'Dailymotion Video'),
                    'duration': info.get('duration', 0),
                    'filename': filename,
                    'filepath': filepath
                }
        except Exception as e:
            return {'status': 'error', 'message': f'Dailymotion error: {str(e)}'}
    
    def download_twitch(self, url, path):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Twitch_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'ignoreerrors': True,
                'retries': 5,
                'timeout': 60,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = f"Twitch_{info.get('title', 'video')}.mp4"
                filepath = os.path.join(path, filename)
                return {
                    'status': 'success',
                    'message': 'Twitch content downloaded!',
                    'title': info.get('title', 'Twitch Video'),
                    'uploader': info.get('uploader', 'Unknown'),
                    'filename': filename,
                    'filepath': filepath
                }
        except Exception as e:
            return {'status': 'error', 'message': f'Twitch error: {str(e)}'}
    
    def download_generic(self, url, path):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, '%(extractor)s_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'ignoreerrors': True,
                'retries': 5,
                'timeout': 60,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = f"{info.get('extractor', 'generic')}_{info.get('title', 'video')}.mp4"
                filepath = os.path.join(path, filename)
                return {
                    'status': 'success',
                    'message': 'Content downloaded!',
                    'title': info.get('title', 'Unknown'),
                    'extractor': info.get('extractor', 'Unknown'),
                    'filename': filename,
                    'filepath': filepath
                }
        except Exception as e:
            return {'status': 'error', 'message': f'Download error: {str(e)}'}

downloader = UniversalDownloader()

# ============================================
# FLASK ROUTES
# ============================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/preview', methods=['POST'])
def preview_video():
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        if not url:
            return jsonify({'status': 'error', 'message': 'URL is required'})
        result = preview.get_video_info(url)
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/download', methods=['POST'])
def download():
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        save_to = data.get('save_to', 'local')
        extract = data.get('extract', False)
        
        if not url:
            return jsonify({'status': 'error', 'message': 'URL is required'})
        
        platform = downloader.detect_platform(url)
        result = downloader.download_content(url, DOWNLOAD_DIR)
        
        if result['status'] == 'success':
            if 'filepath' in result:
                filepath = result['filepath']
                filename = result.get('filename', os.path.basename(filepath))
                result['filename'] = filename
                
                if save_to == 'gallery':
                    gallery_result = GallerySaver.save_to_gallery(filepath, filename)
                    result['gallery'] = gallery_result
                
                if save_to == 'drive':
                    drive_result = drive_manager.upload_file(filepath, filename)
                    result['drive'] = drive_result
                
                if extract:
                    extraction_result = extractor.extract_all(filepath, EXTRACT_DIR)
                    result['extraction'] = extraction_result
        
        result['platform'] = platform
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/bulk-download', methods=['POST'])
def bulk_download():
    try:
        data = request.get_json()
        urls = data.get('urls', [])
        save_to = data.get('save_to', 'local')
        
        if not urls:
            return jsonify({'status': 'error', 'message': 'URLs list is required'})
        
        results = []
        for url in urls:
            if url.strip():
                result = downloader.download_content(url.strip(), DOWNLOAD_DIR)
                result['url'] = url
                
                if result['status'] == 'success' and 'filepath' in result:
                    filepath = result['filepath']
                    filename = result.get('filename', os.path.basename(filepath))
                    result['filename'] = filename
                    
                    if save_to == 'gallery':
                        gallery_result = GallerySaver.save_to_gallery(filepath, filename)
                        result['gallery'] = gallery_result
                    
                    if save_to == 'drive':
                        drive_result = drive_manager.upload_file(filepath, filename)
                        result['drive'] = drive_result
                
                results.append(result)
                time.sleep(2)
        
        return jsonify({
            'status': 'success',
            'message': f'Processed {len(results)} URLs',
            'results': results
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# ============================================
# EXTRACTION ROUTES
# ============================================

@app.route('/extract', methods=['POST'])
def extract_video():
    try:
        data = request.get_json()
        filename = data.get('filename')
        extract_type = data.get('extract_type', 'all')
        
        if not filename:
            return jsonify({'status': 'error', 'message': 'Filename required'})
        
        file_path = None
        for root, dirs, files in os.walk(DOWNLOAD_DIR):
            if filename in files:
                file_path = os.path.join(root, filename)
                break
        
        if not file_path:
            return jsonify({'status': 'error', 'message': 'File not found'})
        
        if extract_type == 'all':
            result = extractor.extract_all(file_path, EXTRACT_DIR)
        elif extract_type == 'audio':
            result = extractor.extract_audio(file_path, EXTRACT_DIR)
        elif extract_type == 'thumbnail':
            result = extractor.extract_thumbnail(file_path, EXTRACT_DIR)
        elif extract_type == 'subtitles':
            result = extractor.extract_subtitles(file_path, EXTRACT_DIR)
        elif extract_type == 'metadata':
            result = extractor.extract_metadata(file_path)
        else:
            return jsonify({'status': 'error', 'message': 'Invalid extract_type'})
        
        return jsonify({
            'status': 'success',
            'message': 'Extraction completed',
            'result': result
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/extract/<extract_type>/<filename>')
def download_extraction(extract_type, filename):
    try:
        safe_filename = secure_filename(filename)
        ext_map = {'audio': 'mp3', 'thumbnail': 'jpg', 'subtitles': 'vtt'}
        
        if extract_type not in ext_map:
            return jsonify({'error': 'Invalid extract type'}), 400
        
        ext = ext_map[extract_type]
        name_without_ext = os.path.splitext(safe_filename)[0]
        
        for f in os.listdir(EXTRACT_DIR):
            if f.startswith(name_without_ext) and f.endswith(f'.{ext}'):
                file_path = os.path.join(EXTRACT_DIR, f)
                return send_file(file_path, as_attachment=True)
        
        return jsonify({'error': 'Extracted file not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# GOOGLE DRIVE ROUTES
# ============================================

@app.route('/drive/auth', methods=['GET', 'POST'])
def drive_auth():
    if request.method == 'POST':
        data = request.get_json()
        auth_code = data.get('code') if data else None
        if auth_code:
            result = drive_manager.authenticate_with_code(auth_code)
            return jsonify(result)
        result = drive_manager.authenticate()
        return jsonify(result)
    
    result = drive_manager.get_auth_url()
    return jsonify(result)

@app.route('/drive/auth/url', methods=['GET'])
def drive_auth_url():
    result = drive_manager.get_auth_url()
    return jsonify(result)

@app.route('/drive/callback', methods=['GET'])
def drive_callback():
    code = request.args.get('code')
    if not code:
        return jsonify({'status': 'error', 'message': 'No authorization code provided'})
    
    result = drive_manager.authenticate_with_code(code)
    if result['status'] == 'success':
        return '''
        <html>
            <head><title>Authentication Successful</title>
            <style>
                body { font-family: Arial; text-align: center; padding: 50px; background: #0a1f0a; color: white; }
                .success { color: #4CAF50; font-size: 24px; }
                .container { max-width: 500px; margin: 0 auto; background: #1a3a1a; padding: 40px; border-radius: 10px; }
                .btn { display: inline-block; padding: 12px 24px; background: #4CAF50; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }
            </style>
            </head>
            <body>
                <div class="container">
                    <div class="success">✅ Authentication Successful!</div>
                    <p>You can now close this window and return to the app.</p>
                    <a href="/" class="btn">Return to App</a>
                </div>
            </body>
        </html>
        '''
    else:
        return f'<html><body><h1>❌ Authentication Failed</h1><p>{result.get("message")}</p></body></html>'

@app.route('/drive/status', methods=['GET'])
def drive_status():
    try:
        if drive_manager.service:
            user_info = drive_manager.service.about().get(fields='user').execute()
            return jsonify({
                'status': 'success',
                'connected': True,
                'email': user_info['user']['emailAddress']
            })
        else:
            return jsonify({
                'status': 'success',
                'connected': False,
                'message': 'Not connected to Google Drive'
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'connected': False,
            'message': str(e)
        })

@app.route('/drive/folders', methods=['GET'])
def drive_list_folders():
    result = drive_manager.list_folders()
    return jsonify(result)

@app.route('/drive/folder/select', methods=['POST'])
def drive_select_folder():
    try:
        data = request.get_json()
        folder_id = data.get('folder_id')
        folder_name = data.get('folder_name')
        if not folder_id:
            return jsonify({'status': 'error', 'message': 'Folder ID required'})
        result = drive_manager.select_folder(folder_id, folder_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/drive/folder/create', methods=['POST'])
def drive_create_folder():
    try:
        data = request.get_json()
        folder_name = data.get('folder_name')
        if not folder_name:
            return jsonify({'status': 'error', 'message': 'Folder name required'})
        result = drive_manager.create_folder(folder_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/drive/upload', methods=['POST'])
def drive_upload_file():
    try:
        data = request.get_json()
        filename = data.get('filename')
        folder_id = data.get('folder_id')
        if not filename:
            return jsonify({'status': 'error', 'message': 'Filename required'})
        
        file_path = None
        for root, dirs, files in os.walk(DOWNLOAD_DIR):
            if filename in files:
                file_path = os.path.join(root, filename)
                break
        
        if not file_path:
            return jsonify({'status': 'error', 'message': 'File not found'})
        
        result = drive_manager.upload_file(file_path, filename, folder_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# ============================================
# GALLERY SAVE ROUTE
# ============================================

@app.route('/save-gallery', methods=['POST'])
def save_to_gallery():
    try:
        data = request.get_json()
        filename = data.get('filename')
        if not filename:
            return jsonify({'status': 'error', 'message': 'Filename required'})
        
        file_path = None
        for root, dirs, files in os.walk(DOWNLOAD_DIR):
            if filename in files:
                file_path = os.path.join(root, filename)
                break
        
        if not file_path:
            return jsonify({'status': 'error', 'message': 'File not found'})
        
        result = GallerySaver.save_to_gallery(file_path, filename)
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# ============================================
# DOWNLOADS MANAGEMENT
# ============================================

@app.route('/downloads')
def list_downloads():
    try:
        items = []
        if os.path.exists(DOWNLOAD_DIR):
            for item in os.listdir(DOWNLOAD_DIR):
                item_path = os.path.join(DOWNLOAD_DIR, item)
                if os.path.isfile(item_path):
                    size = os.path.getsize(item_path)
                    items.append({
                        'name': item,
                        'type': 'file',
                        'size': size,
                        'size_str': f"{size / 1024:.1f} KB" if size < 1024*1024 else f"{size / (1024*1024):.1f} MB",
                        'modified': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M:%S')
                    })
                elif os.path.isdir(item_path):
                    files = [f for f in os.listdir(item_path) if os.path.isfile(os.path.join(item_path, f))]
                    total_size = sum(os.path.getsize(os.path.join(item_path, f)) for f in files)
                    items.append({
                        'name': item,
                        'type': 'folder',
                        'file_count': len(files),
                        'size': total_size,
                        'size_str': f"{total_size / 1024:.1f} KB" if total_size < 1024*1024 else f"{total_size / (1024*1024):.1f} MB",
                        'modified': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M:%S')
                    })
        
        items.sort(key=lambda x: x.get('modified', ''), reverse=True)
        return jsonify({'items': items})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/download-file/<path:filename>')
def download_file(filename):
    try:
        safe_filename = secure_filename(filename)
        file_path = os.path.join(DOWNLOAD_DIR, safe_filename)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return send_file(file_path, as_attachment=True)
        return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download-folder/<foldername>')
def download_folder(foldername):
    try:
        safe_foldername = secure_filename(foldername)
        folder_path = os.path.join(DOWNLOAD_DIR, safe_foldername)
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
            temp_zip.close()
            with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, folder_path)
                        zipf.write(file_path, arcname)
            return send_file(temp_zip.name, as_attachment=True, download_name=f'{safe_foldername}.zip')
        return jsonify({'error': 'Folder not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/clear-downloads', methods=['POST'])
def clear_downloads():
    try:
        if os.path.exists(DOWNLOAD_DIR):
            shutil.rmtree(DOWNLOAD_DIR)
            os.makedirs(DOWNLOAD_DIR)
        return jsonify({'status': 'success', 'message': 'Downloads cleared'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# ============================================
# PLATFORMS & INFO
# ============================================

@app.route('/supported-platforms')
def supported_platforms():
    platforms = {
        'video_platforms': [
            'TikTok (via TikWM API)',
            'YouTube (via RapidAPI + Fallback)',
            'Instagram (via yt-dlp)',
            'Twitter/X',
            'Facebook',
            'Reddit',
            'Twitch',
            'Vimeo',
            'Dailymotion'
        ],
        'features': [
            'Auto-platform detection',
            'Bulk downloads',
            'Video preview',
            'Gallery save',
            'Google Drive integration',
            'Audio extraction (MP3)',
            'Thumbnail extraction',
            'Subtitle extraction',
            'Metadata extraction'
        ]
    }
    return jsonify(platforms)

@app.route('/api-docs')
def api_docs():
    docs = {
        'name': 'Universal Social Media Downloader API',
        'version': '2.0.0',
        'base_url': '/api',
        'endpoints': [
            {'path': '/api/download', 'method': 'POST', 'description': 'Download a video'},
            {'path': '/api/preview', 'method': 'POST', 'description': 'Get video preview info'},
            {'path': '/api/bulk', 'method': 'POST', 'description': 'Download multiple videos'},
            {'path': '/api/extract', 'method': 'POST', 'description': 'Extract audio, thumbnail, subtitles'},
            {'path': '/api/drive/auth', 'method': 'POST', 'description': 'Google Drive authentication'},
            {'path': '/api/drive/folders', 'method': 'GET', 'description': 'List Google Drive folders'},
            {'path': '/api/drive/upload', 'method': 'POST', 'description': 'Upload to Google Drive'},
            {'path': '/api/platforms', 'method': 'GET', 'description': 'List supported platforms'}
        ]
    }
    return jsonify(docs)

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print("🌿 SOCIAL MEDIA DOWNLOADER v2.0")
    print("=" * 60)
    print("📱 Supported Platforms:")
    print("  • TikTok 🎵 (Working)")
    print("  • YouTube ▶️ (Working)")
    print("  • Instagram 📸 (Working)")
    print("  • Twitter/X 🐦 (Working)")
    print("  • Facebook 📘 (Working)")
    print("  • Reddit 🔴 (Working)")
    print("  • Vimeo 🎬 (Working)")
    print("  • Dailymotion 🎥 (Working)")
    print("  • Twitch 📺 (Working)")
    print("=" * 60)
    print("💾 Save Options: Local | Gallery | Google Drive")
    print("=" * 60)
    print("📁 Downloads folder:", DOWNLOAD_DIR)
    print("📁 Extractions folder:", EXTRACT_DIR)
    print("🌐 Server running on: http://localhost:" + str(port))
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=True)
