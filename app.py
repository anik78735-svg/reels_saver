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
app.config['SECRET_KEY'] = 'your-secret-key-here-change-this'
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
            }
        ]
    
    def download(self, url):
        for api in self.apis:
            try:
                if api['method'] == 'GET':
                    params = api.get('params', {})
                    params['url'] = url
                    response = requests.get(api['url'], params=params, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('code') == 0:
                        video_data = result['data']
                        return {
                            'video_url': video_data.get('play', ''),
                            'title': video_data.get('title', 'TikTok Video'),
                            'author': video_data.get('author', {}).get('unique_id', 'Unknown'),
                            'duration': video_data.get('duration', 0),
                            'views': video_data.get('play_count', 0),
                            'likes': video_data.get('digg_count', 0),
                            'comments': video_data.get('comment_count', 0)
                        }
            except Exception as e:
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
        elif 'facebook.com' in url:
            return 'facebook'
        elif 'reddit.com' in url:
            return 'reddit'
        elif 'vimeo.com' in url:
            return 'vimeo'
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
        else:
            return self.download_generic(url, download_folder)
    
    def download_tiktok(self, url, path):
        result = tiktok_downloader.download(url)
        if result and result.get('video_url'):
            return self._download_video(result['video_url'], path, 
                                       f"TikTok_{result['author']}_{result['title']}", result)
        return {'status': 'error', 'message': 'Failed to download TikTok video'}
    
    def _download_video(self, video_url, path, base_name, metadata=None):
        try:
            filename = f"{base_name[:50]}_{int(time.time())}.mp4"
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            filepath = os.path.join(path, filename)
            
            response = requests.get(video_url, stream=True, timeout=60)
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                return {
                    'status': 'success',
                    'message': 'Video downloaded successfully!',
                    'filename': filename,
                    'filepath': filepath,
                    'metadata': metadata or {}
                }
            
            return {'status': 'error', 'message': 'Download failed'}
            
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def download_youtube(self, url, path):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, '%(uploader)s - %(title)s.%(ext)s'),
                'format': 'best[ext=mp4]/best',
                'quiet': True,
                'ignoreerrors': True,
                'retries': 10
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {
                    'status': 'success',
                    'message': 'YouTube video downloaded!',
                    'title': info.get('title', 'Unknown'),
                    'uploader': info.get('uploader', 'Unknown')
                }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def download_instagram(self, url, path):
        try:
            loader = instaloader.Instaloader(
                dirname_pattern=path,
                filename_pattern='{profile}_{mediaid}',
                download_videos=True,
                download_comments=False,
                save_metadata=True
            )
            
            shortcode = re.search(r'/p/([^/?]+)', url) or re.search(r'/reel/([^/?]+)', url)
            if shortcode:
                post = instaloader.Post.from_shortcode(loader.context, shortcode.group(1))
                loader.download_post(post, target=post.owner_username)
                return {
                    'status': 'success',
                    'message': 'Instagram content downloaded!'
                }
            return {'status': 'error', 'message': 'Invalid Instagram URL'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def download_twitter(self, url, path):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Twitter_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'ignoreerrors': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {'status': 'success', 'message': 'Twitter content downloaded!'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def download_facebook(self, url, path):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Facebook_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'ignoreerrors': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {'status': 'success', 'message': 'Facebook video downloaded!'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def download_reddit(self, url, path):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Reddit_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'ignoreerrors': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {'status': 'success', 'message': 'Reddit content downloaded!'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def download_vimeo(self, url, path):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Vimeo_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'ignoreerrors': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {'status': 'success', 'message': 'Vimeo video downloaded!'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def download_generic(self, url, path):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, '%(extractor)s_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'ignoreerrors': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {'status': 'success', 'message': 'Content downloaded!'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

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
        save_to = data.get('save_to', 'local')  # local, gallery, drive
        
        if not url:
            return jsonify({'status': 'error', 'message': 'URL is required'})
        
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
        
        result['platform'] = downloader.detect_platform(url)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/bulk-download', methods=['POST'])
def bulk_download():
    try:
        data = request.get_json()
        urls = data.get('urls', [])
        
        if not urls:
            return jsonify({'status': 'error', 'message': 'URLs list is required'})
        
        results = []
        for url in urls:
            if url.strip():
                result = downloader.download_content(url.strip(), DOWNLOAD_DIR)
                result['url'] = url
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
                    items.append({
                        'name': item,
                        'type': 'file',
                        'size': os.path.getsize(item_path),
                        'modified': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M:%S')
                    })
                elif os.path.isdir(item_path):
                    files = [f for f in os.listdir(item_path) if os.path.isfile(os.path.join(item_path, f))]
                    items.append({
                        'name': item,
                        'type': 'folder',
                        'file_count': len(files),
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

@app.route('/clear-downloads', methods=['POST'])
def clear_downloads():
    try:
        if os.path.exists(DOWNLOAD_DIR):
            shutil.rmtree(DOWNLOAD_DIR)
            os.makedirs(DOWNLOAD_DIR)
        return jsonify({'status': 'success', 'message': 'Downloads cleared'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

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
    print("  • TikTok (via TikWM API)")
    print("  • YouTube (Videos, Shorts, Playlists)")
    print("  • Instagram (Posts, Reels, Stories)")
    print("  • Twitter/X")
    print("  • Facebook")
    print("  • Reddit")
    print("  • Vimeo")
    print("=" * 60)
    print("💾 Save Options:")
    print("  • Local Download")
    print("  • Gallery/System Folder")
    print("  • Google Drive")
    print("=" * 60)
    print(f"📁 Downloads folder: {DOWNLOAD_DIR}")
    print(f"🌐 Server running on: http://localhost:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port)
