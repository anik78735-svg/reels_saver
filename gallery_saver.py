import os
import subprocess
import platform


class GallerySaver:
    """
    IMPORTANT: This app runs on a remote server (Render). A server process
    has NO way to write files into a user's phone/laptop Gallery/Photos app -
    the server's filesystem and the user's device filesystem are completely
    separate machines. The old version of this file copied files into the
    SERVER's own Videos/Downloads folder and reported "success" - which is
    why users never actually saw anything appear on their own device.

    The only real way to get a file onto the user's device from a web app
    is a browser-triggered HTTP download (see triggerBrowserDownload() in
    script.js, which hits GET /download-file/<filename>). Once that lands
    in the phone's own Downloads folder, most Android gallery apps index
    video files automatically.

    This class is now just a safety check that confirms the file exists
    on the server and is ready to be served - it does not claim to save
    anything on the user's device.
    """

    @staticmethod
    def save_to_gallery(file_path, filename):
        try:
            if not file_path or not os.path.exists(file_path):
                return {'status': 'error', 'message': 'File not found on server'}

            return {
                'status': 'success',
                'message': 'File is ready. It will be saved to your device via download.',
                'download_url': f'/download-file/{filename}'
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @staticmethod
    def open_file(file_path):
        """Open file with default application (server-side only - useful
        for local/desktop deployments, has no effect on a hosted server)."""
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
