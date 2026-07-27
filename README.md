# Reels Saver — Flutter App + Web

Pink & white themed video-link saver. Same codebase builds the Android/iOS
app and the website (`flutter build web`).

## What's included
- Splash screen
- Home screen: paste a link → fetch → choose where to save
- Save to device gallery (mobile) / browser download (web)
- Google Drive connect + save into a `TikTok` named folder
- Profile screen with Dark/Light mode toggle (persisted)

## What you need to plug in
This app expects **your own backend endpoint** — the "clean" resolver we
discussed, with no flip/mirror, no audio-swap, no watermarking, and no
bulk cross-platform scraping. It should only resolve a single public post
URL to a direct video file link.

Edit `lib/services/api_service.dart`:

```dart
static const String baseUrl = "https://your-backend.example.com";
```

### Expected backend contract

```
POST /api/resolve
Body: { "url": "https://www.instagram.com/reel/xyz" }

Response 200:
{
  "video_url": "https://.../direct-file.mp4",
  "thumbnail": "https://...jpg",   // optional
  "title": "...",                  // optional
  "caption": "..."                 // optional
}
```

## Google Drive setup
1. Create an OAuth 2.0 Client ID in Google Cloud Console (Android + Web as needed).
2. Enable the Google Drive API.
3. Add your Android package name + SHA-1 fingerprint for the Android client.
4. For web, add your authorized JavaScript origin.
5. No extra code changes needed — `google_sign_in` + `googleapis` in
   `lib/services/drive_service.dart` handle sign-in and folder creation.

## Run it

```bash
flutter pub get
flutter run                 # mobile
flutter run -d chrome        # web (dev)
flutter build apk --release  # Android APK
flutter build web             # website (build/web/)
```

## Folder structure

```
lib/
├── main.dart
├── theme/app_theme.dart          # pink & white light/dark themes
├── providers/theme_provider.dart
├── models/video_info.dart
├── services/
│   ├── api_service.dart          # calls YOUR backend
│   ├── gallery_service.dart      # mobile save / web download
│   ├── gallery_service_web.dart
│   ├── gallery_service_stub.dart
│   └── drive_service.dart        # Google Drive connect + upload
└── screens/
    ├── splash_screen.dart
    ├── home_screen.dart
    └── profile_screen.dart
```

## Note on Play Store approval
As discussed: submitting this to Google Play only goes smoothly if the
backend genuinely just resolves a link a user already has permission to
save (their own content, or content they have rights to) — not bulk
scraping or content laundering. Keep the backend to the clean contract
above and be upfront in your Privacy Policy about what the app fetches
and stores.
