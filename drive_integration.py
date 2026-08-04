import os
import pickle
import json
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/drive.file']


class GoogleDriveManager:
    def __init__(self):
        self.creds = None
        self.service = None
        self.token_file = 'token.pickle'
        self.folder_file = 'selected_folder.json'
        self.selected_folder_id = None
        self.selected_folder_name = None
        self._flow = None

        # Load credentials from environment variables
        self.client_id = os.environ.get('GOOGLE_CLIENT_ID')
        self.client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
        self.project_id = os.environ.get('GOOGLE_PROJECT_ID')
        self.auth_uri = os.environ.get('GOOGLE_AUTH_URI', 'https://accounts.google.com/o/oauth2/auth')
        self.token_uri = os.environ.get('GOOGLE_TOKEN_URI', 'https://oauth2.googleapis.com/token')
        self.auth_provider_cert_url = os.environ.get('GOOGLE_AUTH_PROVIDER_CERT_URL', 'https://www.googleapis.com/oauth2/v1/certs')
        self.redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:5000/drive/callback')

        self._load_selected_folder()
        self._load_token()

    def _load_token(self):
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, 'rb') as token:
                    self.creds = pickle.load(token)
                if self.creds and self.creds.valid:
                    self.service = build('drive', 'v3', credentials=self.creds)
                elif self.creds and self.creds.expired and self.creds.refresh_token:
                    try:
                        self.creds.refresh(Request())
                        self._save_token()
                        self.service = build('drive', 'v3', credentials=self.creds)
                    except Exception as e:
                        print(f"Token refresh on load failed: {e}")
        except Exception as e:
            print(f"Could not load token: {e}")

    def _save_token(self):
        try:
            with open(self.token_file, 'wb') as token:
                pickle.dump(self.creds, token)
        except Exception as e:
            print(f"Could not save token: {e}")

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
        except Exception as e:
            print(f"Could not save selected folder: {e}")

    def get_credentials_config(self):
        """Get credentials config from environment variables"""
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
        """Build an OAuth consent URL for the browser flow.
        NOTE: flow.run_local_server() (the old approach) opens a local
        browser+server pair on the machine running the process - that only
        works when the Flask app and the browser are on the SAME machine.
        On a hosted server like Render, the server can't open a browser on
        the user's phone, so we must use the redirect-based web flow
        instead (authorization_url() + a /drive/callback route)."""
        if not self.client_id or not self.client_secret:
            return {'status': 'error', 'message': 'Google Drive credentials not configured. Please set environment variables.'}
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
        """Exchange the authorization code (from /drive/callback) for tokens."""
        try:
            if not self._flow:
                return {'status': 'error', 'message': 'No authentication flow initialized. Please start the connect process again.'}
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
        """Authenticate with Google Drive using stored/refreshed credentials,
        or return an auth_url to start the OAuth flow if not connected."""
        try:
            if not self.client_id or not self.client_secret:
                return {'status': 'error', 'message': 'Google Drive credentials not configured. Please set environment variables.'}

            if self.creds and self.creds.valid:
                self.service = build('drive', 'v3', credentials=self.creds)
                user_info = self.service.about().get(fields='user').execute()
                return {'status': 'success', 'message': 'Already connected', 'email': user_info['user']['emailAddress'], 'connected': True}

            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                    self._save_token()
                    self.service = build('drive', 'v3', credentials=self.creds)
                    user_info = self.service.about().get(fields='user').execute()
                    return {'status': 'success', 'message': 'Reconnected', 'email': user_info['user']['emailAddress'], 'connected': True}
                except Exception as e:
                    print(f"Refresh failed: {e}")

            return self.get_auth_url()
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def list_folders(self):
        """List all folders in Google Drive"""
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
        """Create a new folder in Google Drive"""
        if not self.service:
            return {'status': 'error', 'message': 'Not authenticated'}

        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }

            file = self.service.files().create(
                body=file_metadata,
                fields='id, name'
            ).execute()

            return {
                'status': 'success',
                'folder_id': file.get('id'),
                'folder_name': file.get('name')
            }

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def select_folder(self, folder_id, folder_name):
        """Select a folder for uploads. Persisted to disk so the choice
        survives page reloads and server restarts/worker respawns."""
        self.selected_folder_id = folder_id
        self.selected_folder_name = folder_name
        self._save_selected_folder()
        return {'status': 'success', 'message': f'Selected folder: {folder_name}'}

    def upload_file(self, file_path, file_name, folder_id=None):
        """Upload a file to Google Drive"""
        if not self.service:
            return {'status': 'error', 'message': 'Not authenticated. Please connect Google Drive first.'}

        if not folder_id:
            folder_id = self.selected_folder_id

        if not folder_id:
            return {'status': 'error', 'message': 'No Drive folder selected. Please select a folder first.'}

        if not file_path or not os.path.exists(file_path):
            return {'status': 'error', 'message': f'Local file not found: {file_path}'}

        try:
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }

            media = MediaFileUpload(
                file_path,
                mimetype='video/mp4',
                resumable=True
            )

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


# Create a singleton instance
drive_manager = GoogleDriveManager()
