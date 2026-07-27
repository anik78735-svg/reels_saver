import 'package:dio/dio.dart';
import '../models/video_info.dart';

/// Talks to YOUR backend endpoint that simply resolves a public post URL
/// to a direct, playable video file URL — no editing, no watermarking,
/// no cross-platform bulk scraping. Point [baseUrl] at your own clean
/// FastAPI/Node endpoint.
class ApiService {
  // TODO: replace with your deployed backend base URL
  static const String baseUrl = "https://your-backend.example.com";

  static final Dio _dio = Dio(
    BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 20),
      receiveTimeout: const Duration(seconds: 30),
    ),
  );

  /// Expected backend contract:
  /// POST /api/resolve   { "url": "<public post url>" }
  /// -> { "video_url": "...", "thumbnail": "...", "title": "...", "caption": "..." }
  static Future<VideoInfo> resolveVideo(String postUrl) async {
    try {
      final response = await _dio.post(
        "/api/resolve",
        data: {"url": postUrl.trim()},
      );

      if (response.statusCode == 200 && response.data != null) {
        return VideoInfo.fromJson(Map<String, dynamic>.from(response.data));
      }
      throw Exception("Server returned status ${response.statusCode}");
    } on DioException catch (e) {
      final msg = e.response?.data is Map
          ? (e.response?.data['detail'] ?? e.message)
          : e.message;
      throw Exception("Could not fetch video: $msg");
    }
  }

  static bool isSupportedUrl(String url) {
    final u = url.toLowerCase();
    return u.contains("instagram.com") ||
        u.contains("facebook.com") ||
        u.contains("fb.watch") ||
        u.contains("tiktok.com");
  }
}
