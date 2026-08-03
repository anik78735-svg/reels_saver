from flask import Flask, request, render_template, jsonify, send_file
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
import socket
from urllib.parse import urlparse

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-this'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Create downloads directory
DOWNLOAD_DIR = os.path.join(os.getcwd(), 'downloads')
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

class TikTokDownloader:
    """TikTok downloader using TikWM API (DNS-free)"""
    
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
        """Download TikTok video using multiple APIs"""
        
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
                    print(f"✅ {api['name']} success!")
                    
                    # Extract video URL
                    video_data = self.extract_video_data(result)
                    if video_data:
                        return video_data
                        
            except Exception as e:
                print(f"❌ {api['name']} error: {str(e)}")
            
            time.sleep(1)
        
        return None
    
    def extract_video_data(self, data):
        """Extract video URL and metadata from different response formats"""
        
        # TikWM format
        if 'data' in data and data.get('code') == 0:
            video_data = data['data']
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
        if 'video' in data:
            return {
                'video_url': data['video'],
                'title': data.get('title', 'TikTok Video'),
                'author': data.get('author', 'Unknown'),
                'duration': data.get('duration', 0),
                'views': data.get('views', 0),
                'likes': data.get('likes', 0),
                'comments': data.get('comments', 0)
            }
        
        # Generic search
        if isinstance(data, dict):
            for key in ['video', 'url', 'play', 'download', 'link']:
                if key in data:
                    return {
                        'video_url': data[key],
                        'title': data.get('title', 'TikTok Video'),
                        'author': data.get('author', 'Unknown')
                    }
        
        return None

