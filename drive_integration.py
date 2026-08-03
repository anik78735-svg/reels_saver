import os
import pickle
import json
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
        self.credentials_file = 'credentials.json'
        self.selected_folder_id = None
        self.selected_folder_name = None
        
    def authenticate(self):
        """Authenticate with Google Drive"""
        try:
            # Load existing token
            if os.path.exists(self.token_file):
                with open(self.token_file, 'rb') as token:
                    self.creds = pickle.load(token)
            
            # If no valid credentials, get new ones
            if not self.creds or not self.creds.valid:
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                else:
                    if not os.path.exists(self.credentials_file):
                        return {
                            'status': 'error',
                            'message': 'credentials.json file not found. Please set up Google Drive API.'
                        }
                    
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_file, SCOPES)
                    self.creds = flow.run_local_server(port=0)
                
                # Save credentials
                with open(self.token_file, 'wb') as token:
                    pickle.dump(self.creds, token)
            
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
