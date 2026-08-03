from flask import Flask, request, render_template, jsonify, send_file, session
import os
import tempfile
import threading
import requests
import json
import re
from datetime import datetime
import yt_dlp
import instaloader
from werkzeug.utils import secure_filename
import zipfile
import shutil
import time
import random
import http.client
import subprocess

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
        self.auth_uri = os.environ.get('GOOGLE_AUTH_URI')
        self.token_uri = os.environ.get('GOOGLE_TOKEN_URI')
        self.auth_provider_cert_url = os.environ.get('GOOGLE_AUTH_PROVIDER_CERT_URL')
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
                'message': 'Google Drive credentials not configured.'
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
                'message': 'Please visit the URL to authorize'
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def authenticate_with_code(self, auth_code):
        try:
            if not hasattr(self, '_flow') or not self._flow:
                return {'status': 'error', 'message': 'No authentication flow initialized.'}
            
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
# TIKTOK DOWNLOADER - MULTI METHOD
# ============================================

class TikTokDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def download(self, url):
        methods = [
            self._download_tikwm,
            self._download_ytdlp,
            self._download_rapidapi,
        ]
        
        for method in methods:
            try:
                print(f"🔄 Trying {method.__name__}...")
                result = method(url)
                if result and result.get('video_url'):
                    print(f"✅ {method.__name__} success!")
                    return result
            except Exception as e:
                print(f"❌ {method.__name__} error: {str(e)}")
                continue
        
        return None
    
    def _download_tikwm(self, url):
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
            print(f"TikWM error: {e}")
        return None
    
    def _download_ytdlp(self, url):
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'format': 'best',
                'extract_flat': False,
                'ignoreerrors': True,
                'retries': 10,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                }
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info and info.get('url'):
                    return {
                        'video_url': info['url'],
                        'title': info.get('title', 'TikTok Video'),
                        'author': info.get('uploader', 'Unknown'),
                        'duration': info.get('duration', 0),
                        'views': info.get('view_count', 0),
                        'likes': info.get('like_count', 0),
                    }
        except Exception as e:
            print(f"yt-dlp error: {e}")
        return None
    
    def _download_rapidapi(self, url):
        try:
            conn = http.client.HTTPSConnection("tiktok-downloader-download-videos-no-watermark1.p.rapidapi.com")
            headers = {
                'x-rapidapi-key': RAPIDAPI_KEY,
                'x-rapidapi-host': "tiktok-downloader-download-videos-no-watermark1.p.rapidapi.com",
            }
            conn.request("GET", f"/video?url={url}", headers=headers)
            res = conn.getresponse()
            data = res.read().decode("utf-8")
            
            if res.status == 200:
                result = json.loads(data)
                if 'data' in result and 'video' in result['data']:
                    return {
                        'video_url': result['data']['video'],
                        'title': result['data'].get('title', 'TikTok Video'),
                        'author': result['data'].get('author', {}).get('unique_id', 'Unknown'),
                    }
        except Exception as e:
            print(f"RapidAPI error: {e}")
        return None

tiktok_downloader = TikTokDownloader()

# ============================================
# YOUTUBE DOWNLOADER
# ============================================

