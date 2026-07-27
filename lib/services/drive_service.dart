import 'dart:io';
import 'package:dio/dio.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:googleapis/drive/v3.dart' as drive;
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

/// Wraps a GoogleSignIn authenticated client so it can be used
/// directly with the googleapis Drive client.
class _GoogleAuthClient extends http.BaseClient {
  final Map<String, String> _headers;
  final http.Client _client = http.Client();
  _GoogleAuthClient(this._headers);

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    request.headers.addAll(_headers);
    return _client.send(request);
  }
}

class DriveService {
  static const String defaultFolderName = "TikTok";

  static final GoogleSignIn _googleSignIn = GoogleSignIn(
    scopes: [drive.DriveApi.driveFileScope],
  );

  static GoogleSignInAccount? _cachedAccount;

  static Future<bool> isConnected() async {
    final signedIn = await _googleSignIn.isSignedIn();
    if (signedIn) {
      _cachedAccount ??= await _googleSignIn.signInSilently();
    }
    return signedIn;
  }

  static Future<bool> connect() async {
    try {
      final account = await _googleSignIn.signIn();
      _cachedAccount = account;
      return account != null;
    } catch (e) {
      return false;
    }
  }

  static Future<void> disconnect() async {
    await _googleSignIn.disconnect();
    _cachedAccount = null;
  }

  static Future<drive.DriveApi> _getDriveApi() async {
    final account = _cachedAccount ?? await _googleSignIn.signInSilently();
    if (account == null) {
      throw Exception("Google Drive is not connected.");
    }
    final authHeaders = await account.authHeaders;
    final client = _GoogleAuthClient(authHeaders);
    return drive.DriveApi(client);
  }

  static Future<String> _getOrCreateFolder(
    drive.DriveApi api,
    String folderName,
  ) async {
    final query =
        "mimeType='application/vnd.google-apps.folder' and name='$folderName' and trashed=false";
    final result = await api.files.list(q: query, $fields: "files(id,name)");

    if (result.files != null && result.files!.isNotEmpty) {
      return result.files!.first.id!;
    }

    final folder = drive.File()
      ..name = folderName
      ..mimeType = 'application/vnd.google-apps.folder';
    final created = await api.files.create(folder, $fields: "id");
    return created.id!;
  }

  /// Downloads [videoUrl] to a temp file, then uploads it into a Drive
  /// folder named [folderName] (defaults to "TikTok" per app convention).
  static Future<void> uploadToFolder(
    String videoUrl, {
    String folderName = defaultFolderName,
    String? fileName,
  }) async {
    final api = await _getDriveApi();
    final targetFolderId = await _getOrCreateFolder(api, folderName);

    final dir = await getTemporaryDirectory();
    final name = fileName ?? "video_${DateTime.now().millisecondsSinceEpoch}.mp4";
    final filePath = "${dir.path}/$name";

    await Dio().download(videoUrl, filePath);
    final file = File(filePath);

    final driveFile = drive.File()
      ..name = name
      ..parents = [targetFolderId];

    await api.files.create(
      driveFile,
      uploadMedia: drive.Media(file.openRead(), await file.length()),
    );

    if (await file.exists()) {
      await file.delete();
    }
  }

  static String? get connectedEmail => _cachedAccount?.email;
}
