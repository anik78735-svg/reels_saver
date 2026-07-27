import 'dart:io';
import 'package:dio/dio.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:gallery_saver_plus/gallery_saver.dart';
import 'package:flutter/foundation.dart' show kIsWeb;

// Web-only download helper lives in gallery_service_web.dart and is
// conditionally imported so this file compiles cleanly on mobile too.
import 'gallery_service_web.dart' if (dart.library.io) 'gallery_service_stub.dart';

class GalleryService {
  /// Downloads [videoUrl] and saves it to the device gallery (mobile),
  /// or triggers a browser download (web).
  static Future<bool> saveVideo(String videoUrl, {String? fileName}) async {
    final name = fileName ?? "video_${DateTime.now().millisecondsSinceEpoch}.mp4";

    if (kIsWeb) {
      triggerBrowserDownload(videoUrl, name);
      return true;
    }

    final granted = await _ensurePermission();
    if (!granted) {
      throw Exception("Storage/Photos permission was denied");
    }

    final dir = await getTemporaryDirectory();
    final filePath = "${dir.path}/$name";

    await Dio().download(videoUrl, filePath);
    final success = await GallerySaver.saveVideo(filePath, albumName: "ReelsSaver");

    // Clean up temp file after saving
    final file = File(filePath);
    if (await file.exists()) {
      await file.delete();
    }

    return success ?? false;
  }

  static Future<bool> _ensurePermission() async {
    if (Platform.isAndroid) {
      // Android 13+ uses granular media permissions; older uses storage.
      final videos = await Permission.videos.status;
      if (videos.isGranted) return true;

      final result = await Permission.videos.request();
      if (result.isGranted) return true;

      final storage = await Permission.storage.request();
      return storage.isGranted;
    } else if (Platform.isIOS) {
      final status = await Permission.photosAddOnly.request();
      return status.isGranted;
    }
    return true;
  }
}