def download_youtube_content(url, path):
    """Download YouTube videos, shorts, playlists"""
    try:
        ydl_opts = {
            'outtmpl': os.path.join(path, '%(uploader)s - %(title)s.%(ext)s'),
            'format': 'best[ext=mp4]/best',
            'quiet': True,
            'ignoreerrors': True,
            'retries': 10,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en'],
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            if 'entries' in info:
                titles = [entry.get('title', 'Unknown') for entry in info['entries'] if entry]
                return {
                    'status': 'success',
                    'message': f'Downloaded {len(titles)} videos from playlist',
                    'titles': titles[:5],
                    'type': 'playlist',
                    'count': len(titles)
                }
            else:
                filename = f"{info.get('uploader', 'Unknown')} - {info.get('title', 'video')}.mp4"
                filepath = os.path.join(path, filename)
                return {
                    'status': 'success',
                    'message': 'YouTube content downloaded successfully!',
                    'title': info.get('title', 'Unknown'),
                    'uploader': info.get('uploader', 'Unknown'),
                    'type': 'video',
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
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'format': 'best',
            'ignoreerrors': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
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
                    'platform': 'youtube',
                    'url': url
                }
        return {'status': 'error', 'message': 'Could not get YouTube info'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

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
    
    def download(self, url, path):
        try:
            loader = instaloader.Instaloader(
                dirname_pattern=path,
                filename_pattern='{profile}_{mediaid}_{date_utc}',
                download_videos=True,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=True,
                compress_json=False,
                post_metadata_txt_pattern=None,
            )
            
            if '/stories/' in url:
                username = self.extract_instagram_username(url)
                if username:
                    profile = instaloader.Profile.from_username(loader.context, username)
                    for story in loader.get_stories([profile.userid]):
                        for item in story.get_items():
                            loader.download_storyitem(item, target=username)
                    return {
                        'status': 'success',
                        'message': f'Instagram stories downloaded for {username}',
                        'type': 'stories'
                    }
            elif '/reel/' in url or '/p/' in url or '/tv/' in url:
                shortcode = self.extract_instagram_shortcode(url)
                post = instaloader.Post.from_shortcode(loader.context, shortcode)
                loader.download_post(post, target=post.owner_username)
                
                content_type = 'reel' if post.is_video else 'post'
                if post.typename == 'GraphSidecar':
                    content_type = 'carousel'
                
                return {
                    'status': 'success',
                    'message': f'Instagram {content_type} downloaded successfully!',
                    'username': post.owner_username,
                    'caption': post.caption[:100] + '...' if post.caption and len(post.caption) > 100 else post.caption,
                    'type': content_type,
                    'likes': post.likes,
                    'comments': post.comments
                }
            else:
                username = self.extract_instagram_username(url)
                profile = instaloader.Profile.from_username(loader.context, username)
                
                count = 0
                for post in profile.get_posts():
                    if count >= 10:
                        break
                    loader.download_post(post, target=username)
                    count += 1
                
                return {
                    'status': 'success',
                    'message': f'Downloaded {count} recent posts from {username}',
                    'type': 'profile',
                    'count': count
                }
                
        except Exception as e:
            return {'status': 'error', 'message': f'Instagram error: {str(e)}'}
    
    def get_preview(self, url):
        try:
            shortcode = self.extract_instagram_shortcode(url)
            if not shortcode:
                return {'status': 'error', 'message': 'Invalid Instagram URL'}
            
            loader = instaloader.Instaloader()
            post = instaloader.Post.from_shortcode(loader.context, shortcode)
            
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
            return {'status': 'error', 'message': str(e)}
    
    def extract_instagram_shortcode(self, url):
        patterns = [
            r'/p/([^/?]+)',
            r'/reel/([^/?]+)',
            r'/tv/([^/?]+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def extract_instagram_username(self, url):
        match = re.search(r'instagram\.com/([^/?]+)', url)
        if match:
            return match.group(1)
        return None

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
            result = tiktok_downloader.download(url)
            if result:
                return {
                    'status': 'success',
                    'title': result.get('title', 'TikTok Video'),
                    'uploader': result.get('author', 'Unknown'),
                    'duration': result.get('duration', 0),
                    'thumbnail': result.get('thumbnail', ''),
                    'views': result.get('views', 0),
                    'likes': result.get('likes', 0),
                    'comments': result.get('comments', 0),
                    'platform': 'tiktok',
                    'url': url,
                    'video_url': result.get('video_url')
                }
            return {'status': 'error', 'message': 'Could not fetch TikTok video'}
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
        elif 'vimeo.com' in url:
            return 'vimeo'
        elif 'dailymotion.com' in url:
            return 'dailymotion'
        elif 'twitch.tv' in url:
            return 'twitch'
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
            return 'unknown'
    
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
            return download_youtube_content(url, download_folder)
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
        return instagram_downloader.download(url, path)
    
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
            'TikTok (Multi-API)',
            'YouTube (Videos, Shorts, Playlists)',
            'Instagram (Posts, Reels, Stories, IGTV)',
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
            'Metadata extraction',
            'Playlist support',
            'Stories download'
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
# MCP SERVER ROUTES
# ============================================

@app.route('/mcp', methods=['POST'])
def mcp_endpoint():
    """MCP endpoint for AI model integration"""
    try:
        data = request.get_json()
        method = data.get('method')
        params = data.get('params', {})
        req_id = data.get('id')
        
        if method == 'tools/list':
            tools = [
                {
                    'name': 'download_video',
                    'description': 'Download a video from social media',
                    'parameters': {
                        'url': {'type': 'string', 'description': 'Video URL'},
                        'save_to': {'type': 'string', 'description': 'local, gallery, drive'}
                    }
                },
                {
                    'name': 'preview_video',
                    'description': 'Get video preview info',
                    'parameters': {
                        'url': {'type': 'string', 'description': 'Video URL'}
                    }
                },
                {
                    'name': 'get_supported_platforms',
                    'description': 'List supported platforms',
                    'parameters': {}
                }
            ]
            return jsonify({
                'jsonrpc': '2.0',
                'result': {'tools': tools},
                'id': req_id
            })
        
        elif method == 'tools/call':
            tool_name = params.get('name')
            arguments = params.get('arguments', {})
            
            if tool_name == 'download_video':
                url = arguments.get('url')
                if not url:
                    return jsonify({'error': 'URL required'}), 400
                result = downloader.download_content(url, DOWNLOAD_DIR)
                return jsonify({
                    'jsonrpc': '2.0',
                    'result': {'output': result},
                    'id': req_id
                })
            
            elif tool_name == 'preview_video':
                url = arguments.get('url')
                if not url:
                    return jsonify({'error': 'URL required'}), 400
                result = preview.get_video_info(url)
                return jsonify({
                    'jsonrpc': '2.0',
                    'result': {'output': result},
                    'id': req_id
                })
            
            elif tool_name == 'get_supported_platforms':
                result = supported_platforms()
                return jsonify({
                    'jsonrpc': '2.0',
                    'result': {'output': result},
                    'id': req_id
                })
        
        return jsonify({
            'jsonrpc': '2.0',
            'error': {'code': -32601, 'message': 'Method not found'},
            'id': req_id
        }), 400
        
    except Exception as e:
        return jsonify({
            'jsonrpc': '2.0',
            'error': {'code': -32603, 'message': str(e)},
            'id': data.get('id') if data else None
        }), 500

@app.route('/mcp/tools', methods=['GET'])
def mcp_tools():
    """List MCP tools"""
    tools = [
        {'name': 'download_video', 'description': 'Download a video from social media'},
        {'name': 'preview_video', 'description': 'Get video preview info'},
        {'name': 'get_supported_platforms', 'description': 'List supported platforms'}
    ]
    return jsonify({'tools': tools})

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
    print("🌿 SOCIAL MEDIA DOWNLOADER v2.0 (Complete)")
    print("=" * 60)
    print("📱 Supported Platforms:")
    print("  • TikTok 🎵")
    print("  • YouTube ▶️")
    print("  • Instagram 📸")
    print("  • Twitter/X 🐦")
    print("  • Facebook 📘")
    print("  • Reddit 🔴")
    print("  • Vimeo 🎬")
    print("  • Dailymotion 🎥")
    print("  • Twitch 📺")
    print("=" * 60)
    print("💾 Save Options: Local | Gallery | Google Drive")
    print("=" * 60)
    print("🎯 Features:")
    print("  • Auto-platform detection")
    print("  • Bulk downloads")
    print("  • Video preview")
    print("  • Gallery save")
    print("  • Google Drive integration")
    print("  • Audio extraction (MP3)")
    print("  • Thumbnail extraction")
    print("  • Subtitle extraction")
    print("  • Metadata extraction")
    print("  • Playlist support")
    print("  • Stories download")
    print("  • MCP Server")
    print("  • REST API")
    print("=" * 60)
    print("📁 Downloads folder:", DOWNLOAD_DIR)
    print("📁 Extractions folder:", EXTRACT_DIR)
    print("🌐 Server running on: http://localhost:" + str(port))
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=True)
