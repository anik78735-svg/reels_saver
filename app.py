import os
import pickle
import json
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
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
        self.selected_folder_id = None
        self.selected_folder_name = None
        self.auth_code = None
        
        # Load credentials from environment variables
        self.client_id = os.environ.get('GOOGLE_CLIENT_ID')
        self.client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
        self.project_id = os.environ.get('GOOGLE_PROJECT_ID')
        self.auth_uri = os.environ.get('GOOGLE_AUTH_URI')
        self.token_uri = os.environ.get('GOOGLE_TOKEN_URI')
        self.auth_provider_cert_url = os.environ.get('GOOGLE_AUTH_PROVIDER_CERT_URL')
        self.redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:5000/auth/google/callback')
        
        # Try to load existing token
        self._load_token()
    
    def _load_token(self):
        """Load existing token from file"""
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, 'rb') as token:
                    self.creds = pickle.load(token)
                return True
        except Exception as e:
            print(f"⚠️ Could not load token: {e}")
        return False
    
    def _save_token(self):
        """Save token to file"""
        try:
            with open(self.token_file, 'wb') as token:
                pickle.dump(self.creds, token)
            return True
        except Exception as e:
            print(f"⚠️ Could not save token: {e}")
        return False
    
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
        """Get authentication URL for user to visit"""
        if not self.client_id or not self.client_secret:
            return {
                'status': 'error',
                'message': 'Google Drive credentials not configured. Please set environment variables.'
            }
        
        try:
            config = self.get_credentials_config()
            flow = InstalledAppFlow.from_client_config(
                config,
                SCOPES
            )
            
            # Generate auth URL
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            
            # Store flow for later use
            self._flow = flow
            
            return {
                'status': 'success',
                'auth_url': auth_url,
                'message': 'Please visit the URL to authorize the application'
            }
            
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def authenticate_with_code(self, auth_code):
        """Authenticate using authorization code"""
        try:
            if not hasattr(self, '_flow'):
                return {'status': 'error', 'message': 'No authentication flow initialized. Please call get_auth_url first.'}
            
            # Exchange code for credentials
            self._flow.fetch_token(code=auth_code)
            self.creds = self._flow.credentials
            
            # Save token
            self._save_token()
            
            # Build service
            self.service = build('drive', 'v3', credentials=self.creds)
            
            # Get user info
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
        """Authenticate with Google Drive - tries existing token first"""
        try:
            # Check if we already have valid credentials
            if self.creds and self.creds.valid:
                # Refresh if expired
                if self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                    self._save_token()
                
                # Build service
                self.service = build('drive', 'v3', credentials=self.creds)
                
                # Get user info
                user_info = self.service.about().get(fields='user').execute()
                user_email = user_info['user']['emailAddress']
                
                return {
                    'status': 'success',
                    'message': f'Already connected to {user_email}',
                    'email': user_email,
                    'connected': True
                }
            
            # Check if we have stored credentials
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
                    # Continue to get new auth
            
            # Need new authentication
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
            return {
                'status': 'success',
                'folders': folders
            }
            
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
        """Select a folder for uploads"""
        self.selected_folder_id = folder_id
        self.selected_folder_name = folder_name
        return {
            'status': 'success',
            'message': f'Selected folder: {folder_name}'
        }
    
    def upload_file(self, file_path, file_name, folder_id=None):
        """Upload a file to Google Drive"""
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
    
    def get_upload_url(self, file_id):
        """Get shareable link for uploaded file"""
        if not self.service:
            return None
        
        try:
            file = self.service.files().get(
                fileId=file_id,
                fields='webViewLink'
            ).execute()
            
            return file.get('webViewLink')
            
        except Exception:
            return None

# Create a singleton instance
drive_manager = GoogleDriveManager()