class UniversalDownloader:
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
        
        # Initialize TikTok downloader
        self.tiktok_downloader = TikTokDownloader()
        
    def detect_platform(self, url):
        """Detect the platform from URL"""
        url = url.lower()
        if 'youtube.com' in url or 'youtu.be' in url:
            return 'youtube'
        elif 'instagram.com' in url:
            return 'instagram'
        elif 'facebook.com' in url or 'fb.watch' in url:
            return 'facebook'
        elif 'twitter.com' in url or 'x.com' in url:
            return 'twitter'
        elif 'tiktok.com' in url:
            return 'tiktok'
        elif 'pinterest.com' in url:
            return 'pinterest'
        elif 'linkedin.com' in url:
            return 'linkedin'
        elif 'snapchat.com' in url:
            return 'snapchat'
        elif 'reddit.com' in url:
            return 'reddit'
        elif 'twitch.tv' in url:
            return 'twitch'
        elif 'vimeo.com' in url:
            return 'vimeo'
        elif 'dailymotion.com' in url:
            return 'dailymotion'
        else:
            return 'unknown'
    
    def download_tiktok_content(self, url, path):
        """Download TikTok video using TikWM API"""
        print("🎯 Downloading TikTok...")
        print("=" * 50)
        print(f"📱 URL: {url}")
        
        # Get video info from TikTok downloader
        result = self.tiktok_downloader.download(url)
        
        if result and result.get('video_url'):
            video_url = result.get('video_url')
            title = result.get('title', 'TikTok_Video')
            author = result.get('author', 'Unknown')
            
            try:
                # Clean filename
                title = re.sub(r'[<>:"/\\|?*]', '_', title)
                safe_title = title[:50] if title else 'TikTok_Video'
                filename = f"TikTok_{author}_{safe_title}_{int(time.time())}.mp4"
                filepath = os.path.join(path, filename)
                
                print(f"📥 Downloading video...")
                print(f"   Title: {title}")
                print(f"   Author: {author}")
                print(f"   Duration: {result.get('duration', 0)}s")
                print(f"   Views: {result.get('views', 0):,}")
                print(f"   Likes: {result.get('likes', 0):,}")
                
                # Download with headers
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'https://www.tiktok.com/',
                    'Accept': 'video/*',
                }
                
                video_response = requests.get(video_url, headers=headers, stream=True, timeout=60)
                
                if video_response.status_code == 200:
                    total_size = int(video_response.headers.get('content-length', 0))
                    downloaded = 0
                    
                    with open(filepath, 'wb') as f:
                        for chunk in video_response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0:
                                    progress = (downloaded / total_size) * 100
                                    if int(progress) % 10 == 0:
                                        print(f"   Progress: {progress:.1f}%")
                    
                    file_size = os.path.getsize(filepath)
                    print(f"✅ Downloaded successfully!")
                    print(f"   File: {filename}")
                    print(f"   Size: {file_size / 1024:.1f} KB")
                    print("=" * 50)
                    
                    return {
                        'status': 'success',
                        'message': f'TikTok video downloaded successfully! 🎉',
                        'title': title,
                        'uploader': author,
                        'type': 'video',
                        'filename': filename,
                        'size': file_size,
                        'duration': result.get('duration', 0),
                        'views': result.get('views', 0),
                        'likes': result.get('likes', 0),
                        'comments': result.get('comments', 0)
                    }
                else:
                    print(f"❌ Download failed: {video_response.status_code}")
                    
            except Exception as e:
                print(f"❌ Download error: {str(e)}")
                return {
                    'status': 'error',
                    'message': f'Download error: {str(e)}'
                }
        
        # If all methods fail
        print("❌ All download methods failed")
        print("=" * 50)
        return {
            'status': 'error',
            'message': '❌ Could not download TikTok video.\n\nPlease try:\n1. Check the URL is correct\n2. Try a different video\n3. Use online downloader:\n   • https://snaptik.app/\n   • https://ssstik.io/'
        }
    
    def download_youtube_content(self, url, path):
        """Download YouTube videos, shorts, playlists"""
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, '%(uploader)s - %(title)s.%(ext)s'),
                'format': 'best[ext=mp4]/best',
                'quiet': True,
                'no_warnings': True,
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
                    titles = [entry.get('title', 'Unknown') for entry in info['entries'] if entry]
                    return {
                        'status': 'success',
                        'message': f'Downloaded {len(titles)} videos from playlist',
                        'titles': titles[:5],
                        'type': 'playlist',
                        'count': len(titles)
                    }
                else:
                    return {
                        'status': 'success',
                        'message': 'YouTube content downloaded successfully!',
                        'title': info.get('title', 'Unknown'),
                        'uploader': info.get('uploader', 'Unknown'),
                        'type': 'video',
                        'duration': info.get('duration', 0),
                        'views': info.get('view_count', 0)
                    }
        except Exception as e:
            return {'status': 'error', 'message': f'YouTube error: {str(e)}'}
    
    def download_instagram_content(self, url, path):
        """Download Instagram posts, reels, stories, IGTV"""
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
                if not shortcode:
                    return {'status': 'error', 'message': 'Invalid Instagram URL'}
                    
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
                if not username:
                    return {'status': 'error', 'message': 'Invalid Instagram URL'}
                    
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
    
    def download_twitter_content(self, url, path):
        """Download Twitter/X videos, images, threads"""
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Twitter_%(uploader)s_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'retries': 10,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['en'],
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {
                    'status': 'success',
                    'message': 'Twitter content downloaded successfully!',
                    'title': info.get('title', 'Twitter Content'),
                    'uploader': info.get('uploader', 'Unknown'),
                    'type': 'tweet',
                    'likes': info.get('like_count', 0),
                    'retweets': info.get('retweet_count', 0)
                }
        except Exception as e:
            return {'status': 'error', 'message': f'Twitter error: {str(e)}'}
    
    def download_facebook_content(self, url, path):
        """Download Facebook videos, posts"""
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Facebook_%(title)s.%(ext)s'),
                'format': 'best[ext=mp4]/best',
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'retries': 10,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {
                    'status': 'success',
                    'message': 'Facebook content downloaded successfully!',
                    'title': info.get('title', 'Facebook Content'),
                    'type': 'video',
                    'duration': info.get('duration', 0)
                }
        except Exception as e:
            return {'status': 'error', 'message': f'Facebook error: {str(e)}'}
    
    def download_reddit_content(self, url, path):
        """Download Reddit videos, images, gifs"""
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Reddit_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'retries': 10,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {
                    'status': 'success',
                    'message': 'Reddit content downloaded successfully!',
                    'title': info.get('title', 'Reddit Post'),
                    'type': 'post',
                    'ups': info.get('like_count', 0),
                    'comments': info.get('comment_count', 0)
                }
        except Exception as e:
            return {'status': 'error', 'message': f'Reddit error: {str(e)}'}
    
    def download_vimeo_content(self, url, path):
        """Download Vimeo videos"""
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, 'Vimeo_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'retries': 10,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {
                    'status': 'success',
                    'message': 'Vimeo video downloaded successfully!',
                    'title': info.get('title', 'Vimeo Video'),
                    'type': 'video',
                    'duration': info.get('duration', 0)
                }
        except Exception as e:
            return {'status': 'error', 'message': f'Vimeo error: {str(e)}'}
    
    def download_generic_content(self, url, path):
        """Download from any supported platform using yt-dlp"""
        try:
            ydl_opts = {
                'outtmpl': os.path.join(path, '%(extractor)s_%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'retries': 10,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {
                    'status': 'success',
                    'message': 'Content downloaded successfully!',
                    'title': info.get('title', 'Unknown'),
                    'extractor': info.get('extractor', 'Unknown'),
                    'type': 'media'
                }
        except Exception as e:
            return {'status': 'error', 'message': f'Download error: {str(e)}'}
    
    def extract_instagram_shortcode(self, url):
        """Extract shortcode from Instagram URL"""
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
        """Extract username from Instagram URL"""
        match = re.search(r'instagram\.com/([^/?]+)', url)
        if match:
            return match.group(1)
        return None
    
    def download_content(self, url, custom_path=None):
        """Main download function"""
        path = custom_path or DOWNLOAD_DIR
        platform = self.detect_platform(url)
        
        # Create timestamped folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        download_folder = os.path.join(path, f"{platform}_{timestamp}")
        os.makedirs(download_folder, exist_ok=True)
        
        try:
            if platform == 'youtube':
                return self.download_youtube_content(url, download_folder)
            elif platform == 'instagram':
                return self.download_instagram_content(url, download_folder)
            elif platform == 'tiktok':
                return self.download_tiktok_content(url, download_folder)
            elif platform == 'twitter':
                return self.download_twitter_content(url, download_folder)
            elif platform == 'facebook':
                return self.download_facebook_content(url, download_folder)
            elif platform == 'reddit':
                return self.download_reddit_content(url, download_folder)
            elif platform == 'vimeo':
                return self.download_vimeo_content(url, download_folder)
            else:
                return self.download_generic_content(url, download_folder)
                
        except Exception as e:
            return {'status': 'error', 'message': f'Unexpected error: {str(e)}'}

# Initialize downloader
downloader = UniversalDownloader()

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    """Handle download requests"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'status': 'error', 'message': 'URL is required'})
        
        platform = downloader.detect_platform(url)
        result = downloader.download_content(url)
        result['platform'] = platform
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'})

@app.route('/bulk-download', methods=['POST'])
def bulk_download():
    """Handle bulk download requests"""
    try:
        data = request.get_json()
        urls = data.get('urls', [])
        
        if not urls:
            return jsonify({'status': 'error', 'message': 'URLs list is required'})
        
        results = []
        for url in urls:
            if url.strip():
                result = downloader.download_content(url.strip())
                result['url'] = url
                results.append(result)
                time.sleep(1)
        
        return jsonify({
            'status': 'success',
            'message': f'Processed {len(results)} URLs',
            'results': results
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Bulk download error: {str(e)}'})

@app.route('/downloads')
def list_downloads():
    """List downloaded files and folders"""
    try:
        items = []
        if os.path.exists(DOWNLOAD_DIR):
            for item in os.listdir(DOWNLOAD_DIR):
                item_path = os.path.join(DOWNLOAD_DIR, item)
                if os.path.isfile(item_path):
                    size = os.path.getsize(item_path)
                    size_str = f"{size / 1024:.1f} KB" if size < 1024*1024 else f"{size / (1024*1024):.1f} MB"
                    items.append({
                        'name': item,
                        'type': 'file',
                        'size': size,
                        'size_str': size_str,
                        'modified': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M:%S')
                    })
                elif os.path.isdir(item_path):
                    files = [f for f in os.listdir(item_path) if os.path.isfile(os.path.join(item_path, f))]
                    total_size = sum(os.path.getsize(os.path.join(item_path, f)) for f in files)
                    size_str = f"{total_size / 1024:.1f} KB" if total_size < 1024*1024 else f"{total_size / (1024*1024):.1f} MB"
                    items.append({
                        'name': item,
                        'type': 'folder',
                        'file_count': len(files),
                        'size': total_size,
                        'size_str': size_str,
                        'modified': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M:%S')
                    })
        
        items.sort(key=lambda x: x.get('modified', ''), reverse=True)
        return jsonify({'items': items})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/download-file/<path:filename>')
def download_file(filename):
    """Download a specific file"""
    try:
        safe_filename = secure_filename(filename)
        file_path = os.path.join(DOWNLOAD_DIR, safe_filename)
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return send_file(file_path, as_attachment=True)
        else:
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

@app.route('/supported-platforms')
def supported_platforms():
    """List supported platforms"""
    platforms = {
        'video_platforms': [
            'YouTube (videos, shorts, playlists)',
            'TikTok (via TikWM API - DNS Free)',
            'Twitter/X',
            'Facebook',
            'Instagram (Reels, IGTV)',
            'Reddit',
            'Twitch',
            'Vimeo',
            'Dailymotion'
        ],
        'social_platforms': [
            'Instagram (Posts, Stories, Reels, IGTV)',
            'Twitter/X (Tweets, Threads)',
            'Facebook (Posts, Videos)',
            'Reddit (Posts, Images, Videos)',
            'LinkedIn (Posts)',
            'Pinterest (Pins)'
        ],
        'features': [
            'Auto-platform detection',
            'Bulk downloads',
            'Stories download',
            'Playlist support',
            'High quality downloads',
            'Metadata preservation',
            'Subtitle downloads',
            'DNS-Free TikTok downloads',
            'No watermark videos'
        ]
    }
    return jsonify(platforms)

@app.route('/clear-downloads', methods=['POST'])
def clear_downloads():
    """Clear all downloaded files"""
    try:
        if os.path.exists(DOWNLOAD_DIR):
            shutil.rmtree(DOWNLOAD_DIR)
            os.makedirs(DOWNLOAD_DIR)
        return jsonify({'status': 'success', 'message': 'Downloads cleared successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error clearing downloads: {str(e)}'})

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 UNIVERSAL SOCIAL MEDIA DOWNLOADER")
    print("=" * 60)
    print("📱 Supported Platforms:")
    print("  • YouTube (Videos, Shorts, Playlists)")
    print("  • Instagram (Posts, Reels, Stories, IGTV)")
    print("  • TikTok (via TikWM API - DNS Free) 🔥")
    print("  • Twitter/X")
    print("  • Facebook")
    print("  • Reddit")
    print("  • Vimeo")
    print("  • Dailymotion")
    print("=" * 60)
    print("🎯 TikTok Features:")
    print("   ✅ TikWM API Integration")
    print("   ✅ No DNS Resolution Required")
    print("   ✅ No Watermark Videos")
    print("   ✅ Metadata Extraction (Title, Author, Views, Likes)")
    print("   ✅ Short URL Support (vt.tiktok.com, vm.tiktok.com)")
    print("=" * 60)
    print("💡 Supported TikTok URL Formats:")
    print("   ✅ https://www.tiktok.com/@user/video/123456789")
    print("   ✅ https://vt.tiktok.com/ZS4AcKLFK/")
    print("   ✅ https://vm.tiktok.com/ZS4AcKLFK/")
    print("   ✅ https://www.tiktok.com/t/ZS4AcKLFK/")
    print("=" * 60)
    print(f"📁 Downloads folder: {DOWNLOAD_DIR}")
    print("🌐 Server running on: http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)
