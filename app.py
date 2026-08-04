from flask import Flask, request, render_template, jsonify, send_file, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
import os
import tempfile
import threading
import requests
import json
import re
import pickle
import http.client
import subprocess
import shutil
import time
import random
import zipfile
from datetime import datetime
from werkzeug.utils import secure_filename

# Third-party imports
try:
    import yt_dlp
except ImportError:
    yt_dlp = None
    print("yt_dlp not installed. Some features limited.")

try:
    import instaloader
except ImportError:
    instaloader = None
    print("instaloader not installed. Instagram features limited.")

try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
except ImportError:
    build = None
    MediaFileUpload = None
    HttpError = Exception
    InstalledAppFlow = None
    Request = None
    print("Google API libraries not installed. Drive features disabled.")

# ============================================
# APP CONFIGURATION
# ============================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-this')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['SESSION_TYPE'] = 'filesystem'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

CORS(app, resources={r"/*": {"origins": "*"}})

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

DOWNLOAD_DIR = os.path.join(os.getcwd(), 'downloads')
TEMP_DIR = os.path.join(os.getcwd(), 'temp')
EXTRACT_DIR = os.path.join(os.getcwd(), 'extractions')

for directory in [DOWNLOAD_DIR, TEMP_DIR, EXTRACT_DIR]:
    os.makedirs(directory, exist_ok=True)

RAPIDAPI_KEY = os.environ.get('RAPIDAPI_KEY', 'e7e2b4ac57mshf5be36f57ac2478p1511dbjsne2dce6703f94')

# ============================================
# URL VALIDATION
# ============================================
INSTAGRAM_REGEX = re.compile(r'instagram\.com/([a-zA-Z0-9_\.]+)')
FACEBOOK_REGEX = re.compile(r'(facebook\.com|fb\.watch|fb\.com)')
YOUTUBE_REGEX = re.compile(r'(youtube\.com|youtu\.be)')
TWITTER_REGEX = re.compile(r'(twitter\.com|x\.com)')

# ============================================
# TIKTOK URL VALIDATION - FIXED
# ============================================

TIKTOK_REGEX = re.compile(r'https?://(www\.|vm\.|vt\.)?tiktok\.com/(@[\w\-]+/video/[\d]+|@[\w\-]+/v/[\d]+|t/[\w]+|[\w]+)')

def is_valid_tiktok_url(url):
    """Check if URL is a valid TikTok video URL"""
    # First check regex
    if not bool(TIKTOK_REGEX.search(url)):
        return False
    
    # Make sure it's not just the homepage
    if url in ['https://www.tiktok.com', 'https://www.tiktok.com/', 'https://www.tiktok.com/?_r=1']:
        return False
    
    # Must have @username or /video/ or /t/ or vm/vt domain
    if '@' in url or '/video/' in url or '/v/' in url or '/t/' in url or 'vm.tiktok.com' in url or 'vt.tiktok.com' in url:
        return True
    
    return False

