from flask import Flask, request, render_template, jsonify, send_file, session
import os
import tempfile
import json
import re
from datetime import datetime
import yt_dlp
import instaloader
from werkzeug.utils import secure_filename
import zipfile
import shutil
import time
import requests

# Import custom modules
from drive_integration import drive_manager
from video_preview import preview
from gallery_saver import GallerySaver

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-this')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['SESSION_TYPE'] = 'filesystem'

# Create required directories
DOWNLOAD_DIR = os.path.join(os.getcwd(), 'downloads')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ============================================
# TIKTOK DOWNLOADER CLASS
# ============================================

class TikTokDownloader:
    def __init__(self):
        self.apis = [
            {
                'name': 'TikWM',
                'url': 'https://www.tikwm.com/api/',
                'method': 'GET',
                'params': {'hd': 1}
            },
            {
                'name': 'SSSTikTok',
                'url': 'https://ssstik.io/api',
                'method': 'POST',
                'data': {}
            }
        ]
    
    def download(self, url):
        for api in self.apis:
            try:
                print(f"🔄 Trying {api['name']}...")
                
                if api['method'] == 'GET':
                    params = api.get('params', {})
                    params['url'] = url
                    response = requests.get(api['url'], params=params, timeout=30)
                else:
                    data = api.get('data', {})
                    data['url'] = url
                    response = requests.post(api['url'], data=data, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # TikWM format
                    if result.get('code') == 0:
                        video_data = result['data']
                        return {
                            'video_url': video_data.get('play', ''),
                            'title': video_data.get('title', 'TikTok Video'),
                            'author': video_data.get('author', {}).get('unique_id', 'Unknown'),
                            'duration': video_data.get('duration', 0),
                            'views': video_data.get('play_count', 0),
                            'likes': video_data.get('digg_count', 0),
                            'comments': video_data.get('comment_count', 0),
                            'thumbnail': video_data.get('cover', '')
                        }
                    
                    # SSSTikTok format
                    if 'video' in result:
                        return {
                            'video_url': result['video'],
                            'title': result.get('title', 'TikTok Video'),
                            'author': result.get('author', 'Unknown'),
                            'duration': result.get('duration', 0),
                            'views': result.get('views', 0),
                            'likes': result.get('likes', 0),
                            'comments': result.get('comments', 0)
                        }
                        
            except Exception as e:
                print(f"❌ {api['name']} error: {str(e)}")
                continue
        
        return None

tiktok_downloader = TikTokDownloader()

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
        
        # Create timestamped folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        download_folder = os.path.join(path, f"{platform}_{timestamp}")
        os.makedirs(download_folder, exist_ok=True)
        
        if platform == 'tiktok':
            return self.download_tiktok(url, download_folder)
        elif platform == 'youtube':
            return self.download_youtube(url, download_folder)
        elif platform == 'instagram':
            return self.download_instagram(url, download_folder)
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
        print("🎯 Downloading TikTok...")
        result = tiktok_downloader.download(url)
        
        if result and result.get('video_url'):
            print(f"✅ Found video: {result.get('title')}")
            download_result = self._download_video(
                result['video_url'], 
                path, 
                f"TikTok_{result.get('author', 'Unknown')}_{result.get('title', 'video')}", 
                result
            )
            if download_result.get('status') == 'success':
                download_result['platform'] = 'tiktok'
                download_result['metadata'] = result
            return download_result
        
        return {'status': 'error', 'message': 'Failed to download TikTok video. Please try again or use a different URL.'}
    
    def _download_video(self, video_url, path, base_name, metadata=None):
        try:
            # Clean filename
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', base_name)
            filename = f"{safe_name[:50]}_{int(time.time())}.mp4"
            filepath = os.path.join(path, filename)
            
            print(f"📥 Downloading: {filename}")
            
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
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                if int(progress) % 10 == 0:
                                    print(f"   Progress: {progress:.1f}%")
                
                file_size = os.path.getsize(filepath)
                print(f"✅ Downloaded: {filename} ({file_size / 1024:.1f} KB)")
                
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
    
    def download_youtube(self, url, path):
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
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if 'entries' in info:
                    return {
                        'status': 'success',
                        'message': f'Downloaded {len(info["entries"])} videos from playlist',
                        'type': 'playlist',
                        'count': len(info["entries"])
                    }
                else:
                    return {
                        'status': 'success',
                        'message': 'YouTube video downloaded!',
                        'title': info.get('title', 'Unknown'),
                        'uploader': info.get('uploader', 'Unknown'),
                        'duration': info.get('duration', 0),
                        'views': info.get('view_count', 0)
                    }
        except Exception as e:
            return {'status': 'error', 'message': f'YouTube error: {str(e)}'}
    
    def download_instagram(self, url, path):
        try:
            loader = instaloader.Instaloader(
                dirname_pattern=path,
                filename_pattern='{profile}_{mediaid}',
                download_videos=True,
                download_comments=False,
                save_metadata=True,
                post_metadata_txt_pattern=None,
            )
            
            shortcode = re.search(r'/p/([^/?]+)', url) or re.search(r'/reel/([^/?]+)', url) or re.search(r'/tv/([^/?]+)', url)
            if shortcode:
                post = instaloader.Post.from_shortcode(loader.context, shortcode.group(1))
                loader.download_post(post, target=post.owner_username)
                return {
                    'status': 'success',
                    'message': 'Instagram content downloaded!',
                    'username': post.owner_username,
                    'likes': post.likes,
                    'comments': post.comments
                }
            return {'status': 'error', 'message': 'Invalid Instagram URL'}
        except Exception as e:
            return {'status': 'error', 'message': f'Instagram error: {str(e)}'}
    
    def download_twitter(self, url, path):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Twitter_%(uploader)s_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'ignoreerrors': True,
                'retries': 10,
                'writesubtitles': True,
                'writeautomaticsub': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {
                    'status': 'success',
                    'message': 'Twitter content downloaded!',
                    'title': info.get('title', 'Tweet'),
                    'uploader': info.get('uploader', 'Unknown'),
                    'likes': info.get('like_count', 0),
                    'retweets': info.get('retweet_count', 0)
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
                'retries': 10,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {
                    'status': 'success',
                    'message': 'Facebook video downloaded!',
                    'title': info.get('title', 'Facebook Video'),
                    'duration': info.get('duration', 0)
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
                'retries': 10,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {
                    'status': 'success',
                    'message': 'Reddit content downloaded!',
                    'title': info.get('title', 'Reddit Post'),
                    'ups': info.get('like_count', 0),
                    'comments': info.get('comment_count', 0)
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
                'retries': 10,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {
                    'status': 'success',
                    'message': 'Vimeo video downloaded!',
                    'title': info.get('title', 'Vimeo Video'),
                    'duration': info.get('duration', 0)
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
                'retries': 10,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {
                    'status': 'success',
                    'message': 'Dailymotion video downloaded!',
                    'title': info.get('title', 'Dailymotion Video'),
                    'duration': info.get('duration', 0)
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
                'retries': 10,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {
                    'status': 'success',
                    'message': 'Twitch content downloaded!',
                    'title': info.get('title', 'Twitch Video'),
                    'uploader': info.get('uploader', 'Unknown')
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
                'retries': 10,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {
                    'status': 'success',
                    'message': 'Content downloaded!',
                    'title': info.get('title', 'Unknown'),
                    'extractor': info.get('extractor', 'Unknown')
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
    """Get video preview info"""
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
        
        if not url:
            return jsonify({'status': 'error', 'message': 'URL is required'})
        
        # Detect platform
        platform = downloader.detect_platform(url)
        
        # Download the content
        result = downloader.download_content(url, DOWNLOAD_DIR)
        
        if result['status'] == 'success':
            # If file was downloaded, handle save options
            if 'filepath' in result:
                filepath = result['filepath']
                filename = result.get('filename', os.path.basename(filepath))
                
                # Save to gallery if requested
                if save_to == 'gallery':
                    gallery_result = GallerySaver.save_to_gallery(filepath, filename)
                    result['gallery'] = gallery_result
                
                # Upload to Drive if requested
                if save_to == 'drive':
                    drive_result = drive_manager.upload_file(filepath, filename)
                    result['drive'] = drive_result
        
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
                
                # Handle save options for each file
                if result['status'] == 'success' and 'filepath' in result:
                    filepath = result['filepath']
                    filename = result.get('filename', os.path.basename(filepath))
                    
                    if save_to == 'gallery':
                        gallery_result = GallerySaver.save_to_gallery(filepath, filename)
                        result['gallery'] = gallery_result
                    
                    if save_to == 'drive':
                        drive_result = drive_manager.upload_file(filepath, filename)
                        result['drive'] = drive_result
                
                results.append(result)
                time.sleep(1)
        
        return jsonify({
            'status': 'success',
            'message': f'Processed {len(results)} URLs',
            'results': results
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# ============================================
# GOOGLE DRIVE ROUTES
# ============================================

@app.route('/drive/auth', methods=['POST'])
def drive_auth():
    """Authenticate with Google Drive"""
    result = drive_manager.authenticate()
    return jsonify(result)

@app.route('/drive/folders', methods=['GET'])
def drive_list_folders():
    """List Google Drive folders"""
    result = drive_manager.list_folders()
    return jsonify(result)

@app.route('/drive/folder/select', methods=['POST'])
def drive_select_folder():
    """Select a folder for uploads"""
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
    """Create a new folder in Google Drive"""
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
    """Upload a file to Google Drive"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        folder_id = data.get('folder_id')
        
        if not filename:
            return jsonify({'status': 'error', 'message': 'Filename required'})
        
        # Find the file in downloads directory
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
    """Save a file to gallery/system folder"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        
        if not filename:
            return jsonify({'status': 'error', 'message': 'Filename required'})
        
        # Find the file in downloads directory
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
    """Download a folder as ZIP"""
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
        else:
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
    """List supported platforms"""
    platforms = {
        'video_platforms': [
            'TikTok (via TikWM API)',
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
            'High quality downloads',
            'Metadata preservation'
        ]
    }
    return jsonify(platforms)

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print("🚀 UNIVERSAL SOCIAL MEDIA DOWNLOADER")
    print("=" * 60)
    print("📱 Supported Platforms:")
    print("  • TikTok (via TikWM API) 🎵")
    print("  • YouTube (Videos, Shorts, Playlists) ▶️")
    print("  • Instagram (Posts, Reels, Stories) 📸")
    print("  • Twitter/X 🐦")
    print("  • Facebook 📘")
    print("  • Reddit 🔴")
    print("  • Vimeo 🎬")
    print("  • Dailymotion 🎥")
    print("  • Twitch 📺")
    print("=" * 60)
    print("💾 Save Options:")
    print("  • 💾 Local Download")
    print("  • 🖼️ Gallery/System Folder")
    print("  • ☁️ Google Drive")
    print("=" * 60)
    print("🎯 Features:")
    print("  • Video Preview")
    print("  • Bulk Download")
    print("  • Auto Platform Detection")
    print("  • Metadata Extraction")
    print("=" * 60)
    print(f"📁 Downloads folder: {DOWNLOAD_DIR}")
    print(f"🌐 Server running on: http://localhost:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port)
