import os
import shutil
import subprocess
import platform

class GallerySaver:
    @staticmethod
    def save_to_gallery(file_path, filename):
        """Save video to system gallery/folder"""
        try:
            system = platform.system()
            
            if system == 'Windows':
                # Windows: Save to Videos folder
                videos_folder = os.path.join(os.environ['USERPROFILE'], 'Videos')
                destination = os.path.join(videos_folder, filename)
                shutil.copy2(file_path, destination)
                
                # Also save to Downloads
                downloads_folder = os.path.join(os.environ['USERPROFILE'], 'Downloads')
                dest_downloads = os.path.join(downloads_folder, filename)
                shutil.copy2(file_path, dest_downloads)
                
                return {
                    'status': 'success',
                    'message': f'Saved to Videos and Downloads folders',
                    'path': destination
                }
                
            elif system == 'Darwin':  # macOS
                # Save to Movies folder
                movies_folder = os.path.expanduser('~/Movies')
                destination = os.path.join(movies_folder, filename)
                shutil.copy2(file_path, destination)
                
                return {
                    'status': 'success',
                    'message': f'Saved to Movies folder',
                    'path': destination
                }
                
            elif system == 'Linux':
                # Save to Videos folder
                videos_folder = os.path.expanduser('~/Videos')
                if not os.path.exists(videos_folder):
                    videos_folder = os.path.expanduser('~/Downloads')
                destination = os.path.join(videos_folder, filename)
                shutil.copy2(file_path, destination)
                
                return {
                    'status': 'success',
                    'message': f'Saved to Videos folder',
                    'path': destination
                }
            
            # Android/Other
            return {
                'status': 'info',
                'message': 'File saved in downloads folder',
                'path': file_path
            }
            
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    @staticmethod
    def open_file(file_path):
        """Open file with default application"""
        try:
            system = platform.system()
            
            if system == 'Windows':
                os.startfile(file_path)
            elif system == 'Darwin':
                subprocess.run(['open', file_path])
            else:
                subprocess.run(['xdg-open', file_path])
            
            return {'status': 'success', 'message': 'File opened'}
            
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