def extract_tiktok_video_id(url):
    """Extract video ID from TikTok URL"""
    patterns = [
        r'/video/(\d+)',
        r'/v/(\d+)',
        r'/t/(\w+)',
        r'vm\.tiktok\.com/(\w+)',
        r'vt\.tiktok\.com/(\w+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def is_valid_instagram_url(url):
    return bool(INSTAGRAM_REGEX.search(url))

def is_valid_facebook_url(url):
    return bool(FACEBOOK_REGEX.search(url))

def is_valid_youtube_url(url):
    return bool(YOUTUBE_REGEX.search(url))

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
        self.enabled = all([build is not None, InstalledAppFlow is not None, Request is not None])

        self.client_id = os.environ.get('GOOGLE_CLIENT_ID')
        self.client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
        self.project_id = os.environ.get('GOOGLE_PROJECT_ID')
        self.auth_uri = os.environ.get('GOOGLE_AUTH_URI', 'https://accounts.google.com/o/oauth2/auth')
        self.token_uri = os.environ.get('GOOGLE_TOKEN_URI', 'https://oauth2.googleapis.com/token')
        self.auth_provider_cert_url = os.environ.get('GOOGLE_AUTH_PROVIDER_CERT_URL', 'https://www.googleapis.com/oauth2/v1/certs')
        self.redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:5000/drive/callback')

        # Persist selected folder across restarts / worker respawns
        self.folder_file = 'selected_folder.json'
        self._load_selected_folder()

        if self.enabled:
            self._load_token()

    def _load_token(self):
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, 'rb') as token:
                    self.creds = pickle.load(token)
                return True
        except Exception as e:
            print(f"Could not load token: {e}")
        return False

    def _save_token(self):
        try:
            with open(self.token_file, 'wb') as token:
                pickle.dump(self.creds, token)
            return True
        except Exception as e:
            print(f"Could not save token: {e}")
        return False

    def _load_selected_folder(self):
        try:
            if os.path.exists(self.folder_file):
                with open(self.folder_file, 'r') as f:
                    data = json.load(f)
                    self.selected_folder_id = data.get('folder_id')
                    self.selected_folder_name = data.get('folder_name')
        except Exception as e:
            print(f"Could not load selected folder: {e}")

    def _save_selected_folder(self):
        try:
            with open(self.folder_file, 'w') as f:
                json.dump({'folder_id': self.selected_folder_id, 'folder_name': self.selected_folder_name}, f)
            return True
        except Exception as e:
            print(f"Could not save selected folder: {e}")
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
        if not self.enabled:
            return {'status': 'error', 'message': 'Google Drive libraries not installed.'}
        if not self.client_id or not self.client_secret:
            return {'status': 'error', 'message': 'Google Drive credentials not configured.'}
        try:
            config = self.get_credentials_config()
            flow = InstalledAppFlow.from_client_config(config, SCOPES)
            flow.redirect_uri = self.redirect_uri
            auth_url, _ = flow.authorization_url(access_type='offline', include_granted_scopes='true', prompt='consent')
            self._flow = flow
            return {'status': 'success', 'auth_url': auth_url, 'message': 'Please visit the URL to authorize'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def authenticate_with_code(self, auth_code):
        if not self.enabled:
            return {'status': 'error', 'message': 'Google Drive libraries not installed.'}
        try:
            if not hasattr(self, '_flow') or not self._flow:
                return {'status': 'error', 'message': 'No authentication flow initialized.'}
            self._flow.fetch_token(code=auth_code)
            self.creds = self._flow.credentials
            self._save_token()
            self.service = build('drive', 'v3', credentials=self.creds)
            user_info = self.service.about().get(fields='user').execute()
            user_email = user_info['user']['emailAddress']
            return {'status': 'success', 'message': f'Connected to {user_email}', 'email': user_email}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def authenticate(self):
        if not self.enabled:
            return {'status': 'error', 'message': 'Google Drive libraries not installed.'}
        try:
            if self.creds and self.creds.valid:
                if self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                    self._save_token()
                self.service = build('drive', 'v3', credentials=self.creds)
                user_info = self.service.about().get(fields='user').execute()
                return {'status': 'success', 'message': f'Already connected', 'email': user_info['user']['emailAddress'], 'connected': True}
            if self.creds and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                    self._save_token()
                    self.service = build('drive', 'v3', credentials=self.creds)
                    user_info = self.service.about().get(fields='user').execute()
                    return {'status': 'success', 'message': f'Reconnected', 'email': user_info['user']['emailAddress'], 'connected': True}
                except Exception as e:
                    print(f"Refresh failed: {e}")
            return self.get_auth_url()
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def list_folders(self):
        if not self.service:
            return {'status': 'error', 'message': 'Not authenticated'}
        try:
            results = self.service.files().list(q="mimeType='application/vnd.google-apps.folder'", fields="files(id, name, createdTime)", orderBy="createdTime desc").execute()
            return {'status': 'success', 'folders': results.get('files', [])}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def create_folder(self, folder_name):
        if not self.service:
            return {'status': 'error', 'message': 'Not authenticated'}
        try:
            file_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
            file = self.service.files().create(body=file_metadata, fields='id, name').execute()
            return {'status': 'success', 'folder_id': file.get('id'), 'folder_name': file.get('name')}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def select_folder(self, folder_id, folder_name):
        self.selected_folder_id = folder_id
        self.selected_folder_name = folder_name
        self._save_selected_folder()
        return {'status': 'success', 'message': f'Selected folder: {folder_name}'}

    def upload_file(self, file_path, file_name, folder_id=None):
        if not self.service:
            return {'status': 'error', 'message': 'Not authenticated. Please connect Google Drive first.'}
        if not folder_id:
            folder_id = self.selected_folder_id
        if not folder_id:
            return {'status': 'error', 'message': 'No Drive folder selected. Please select a folder first.'}
        if not os.path.exists(file_path):
            return {'status': 'error', 'message': f'Local file not found: {file_path}'}
        try:
            file_metadata = {'name': file_name, 'parents': [folder_id]}
            media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True)
            file = self.service.files().create(body=file_metadata, media_body=media, fields='id, name, webViewLink').execute()
            return {'status': 'success', 'message': f'Uploaded: {file.get("name")}', 'file_id': file.get('id'), 'web_link': file.get('webViewLink')}
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
# ============================================
# TIKTOK DOWNLOADER - COMPLETE FIX
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
        # Validate URL first
        if not is_valid_tiktok_url(url):
            return {'status': 'error', 'message': 'Invalid TikTok URL. Use format: https://www.tiktok.com/@username/video/123456789'}
        
        # Try to resolve short URLs
        if 'vm.tiktok.com' in url or 'vt.tiktok.com' in url:
            try:
                response = self.session.get(url, allow_redirects=True, timeout=10)
                if response.url != url:
                    url = response.url
                    print(f"Resolved to: {url}")
            except Exception as e:
                print(f"URL resolution error: {e}")
        
        methods = [
            self._download_tikwm,
            self._download_ytdlp,
            self._download_rapidapi,
            self._download_ssstik,
        ]
        
        errors = []
        for method in methods:
            try:
                print(f"Trying {method.__name__}...")
                result = method(url)
                if result and result.get('video_url'):
                    print(f"{method.__name__} success!")
                    return result
                elif result and result.get('status') == 'success':
                    print(f"{method.__name__} returned success but no video_url")
                else:
                    print(f"{method.__name__} failed or returned no data")
            except Exception as e:
                print(f"{method.__name__} error: {str(e)}")
                errors.append(f"{method.__name__}: {str(e)}")
                continue
        
        return {'status': 'error', 'message': 'All TikTok methods failed', 'errors': errors}

    def _download_tikwm(self, url):
        try:
            response = self.session.get('https://www.tikwm.com/api/', params={'url': url, 'hd': 1}, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 0:
                    video_data = result['data']
                    video_url = video_data.get('play', '')
                    if video_url:
                        return {
                            'status': 'success',
                            'video_url': video_url,
                            'title': video_data.get('title', 'TikTok Video'),
                            'author': video_data.get('author', {}).get('unique_id', 'Unknown'),
                            'duration': video_data.get('duration', 0),
                            'views': video_data.get('play_count', 0),
                            'likes': video_data.get('digg_count', 0),
                            'comments': video_data.get('comment_count', 0),
                            'thumbnail': video_data.get('cover', ''),
                            'source': 'tikwm'
                        }
        except Exception as e:
            print(f"TikWM error: {e}")
        return None

    def _download_ytdlp(self, url):
        if yt_dlp is None:
            return None
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'format': 'best',
                'extract_flat': False,
                'ignoreerrors': True,
                'retries': 10,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    # Try different ways to get video URL
                    video_url = None
                    
                    if info.get('url'):
                        video_url = info['url']
                    elif info.get('webpage_url'):
                        video_url = info['webpage_url']
                    elif info.get('formats'):
                        for fmt in info['formats']:
                            if fmt.get('url'):
                                video_url = fmt['url']
                                break
                    
                    if video_url:
                        return {
                            'status': 'success',
                            'video_url': video_url,
                            'title': info.get('title', 'TikTok Video'),
                            'author': info.get('uploader', 'Unknown'),
                            'duration': info.get('duration', 0),
                            'views': info.get('view_count', 0),
                            'likes': info.get('like_count', 0),
                            'source': 'ytdlp'
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
                    video_url = result['data']['video']
                    if video_url:
                        return {
                            'status': 'success',
                            'video_url': video_url,
                            'title': result['data'].get('title', 'TikTok Video'),
                            'author': result['data'].get('author', {}).get('unique_id', 'Unknown'),
                            'source': 'rapidapi'
                        }
        except Exception as e:
            print(f"RapidAPI error: {e}")
        return None

    def _download_ssstik(self, url):
        try:
            response = self.session.post(
                'https://ssstik.io/api',
                data={'url': url},
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                if result.get('video'):
                    return {
                        'status': 'success',
                        'video_url': result['video'],
                        'title': result.get('title', 'TikTok Video'),
                        'author': result.get('author', 'Unknown'),
                        'duration': result.get('duration', 0),
                        'views': result.get('views', 0),
                        'likes': result.get('likes', 0),
                        'source': 'ssstik'
                    }
        except Exception as e:
            print(f"SSSTikTok error: {e}")
        return None

tiktok_downloader = TikTokDownloader()

# ============================================
# INSTAGRAM DOWNLOADER - MULTI METHOD
# ============================================
class InstagramDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })

    def download(self, url, path):
        if not is_valid_instagram_url(url):
            return {'status': 'error', 'message': 'Invalid Instagram URL'}
        try:
            result = self._download_via_api(url, path)
            if result and result.get('status') == 'success':
                return result
        except Exception as e:
            print(f"Instagram API error: {e}")
        if instaloader:
            try:
                return self._download_via_instaloader(url, path)
            except Exception as e:
                return {'status': 'error', 'message': f'Instagram error: {str(e)}'}
        return {'status': 'error', 'message': 'Instagram download failed'}

    def _download_via_api(self, url, path):
        try:
            username = self.extract_instagram_username(url)
            if not username:
                return None
            # Try Instagram Looter API
            conn = http.client.HTTPSConnection("instagram-looter2.p.rapidapi.com")
            headers = {'x-rapidapi-key': RAPIDAPI_KEY, 'x-rapidapi-host': "instagram-looter2.p.rapidapi.com"}
            conn.request("GET", f"/profile?username={username}", headers=headers)
            res = conn.getresponse()
            profile_data = json.loads(res.read().decode("utf-8"))
            user_id = (profile_data.get('pk') or profile_data.get('id') or profile_data.get('user_id') or
                      (profile_data.get('user') and (profile_data['user'].get('pk') or profile_data['user'].get('id'))))
            if not user_id:
                return None
            conn = http.client.HTTPSConnection("instagram-looter2.p.rapidapi.com")
            conn.request("GET", f"/reels?id={user_id}&count=12", headers=headers)
            res = conn.getresponse()
            reels_data = json.loads(res.read().decode("utf-8"))
            reel_links = self._extract_reel_links(reels_data)
            if reel_links:
                video_url = reel_links[0]
                safe_name = re.sub(r'[<>:\"/\\|?*]', '_', username)
                filename = f"Instagram_{safe_name}_{int(time.time())}.mp4"
                filepath = os.path.join(path, filename)
                response = requests.get(video_url, stream=True, timeout=60)
                if response.status_code == 200:
                    with open(filepath, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    return {
                        'status': 'success', 'message': 'Instagram reel downloaded via API!',
                        'username': username, 'type': 'reel', 'filename': filename,
                        'filepath': filepath, 'size': os.path.getsize(filepath), 'source': 'rapidapi'
                    }
            return None
        except Exception as e:
            print(f"Instagram API download error: {e}")
            return None

    def _extract_reel_links(self, data):
        reel_links = []
        possible_arrays = [
            data.get('items'), data.get('medias'), data.get('reels'),
            data.get('data', {}).get('items') if isinstance(data.get('data'), dict) else None,
            data.get('data', {}).get('medias') if isinstance(data.get('data'), dict) else None,
            data if isinstance(data, list) else None
        ]
        list_data = None
        for arr in possible_arrays:
            if isinstance(arr, list) and len(arr) > 0:
                list_data = arr
                break
        if not list_data:
            return reel_links
        for item in list_data:
            video_url = (
                (item.get('media', {}).get('video_versions', [{}])[0].get('url') if isinstance(item.get('media'), dict) else None) or
                (item.get('video_versions', [{}])[0].get('url') if isinstance(item.get('video_versions'), list) else None) or
                item.get('video_url') or item.get('video') or
                (item.get('media', {}).get('video_url') if isinstance(item.get('media'), dict) else None)
            )
            if video_url:
                reel_links.append(video_url)
        return reel_links

    def _download_via_instaloader(self, url, path):
        loader = instaloader.Instaloader(
            dirname_pattern=path, filename_pattern='{profile}_{mediaid}_{date_utc}',
            download_videos=True, download_video_thumbnails=False, download_geotags=False,
            download_comments=False, save_metadata=True, compress_json=False, post_metadata_txt_pattern=None,
        )
        if '/stories/' in url:
            username = self.extract_instagram_username(url)
            if username:
                profile = instaloader.Profile.from_username(loader.context, username)
                for story in loader.get_stories([profile.userid]):
                    for item in story.get_items():
                        loader.download_storyitem(item, target=username)
                return {'status': 'success', 'message': f'Instagram stories downloaded for {username}', 'type': 'stories', 'source': 'instaloader'}
        elif '/reel/' in url or '/p/' in url or '/tv/' in url:
            shortcode = self.extract_instagram_shortcode(url)
            post = instaloader.Post.from_shortcode(loader.context, shortcode)
            loader.download_post(post, target=post.owner_username)
            content_type = 'reel' if post.is_video else 'post'
            if post.typename == 'GraphSidecar':
                content_type = 'carousel'
            return {
                'status': 'success', 'message': f'Instagram {content_type} downloaded!',
                'username': post.owner_username,
                'caption': post.caption[:100] + '...' if post.caption and len(post.caption) > 100 else post.caption,
                'type': content_type, 'likes': post.likes, 'comments': post.comments, 'source': 'instaloader'
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
            return {'status': 'success', 'message': f'Downloaded {count} posts from {username}', 'type': 'profile', 'count': count, 'source': 'instaloader'}

    def get_preview(self, url):
        try:
            shortcode = self.extract_instagram_shortcode(url)
            if not shortcode:
                return {'status': 'error', 'message': 'Invalid Instagram URL'}
            if instaloader:
                loader = instaloader.Instaloader()
                post = instaloader.Post.from_shortcode(loader.context, shortcode)
                return {
                    'status': 'success', 'title': post.caption[:100] if post.caption else 'Instagram Post',
                    'uploader': post.owner_username, 'duration': post.video_duration if post.is_video else 0,
                    'thumbnail': post.url, 'views': post.video_view_count if post.is_video else 0,
                    'likes': post.likes, 'comments': post.comments, 'platform': 'instagram', 'url': url
                }
            return {'status': 'error', 'message': 'instaloader not installed'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def extract_instagram_shortcode(self, url):
        patterns = [r'/p/([^/?]+)', r'/reel/([^/?]+)', r'/tv/([^/?]+)']
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
# FACEBOOK DOWNLOADER - MULTI API
# ============================================
class FacebookDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
        })

    def download(self, url, path):
        if not is_valid_facebook_url(url):
            return {'status': 'error', 'message': 'Invalid Facebook URL'}
        methods = [self._download_via_ytdlp, self._download_via_fdownloader, self._download_via_tikwm_style]
        errors = []
        for method in methods:
            try:
                print(f"Trying Facebook {method.__name__}...")
                result = method(url, path)
                if result and result.get('status') == 'success':
                    print(f"Facebook {method.__name__} success!")
                    return result
            except Exception as e:
                print(f"Facebook {method.__name__} error: {str(e)}")
                errors.append(f"{method.__name__}: {str(e)}")
                continue
        return {'status': 'error', 'message': 'All Facebook methods failed', 'errors': errors}

    def _download_via_ytdlp(self, url, path):
        if yt_dlp is None:
            return None
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Facebook_%(title)s_%(id)s.%(ext)s'),
                'format': 'best[ext=mp4]/best', 'quiet': True, 'ignoreerrors': True,
                'retries': 5, 'timeout': 60,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    for f in os.listdir(path):
                        if f.startswith('Facebook_') and f.endswith('.mp4'):
                            filepath = os.path.join(path, f)
                            return {
                                'status': 'success', 'message': 'Facebook video downloaded!',
                                'title': info.get('title', 'Facebook Video'),
                                'duration': info.get('duration', 0),
                                'filename': f, 'filepath': filepath,
                                'size': os.path.getsize(filepath), 'source': 'ytdlp'
                            }
            return None
        except Exception as e:
            print(f"Facebook ytdlp error: {e}")
            return None

    def _download_via_fdownloader(self, url, path):
        try:
            response = self.session.post('https://fdownloader.net/api/ajaxSearch',
                data={'q': url},
                headers={'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest',
                         'Origin': 'https://fdownloader.net', 'Referer': 'https://fdownloader.net/'},
                timeout=20)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'ok' and 'links' in data:
                    hd = data['links'].get('hd', '')
                    sd = data['links'].get('sd', '')
                    video_url = hd if hd else sd
                    if video_url:
                        filename = f"Facebook_{int(time.time())}.mp4"
                        filepath = os.path.join(path, filename)
                        vid_response = self.session.get(video_url, stream=True, timeout=60)
                        if vid_response.status_code == 200:
                            with open(filepath, 'wb') as f:
                                for chunk in vid_response.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                            return {
                                'status': 'success', 'message': 'Facebook video downloaded via API!',
                                'title': data.get('title', 'Facebook Video'),
                                'filename': filename, 'filepath': filepath,
                                'size': os.path.getsize(filepath), 'source': 'fdownloader_api'
                            }
            return None
        except Exception as e:
            print(f"Facebook fdownloader error: {e}")
            return None

    def _download_via_tikwm_style(self, url, path):
        try:
            apis = ['https://snapsave.app/api/ajaxSearch', 'https://getfvid.com/api/ajaxSearch']
            for api_url in apis:
                try:
                    response = self.session.post(api_url, data={'q': url},
                        headers={'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest'},
                        timeout=15)
                    if response.status_code == 200:
                        data = response.json()
                        video_url = None
                        if 'links' in data and isinstance(data['links'], dict):
                            video_url = data['links'].get('hd') or data['links'].get('sd')
                        elif 'url' in data:
                            video_url = data['url']
                        if video_url:
                            filename = f"Facebook_{int(time.time())}.mp4"
                            filepath = os.path.join(path, filename)
                            vid_response = self.session.get(video_url, stream=True, timeout=60)
                            if vid_response.status_code == 200:
                                with open(filepath, 'wb') as f:
                                    for chunk in vid_response.iter_content(chunk_size=8192):
                                        if chunk:
                                            f.write(chunk)
                                return {
                                    'status': 'success', 'message': 'Facebook video downloaded!',
                                    'title': data.get('title', 'Facebook Video'),
                                    'filename': filename, 'filepath': filepath,
                                    'size': os.path.getsize(filepath), 'source': 'alternative_api'
                                }
                except Exception:
                    continue
            return None
        except Exception as e:
            print(f"Facebook alternative API error: {e}")
            return None

    def get_preview(self, url):
        if yt_dlp is None:
            return {'status': 'error', 'message': 'yt-dlp not installed'}
        try:
            ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': False, 'format': 'best', 'ignoreerrors': True, 'timeout': 30}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    return {
                        'status': 'success', 'title': info.get('title', 'Facebook Video'),
                        'uploader': info.get('uploader', 'Unknown'), 'duration': info.get('duration', 0),
                        'thumbnail': info.get('thumbnail', ''), 'views': info.get('view_count', 0),
                        'likes': info.get('like_count', 0), 'platform': 'facebook', 'url': url
                    }
            return {'status': 'error', 'message': 'Could not get Facebook info'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

facebook_downloader = FacebookDownloader()

# ============================================
# YOUTUBE DOWNLOADER
# ============================================
def download_youtube_content(url, path):
    if yt_dlp is None:
        return {'status': 'error', 'message': 'yt-dlp not installed'}
    if not is_valid_youtube_url(url):
        return {'status': 'error', 'message': 'Invalid YouTube URL'}
    try:
        ydl_opts = {
            'outtmpl': os.path.join(path, '%(uploader)s - %(title)s.%(ext)s'),
            'format': 'best[ext=mp4]/best', 'quiet': True, 'ignoreerrors': True,
            'retries': 10, 'writesubtitles': True, 'writeautomaticsub': True,
            'subtitleslangs': ['en'],
            'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if 'entries' in info:
                titles = [entry.get('title', 'Unknown') for entry in info['entries'] if entry]
                return {'status': 'success', 'message': f'Downloaded {len(titles)} videos from playlist', 'titles': titles[:5], 'type': 'playlist', 'count': len(titles)}
            else:
                filename = f"{info.get('uploader', 'Unknown')} - {info.get('title', 'video')}.mp4"
                filepath = os.path.join(path, filename)
                return {'status': 'success', 'message': 'YouTube content downloaded successfully!', 'title': info.get('title', 'Unknown'), 'uploader': info.get('uploader', 'Unknown'), 'type': 'video', 'duration': info.get('duration', 0), 'views': info.get('view_count', 0), 'filename': filename, 'filepath': filepath, 'size': os.path.getsize(filepath) if os.path.exists(filepath) else 0}
    except Exception as e:
        return {'status': 'error', 'message': f'YouTube error: {str(e)}'}

def get_youtube_info(url):
    if yt_dlp is None:
        return {'status': 'error', 'message': 'yt-dlp not installed'}
    try:
        ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': False, 'format': 'best', 'ignoreerrors': True, 'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8', 'Accept-Language': 'en-US,en;q=0.5'}}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                return {'status': 'success', 'title': info.get('title', 'Unknown'), 'uploader': info.get('uploader', 'Unknown'), 'duration': info.get('duration', 0), 'thumbnail': info.get('thumbnail', ''), 'views': info.get('view_count', 0), 'likes': info.get('like_count', 0), 'platform': 'youtube', 'url': url}
        return {'status': 'error', 'message': 'Could not get YouTube info'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

# ============================================
# VIDEO EXTRACTOR
# ============================================
class VideoExtractor:
    @staticmethod
    def extract_metadata(filepath):
        if yt_dlp is None:
            return {'error': 'yt-dlp not installed'}
        try:
            ydl_opts = {'quiet': True, 'no_warnings': True, 'timeout': 30}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(filepath, download=False)
                return {'title': info.get('title', 'Unknown'), 'uploader': info.get('uploader', 'Unknown'), 'duration': info.get('duration', 0), 'view_count': info.get('view_count', 0), 'like_count': info.get('like_count', 0), 'comment_count': info.get('comment_count', 0), 'upload_date': info.get('upload_date', ''), 'description': info.get('description', '')[:500]}
        except Exception as e:
            return {'error': str(e)}

    @staticmethod
    def extract_audio(filepath, output_dir=TEMP_DIR):
        if yt_dlp is None:
            return {'status': 'error', 'message': 'yt-dlp not installed'}
        try:
            filename = os.path.basename(filepath)
            name_without_ext = os.path.splitext(filename)[0]
            ydl_opts = {
                'format': 'bestaudio/best', 'outtmpl': os.path.join(output_dir, name_without_ext),
                'quiet': True, 'no_warnings': True, 'timeout': 60,
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
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
            if yt_dlp is None:
                return {'status': 'error', 'message': 'yt-dlp not installed'}
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
        if yt_dlp is None:
            return {'status': 'error', 'message': 'yt-dlp not installed'}
        try:
            filename = os.path.basename(filepath)
            name_without_ext = os.path.splitext(filename)[0]
            ydl_opts = {'quiet': True, 'no_warnings': True, 'timeout': 60, 'writesubtitles': True, 'writeautomaticsub': True, 'subtitleslangs': ['en'], 'subtitlesformat': 'vtt', 'outtmpl': os.path.join(output_dir, name_without_ext)}
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
        return {'metadata': VideoExtractor.extract_metadata(filepath), 'audio': VideoExtractor.extract_audio(filepath, output_dir), 'thumbnail': VideoExtractor.extract_thumbnail(filepath, output_dir), 'subtitles': VideoExtractor.extract_subtitles(filepath, output_dir)}

extractor = VideoExtractor()

# ============================================
# GALLERY SAVER
# ============================================
class GallerySaver:
    @staticmethod
    def save_to_gallery(file_path, filename):
        if not os.path.exists(file_path):
            return {'status': 'error', 'message': 'File not found on server'}
        return {
            'status': 'success',
            'message': 'File is ready. Use the download link to save it to your device.',
            'download_url': f'/download-file/{filename}'
        }

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
            elif platform == 'facebook':
                return facebook_downloader.get_preview(url)
            else:
                return self.get_generic_info(url)
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def get_tiktok_info(self, url):
        try:
            result = tiktok_downloader.download(url)
            if result and result.get('status') == 'success':
                return {'status': 'success', 'title': result.get('title', 'TikTok Video'), 'uploader': result.get('author', 'Unknown'), 'duration': result.get('duration', 0), 'thumbnail': result.get('thumbnail', ''), 'views': result.get('views', 0), 'likes': result.get('likes', 0), 'comments': result.get('comments', 0), 'platform': 'tiktok', 'url': url, 'video_url': result.get('video_url')}
            return {'status': 'error', 'message': result.get('message', 'Could not fetch TikTok video')}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def get_generic_info(self, url):
        if yt_dlp is None:
            return {'status': 'error', 'message': 'yt-dlp not installed'}
        try:
            ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': False, 'format': 'best', 'ignoreerrors': True, 'timeout': 30}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    return {'status': 'success', 'title': info.get('title', 'Unknown'), 'uploader': info.get('uploader', 'Unknown'), 'duration': info.get('duration', 0), 'thumbnail': info.get('thumbnail', ''), 'views': info.get('view_count', 0), 'likes': info.get('like_count', 0), 'platform': self.detect_platform(url), 'url': url}
            return {'status': 'error', 'message': 'Could not get video info'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def detect_platform(self, url):
        url = url.lower()
        if 'tiktok.com' in url: return 'tiktok'
        elif 'youtube.com' in url or 'youtu.be' in url: return 'youtube'
        elif 'instagram.com' in url: return 'instagram'
        elif 'twitter.com' in url or 'x.com' in url: return 'twitter'
        elif 'facebook.com' in url or 'fb.watch' in url or 'fb.com' in url: return 'facebook'
        elif 'reddit.com' in url: return 'reddit'
        elif 'vimeo.com' in url: return 'vimeo'
        elif 'dailymotion.com' in url: return 'dailymotion'
        elif 'twitch.tv' in url: return 'twitch'
        else: return 'generic'

preview = VideoPreview()

# ============================================
# UNIVERSAL DOWNLOADER
# ============================================
class UniversalDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

    def detect_platform(self, url):
        url = url.lower()
        if 'tiktok.com' in url: return 'tiktok'
        elif 'youtube.com' in url or 'youtu.be' in url: return 'youtube'
        elif 'instagram.com' in url: return 'instagram'
        elif 'twitter.com' in url or 'x.com' in url: return 'twitter'
        elif 'facebook.com' in url or 'fb.watch' in url or 'fb.com' in url: return 'facebook'
        elif 'reddit.com' in url: return 'reddit'
        elif 'vimeo.com' in url: return 'vimeo'
        elif 'dailymotion.com' in url: return 'dailymotion'
        elif 'twitch.tv' in url: return 'twitch'
        else: return 'unknown'

    def download_content(self, url, path):
        platform = self.detect_platform(url)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        download_folder = os.path.join(path, f"{platform}_{timestamp}")
        os.makedirs(download_folder, exist_ok=True)
        if platform == 'tiktok':
            return self.download_tiktok(url, download_folder)
        elif platform == 'instagram':
            return instagram_downloader.download(url, download_folder)
        elif platform == 'youtube':
            return download_youtube_content(url, download_folder)
        elif platform == 'facebook':
            return facebook_downloader.download(url, download_folder)
        elif platform == 'twitter':
            return self.download_twitter(url, download_folder)
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
        if result.get('status') == 'error':
            return result
        if result.get('video_url'):
            return self._download_video(result['video_url'], path, f"TikTok_{result.get('author', 'Unknown')}_{result.get('title', 'video')}", result)
        return {'status': 'error', 'message': 'Failed to download TikTok video'}

    def _download_video(self, video_url, path, base_name, metadata=None):
        try:
            safe_name = re.sub(r'[<>:\"/\\|?*]', '_', base_name)
            filename = f"{safe_name[:50]}_{int(time.time())}.mp4"
            filepath = os.path.join(path, filename)
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': 'https://www.tiktok.com/', 'Accept': 'video/*'}
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
                                print(f"Progress: {(downloaded/total_size)*100:.1f}%")
                file_size = os.path.getsize(filepath)
                return {'status': 'success', 'message': 'Video downloaded successfully!', 'filename': filename, 'filepath': filepath, 'size': file_size, 'metadata': metadata or {}}
            return {'status': 'error', 'message': f'Download failed: HTTP {response.status_code}'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def download_twitter(self, url, path):
        if yt_dlp is None:
            return {'status': 'error', 'message': 'yt-dlp not installed'}
        try:
            ydl_opts = {'outtmpl': os.path.join(path, 'Twitter_%(uploader)s_%(title)s.%(ext)s'), 'format': 'best', 'quiet': True, 'ignoreerrors': True, 'retries': 5, 'timeout': 60}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = f"Twitter_{info.get('uploader', 'Unknown')}_{info.get('title', 'tweet')}.mp4"
                filepath = os.path.join(path, filename)
                return {'status': 'success', 'message': 'Twitter content downloaded!', 'title': info.get('title', 'Tweet'), 'uploader': info.get('uploader', 'Unknown'), 'likes': info.get('like_count', 0), 'retweets': info.get('retweet_count', 0), 'filename': filename, 'filepath': filepath}
        except Exception as e:
            return {'status': 'error', 'message': f'Twitter error: {str(e)}'}

    def download_reddit(self, url, path):
        if yt_dlp is None:
            return {'status': 'error', 'message': 'yt-dlp not installed'}
        try:
            ydl_opts = {'outtmpl': os.path.join(path, 'Reddit_%(title)s.%(ext)s'), 'format': 'best', 'quiet': True, 'ignoreerrors': True, 'retries': 5, 'timeout': 60}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = f"Reddit_{info.get('title', 'post')}.mp4"
                filepath = os.path.join(path, filename)
                return {'status': 'success', 'message': 'Reddit content downloaded!', 'title': info.get('title', 'Reddit Post'), 'ups': info.get('like_count', 0), 'comments': info.get('comment_count', 0), 'filename': filename, 'filepath': filepath}
        except Exception as e:
            return {'status': 'error', 'message': f'Reddit error: {str(e)}'}

    def download_vimeo(self, url, path):
        if yt_dlp is None:
            return {'status': 'error', 'message': 'yt-dlp not installed'}
        try:
            ydl_opts = {'outtmpl': os.path.join(path, 'Vimeo_%(title)s.%(ext)s'), 'format': 'best', 'quiet': True, 'ignoreerrors': True, 'retries': 5, 'timeout': 60}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = f"Vimeo_{info.get('title', 'video')}.mp4"
                filepath = os.path.join(path, filename)
                return {'status': 'success', 'message': 'Vimeo video downloaded!', 'title': info.get('title', 'Vimeo Video'), 'duration': info.get('duration', 0), 'filename': filename, 'filepath': filepath}
        except Exception as e:
            return {'status': 'error', 'message': f'Vimeo error: {str(e)}'}

    def download_dailymotion(self, url, path):
        if yt_dlp is None:
            return {'status': 'error', 'message': 'yt-dlp not installed'}
        try:
            ydl_opts = {'outtmpl': os.path.join(path, 'Dailymotion_%(title)s.%(ext)s'), 'format': 'best', 'quiet': True, 'ignoreerrors': True, 'retries': 5, 'timeout': 60}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = f"Dailymotion_{info.get('title', 'video')}.mp4"
                filepath = os.path.join(path, filename)
                return {'status': 'success', 'message': 'Dailymotion video downloaded!', 'title': info.get('title', 'Dailymotion Video'), 'duration': info.get('duration', 0), 'filename': filename, 'filepath': filepath}
        except Exception as e:
            return {'status': 'error', 'message': f'Dailymotion error: {str(e)}'}

    def download_twitch(self, url, path):
        if yt_dlp is None:
            return {'status': 'error', 'message': 'yt-dlp not installed'}
        try:
            ydl_opts = {'outtmpl': os.path.join(path, 'Twitch_%(title)s.%(ext)s'), 'format': 'best', 'quiet': True, 'ignoreerrors': True, 'retries': 5, 'timeout': 60}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = f"Twitch_{info.get('title', 'video')}.mp4"
                filepath = os.path.join(path, filename)
                return {'status': 'success', 'message': 'Twitch content downloaded!', 'title': info.get('title', 'Twitch Video'), 'uploader': info.get('uploader', 'Unknown'), 'filename': filename, 'filepath': filepath}
        except Exception as e:
            return {'status': 'error', 'message': f'Twitch error: {str(e)}'}

    def download_generic(self, url, path):
        if yt_dlp is None:
            return {'status': 'error', 'message': 'yt-dlp not installed'}
        try:
            ydl_opts = {'outtmpl': os.path.join(path, '%(extractor)s_%(title)s.%(ext)s'), 'format': 'best', 'quiet': True, 'ignoreerrors': True, 'retries': 5, 'timeout': 60}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = f"{info.get('extractor', 'generic')}_{info.get('title', 'video')}.mp4"
                filepath = os.path.join(path, filename)
                return {'status': 'success', 'message': 'Content downloaded!', 'title': info.get('title', 'Unknown'), 'extractor': info.get('extractor', 'Unknown'), 'filename': filename, 'filepath': filepath}
        except Exception as e:
            return {'status': 'error', 'message': f'Download error: {str(e)}'}

downloader = UniversalDownloader()

# ============================================
# API ROUTES - WITH /api PREFIX
# ============================================

@app.route('/api/health', methods=['GET'])
def api_health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'version': '3.1.0',
        'timestamp': datetime.now().isoformat(),
        'platforms': ['tiktok', 'youtube', 'instagram', 'twitter', 'facebook', 'reddit', 'vimeo', 'twitch', 'dailymotion']
    })

@app.route('/api/version', methods=['GET'])
def api_version():
    """Version info endpoint"""
    return jsonify({
        'version': '3.1.0',
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

@app.route('/api/platforms', methods=['GET'])
def api_platforms():
    """List supported platforms"""
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

@app.route('/api/preview', methods=['POST'])
def api_preview():
    """Preview video via API"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        if not url:
            return jsonify({'status': 'error', 'message': 'URL is required'}), 400
        result = preview.get_video_info(url)
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def api_download():
    """Download video via API"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        save_to = data.get('save_to', 'local')
        extract = data.get('extract', False)
        
        if not url:
            return jsonify({'status': 'error', 'message': 'URL is required'}), 400
        
        platform = downloader.detect_platform(url)
        result = downloader.download_content(url, DOWNLOAD_DIR)
        
        # LOG: Check what result contains
        print(f"Download result: {json.dumps(result, indent=2)[:500]}")
        
        if result.get('status') == 'success':
            if 'filepath' in result:
                filepath = result['filepath']
                filename = result.get('filename', os.path.basename(filepath))
                result['filename'] = filename
                result['download_link'] = f"/download-file/{filename}"
                
                if save_to == 'gallery':
                    gallery_result = GallerySaver.save_to_gallery(filepath, filename)
                    result['gallery'] = gallery_result
                
                if save_to == 'drive':
                    drive_result = drive_manager.upload_file(filepath, filename)
                    result['drive'] = drive_result
            
            # Always return download link
            if 'filename' in result:
                result['download_link'] = f"/download-file/{result['filename']}"
        
        result['platform'] = platform
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
@app.route('/api/bulk', methods=['POST'])
def api_bulk():
    """Bulk download via API"""
    try:
        data = request.get_json()
        urls = data.get('urls', [])
        save_to = data.get('save_to', 'local')
        
        if not urls:
            return jsonify({'status': 'error', 'message': 'URLs list is required'}), 400
        
        results = []
        for url in urls:
            if url.strip():
                result = downloader.download_content(url.strip(), DOWNLOAD_DIR)
                result['url'] = url
                
                if result.get('status') == 'success' and 'filepath' in result:
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
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/extract', methods=['POST'])
def api_extract():
    """Extract video via API"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        extract_type = data.get('extract_type', 'all')
        
        if not filename:
            return jsonify({'status': 'error', 'message': 'Filename required'}), 400
        
        file_path = None
        for root, dirs, files in os.walk(DOWNLOAD_DIR):
            if filename in files:
                file_path = os.path.join(root, filename)
                break
        
        if not file_path:
            return jsonify({'status': 'error', 'message': 'File not found'}), 404
        
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
            return jsonify({'status': 'error', 'message': 'Invalid extract_type'}), 400
        
        return jsonify({
            'status': 'success',
            'message': 'Extraction completed',
            'result': result
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/drive/auth', methods=['POST'])
def api_drive_auth():
    """Google Drive authentication via API"""
    try:
        data = request.get_json() or {}
        action = data.get('action', 'connect')
        code = data.get('code')
        
        if action == 'status':
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
        elif action == 'connect':
            if code:
                result = drive_manager.authenticate_with_code(code)
                return jsonify(result)
            else:
                result = drive_manager.get_auth_url()
                return jsonify(result)
        else:
            return jsonify({'status': 'error', 'message': 'Invalid action'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/drive/folders', methods=['GET'])
def api_drive_folders():
    """List Google Drive folders via API"""
    result = drive_manager.list_folders()
    return jsonify(result)

@app.route('/api/drive/upload', methods=['POST'])
def api_drive_upload():
    """Upload to Google Drive via API"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        folder_id = data.get('folder_id')
        
        if not filename:
            return jsonify({'status': 'error', 'message': 'Filename required'}), 400
        
        file_path = None
        for root, dirs, files in os.walk(DOWNLOAD_DIR):
            if filename in files:
                file_path = os.path.join(root, filename)
                break
        
        if not file_path:
            return jsonify({'status': 'error', 'message': 'File not found'}), 404
        
        result = drive_manager.upload_file(file_path, filename, folder_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/drive/folder/select', methods=['POST'])
def api_drive_select_folder():
    """Select Google Drive folder via API"""
    try:
        data = request.get_json()
        folder_id = data.get('folder_id')
        folder_name = data.get('folder_name')
        
        if not folder_id:
            return jsonify({'status': 'error', 'message': 'Folder ID required'}), 400
        
        result = drive_manager.select_folder(folder_id, folder_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/drive/folder/create', methods=['POST'])
def api_drive_create_folder():
    """Create Google Drive folder via API"""
    try:
        data = request.get_json()
        folder_name = data.get('folder_name')
        
        if not folder_name:
            return jsonify({'status': 'error', 'message': 'Folder name required'}), 400
        
        result = drive_manager.create_folder(folder_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ============================================
# MAIN FLASK ROUTES
# ============================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/preview', methods=['POST'])
@limiter.limit("30 per minute")
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
@limiter.limit("10 per minute")
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
                    if drive_result.get('status') != 'success':
                        result['status'] = 'partial_success'
                        result['message'] = f"Video downloaded but Google Drive upload failed: {drive_result.get('message')}"
                if extract:
                    extraction_result = extractor.extract_all(filepath, EXTRACT_DIR)
                    result['extraction'] = extraction_result
        result['platform'] = platform
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/bulk-download', methods=['POST'])
@limiter.limit("5 per minute")
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
                        if drive_result.get('status') != 'success':
                            result['status'] = 'partial_success'
                            result['message'] = f"Video downloaded but Google Drive upload failed: {drive_result.get('message')}"
                results.append(result)
                time.sleep(2)
        return jsonify({'status': 'success', 'message': f'Processed {len(results)} URLs', 'results': results})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/extract', methods=['POST'])
@limiter.limit("20 per minute")
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
        return jsonify({'status': 'success', 'message': 'Extraction completed', 'result': result})
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
        return '<html><head><title>Auth Success</title><style>body{font-family:Arial;text-align:center;padding:50px;background:#0a1f0a;color:white;}.success{color:#4CAF50;font-size:24px;}.container{max-width:500px;margin:0 auto;background:#1a3a1a;padding:40px;border-radius:10px;}.btn{display:inline-block;padding:12px 24px;background:#4CAF50;color:white;text-decoration:none;border-radius:5px;margin-top:20px;}</style></head><body><div class="container"><div class="success">Authentication Successful!</div><p>You can now close this window and return to the app.</p><a href="/" class="btn">Return to App</a></div></body></html>'
    else:
        return f'<html><body><h1>Authentication Failed</h1><p>{result.get("message")}</p></body></html>'

@app.route('/drive/status', methods=['GET'])
def drive_status():
    try:
        if drive_manager.service:
            user_info = drive_manager.service.about().get(fields='user').execute()
            return jsonify({
                'status': 'success', 'connected': True,
                'email': user_info['user']['emailAddress'],
                'selected_folder_id': drive_manager.selected_folder_id,
                'selected_folder_name': drive_manager.selected_folder_name
            })
        else:
            return jsonify({'status': 'success', 'connected': False, 'message': 'Not connected to Google Drive'})
    except Exception as e:
        return jsonify({'status': 'error', 'connected': False, 'message': str(e)})

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

@app.route('/downloads')
def list_downloads():
    try:
        items = []
        if os.path.exists(DOWNLOAD_DIR):
            for item in os.listdir(DOWNLOAD_DIR):
                item_path = os.path.join(DOWNLOAD_DIR, item)
                if os.path.isfile(item_path):
                    size = os.path.getsize(item_path)
                    items.append({'name': item, 'type': 'file', 'size': size, 'size_str': f"{size / 1024:.1f} KB" if size < 1024*1024 else f"{size / (1024*1024):.1f} MB", 'modified': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M:%S')})
                elif os.path.isdir(item_path):
                    files = [f for f in os.listdir(item_path) if os.path.isfile(os.path.join(item_path, f))]
                    total_size = sum(os.path.getsize(os.path.join(item_path, f)) for f in files)
                    items.append({'name': item, 'type': 'folder', 'file_count': len(files), 'size': total_size, 'size_str': f"{total_size / 1024:.1f} KB" if total_size < 1024*1024 else f"{total_size / (1024*1024):.1f} MB", 'modified': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M:%S')})
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
        for root, dirs, files in os.walk(DOWNLOAD_DIR):
            if safe_filename in files:
                return send_file(os.path.join(root, safe_filename), as_attachment=True)
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

@app.route('/supported-platforms')
def supported_platforms():
    return jsonify({
        'video_platforms': [
            'TikTok (Multi-API: TikWM, yt-dlp, RapidAPI)',
            'YouTube (Videos, Shorts, Playlists)',
            'Instagram (Posts, Reels, Stories, IGTV - Multi-API)',
            'Twitter/X',
            'Facebook (Multi-API: yt-dlp, Fdownloader, Alternative)',
            'Reddit', 'Twitch', 'Vimeo', 'Dailymotion'
        ],
        'features': [
            'Auto-platform detection', 'Bulk downloads', 'Video preview',
            'Direct browser download', 'Google Drive integration', 'Audio extraction (MP3)',
            'Thumbnail extraction', 'Subtitle extraction', 'Metadata extraction',
            'Playlist support', 'Stories download', 'Multi-API fallback (TikTok, FB, IG)',
            'Rate limiting protection', 'CORS enabled'
        ]
    })

@app.route('/api-docs')
def api_docs():
    return jsonify({
        'name': 'Universal Social Media Downloader API',
        'version': '3.1.0',
        'endpoints': [
            {'path': '/api/health', 'method': 'GET', 'description': 'Health check'},
            {'path': '/api/version', 'method': 'GET', 'description': 'Version info'},
            {'path': '/api/platforms', 'method': 'GET', 'description': 'List supported platforms'},
            {'path': '/api/preview', 'method': 'POST', 'description': 'Get video preview info'},
            {'path': '/api/download', 'method': 'POST', 'description': 'Download a video'},
            {'path': '/api/bulk', 'method': 'POST', 'description': 'Download multiple videos'},
            {'path': '/api/extract', 'method': 'POST', 'description': 'Extract audio, thumbnail, subtitles'},
            {'path': '/api/drive/auth', 'method': 'POST', 'description': 'Google Drive authentication'},
            {'path': '/api/drive/folders', 'method': 'GET', 'description': 'List Google Drive folders'},
            {'path': '/api/drive/upload', 'method': 'POST', 'description': 'Upload to Google Drive'},
            {'path': '/api/drive/folder/select', 'method': 'POST', 'description': 'Select Google Drive folder'},
            {'path': '/api/drive/folder/create', 'method': 'POST', 'description': 'Create Google Drive folder'},
        ]
    })


@app.route('/api-tester')
def api_tester():
    return render_template('api_tester.html')
    
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'status': 'error', 'message': 'Rate limit exceeded. Please slow down!'}), 429

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print("SOCIAL MEDIA DOWNLOADER v3.1 (Complete)")
    print("=" * 60)
    print("Supported Platforms:")
    print("  - TikTok (Multi-API Fallback)")
    print("  - YouTube")
    print("  - Instagram (Multi-API Fallback)")
    print("  - Twitter/X")
    print("  - Facebook (Multi-API Fallback)")
    print("  - Reddit, Vimeo, Dailymotion, Twitch")
    print("=" * 60)
    print("API Routes with /api prefix:")
    print("  - /api/health")
    print("  - /api/version")
    print("  - /api/platforms")
    print("  - /api/preview")
    print("  - /api/download")
    print("  - /api/bulk")
    print("  - /api/extract")
    print("  - /api/drive/*")
    print("=" * 60)
    print("Features: Auto-detection, Multi-API fallback, Rate limiting, CORS")
    print("=" * 60)
    print(f"Downloads: {DOWNLOAD_DIR}")
    print(f"Server: http://localhost:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=True)
