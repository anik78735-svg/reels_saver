import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show Clipboard, ClipboardData;
import 'package:flutter/foundation.dart' show kIsWeb;
import '../models/video_info.dart';
import '../services/api_service.dart';
import '../services/gallery_service.dart';
import '../services/drive_service.dart';
import '../theme/app_theme.dart';
import 'profile_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final TextEditingController _urlController = TextEditingController();
  bool _loading = false;
  VideoInfo? _videoInfo;
  String? _errorText;

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _fetchVideo() async {
    final url = _urlController.text.trim();
    FocusScope.of(context).unfocus();

    if (url.isEmpty) {
      setState(() => _errorText = "Please paste a video link first");
      return;
    }
    if (!ApiService.isSupportedUrl(url)) {
      setState(() => _errorText = "Paste a valid Instagram, Facebook, or TikTok link");
      return;
    }

    setState(() {
      _loading = true;
      _errorText = null;
      _videoInfo = null;
    });

    try {
      final info = await ApiService.resolveVideo(url);
      setState(() => _videoInfo = info);
      if (mounted) _showDownloadOptions(info);
    } catch (e) {
      setState(() => _errorText = e.toString().replaceFirst("Exception: ", ""));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _showDownloadOptions(VideoInfo info) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (ctx) => _DownloadOptionsSheet(videoInfo: info),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Reels Saver"),
        actions: [
          IconButton(
            icon: const Icon(Icons.person_outline),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const ProfileScreen()),
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 12),
              Text(
                "Paste a video link",
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: AppColors.deepPink,
                    ),
              ),
              const SizedBox(height: 6),
              Text(
                "Instagram, Facebook, or TikTok — we'll fetch it for you.",
                style: TextStyle(color: Colors.grey.shade600),
              ),
              const SizedBox(height: 24),
              TextField(
                controller: _urlController,
                keyboardType: TextInputType.url,
                decoration: InputDecoration(
                  hintText: "https://www.instagram.com/reel/...",
                  prefixIcon: const Icon(Icons.link, color: AppColors.primaryPink),
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.paste, color: AppColors.deepPink),
                    onPressed: () async {
                      final data = await Clipboard.getData('text/plain');
                      if (data?.text != null) {
                        _urlController.text = data!.text!;
                      }
                    },
                  ),
                ),
              ),
              if (_errorText != null) ...[
                const SizedBox(height: 10),
                Text(_errorText!, style: const TextStyle(color: Colors.red)),
              ],
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: _loading ? null : _fetchVideo,
                  icon: _loading
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Icon(Icons.search),
                  label: Text(_loading ? "Fetching..." : "Fetch Video"),
                ),
              ),
              const SizedBox(height: 32),
              if (_videoInfo != null) _buildPreviewCard(_videoInfo!),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPreviewCard(VideoInfo info) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (info.thumbnail != null)
              ClipRRect(
                borderRadius: BorderRadius.circular(14),
                child: Image.network(
                  info.thumbnail!,
                  height: 180,
                  width: double.infinity,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => const SizedBox.shrink(),
                ),
              ),
            const SizedBox(height: 12),
            Text(
              info.title ?? info.caption ?? "Video ready",
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () => _showDownloadOptions(info),
                icon: const Icon(Icons.file_download_outlined, color: AppColors.deepPink),
                label: const Text("Download Options",
                    style: TextStyle(color: AppColors.deepPink)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Bottom sheet: always offers direct gallery/browser download, and
/// separately offers Drive save — either straight to the "TikTok"
/// folder if already connected, or a Connect button if not.
class _DownloadOptionsSheet extends StatefulWidget {
  final VideoInfo videoInfo;
  const _DownloadOptionsSheet({required this.videoInfo});

  @override
  State<_DownloadOptionsSheet> createState() => _DownloadOptionsSheetState();
}

class _DownloadOptionsSheetState extends State<_DownloadOptionsSheet> {
  bool _driveConnected = false;
  bool _checkingConnection = true;
  bool _busy = false;
  String? _statusMessage;

  @override
  void initState() {
    super.initState();
    _checkDrive();
  }

  Future<void> _checkDrive() async {
    final connected = await DriveService.isConnected();
    if (mounted) {
      setState(() {
        _driveConnected = connected;
        _checkingConnection = false;
      });
    }
  }

  Future<void> _saveToGallery() async {
    setState(() {
      _busy = true;
      _statusMessage = null;
    });
    try {
      await GalleryService.saveVideo(widget.videoInfo.videoUrl);
      setState(() => _statusMessage = kIsWeb
          ? "Download started in your browser"
          : "Saved to your gallery ✓");
    } catch (e) {
      setState(() => _statusMessage = "Failed: ${e.toString().replaceFirst("Exception: ", "")}");
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _connectDrive() async {
    setState(() => _busy = true);
    final ok = await DriveService.connect();
    if (mounted) {
      setState(() {
        _driveConnected = ok;
        _busy = false;
        _statusMessage = ok ? null : "Could not connect to Google Drive";
      });
    }
  }

  Future<void> _saveToDrive() async {
    setState(() {
      _busy = true;
      _statusMessage = null;
    });
    try {
      await DriveService.uploadToFolder(
        widget.videoInfo.videoUrl,
        folderName: DriveService.defaultFolderName,
      );
      setState(() => _statusMessage = "Saved to Drive → \"TikTok\" folder ✓");
    } catch (e) {
      setState(() => _statusMessage = "Failed: ${e.toString().replaceFirst("Exception: ", "")}");
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 24,
      ),
      decoration: const BoxDecoration(
        color: AppColors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.grey.shade300,
                borderRadius: BorderRadius.circular(4),
              ),
            ),
          ),
          const SizedBox(height: 18),
          const Text(
            "Choose how to save",
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.deepPink),
          ),
          const SizedBox(height: 16),

          // Always-available direct download option
          _OptionTile(
            icon: Icons.download_rounded,
            iconBg: AppColors.primaryPink,
            title: kIsWeb ? "Download to device" : "Save to Gallery",
            subtitle: "Direct download, no account needed",
            onTap: _busy ? null : _saveToGallery,
          ),
          const SizedBox(height: 12),

          // Drive option — behavior depends on connection state
          if (_checkingConnection)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
            )
          else if (_driveConnected)
            _OptionTile(
              icon: Icons.add_to_drive,
              iconBg: AppColors.deepPink,
              title: "Save to Drive",
              subtitle: 'Goes into your "TikTok" folder',
              onTap: _busy ? null : _saveToDrive,
            )
          else
            _OptionTile(
              icon: Icons.link,
              iconBg: Colors.grey.shade500,
              title: "Connect Google Drive",
              subtitle: "Connect once to enable Drive saving",
              onTap: _busy ? null : _connectDrive,
            ),

          if (_busy) ...[
            const SizedBox(height: 16),
            const Center(child: CircularProgressIndicator()),
          ],

          if (_statusMessage != null) ...[
            const SizedBox(height: 16),
            Text(
              _statusMessage!,
              style: TextStyle(
                color: _statusMessage!.startsWith("Failed")
                    ? Colors.red
                    : Colors.green.shade700,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _OptionTile extends StatelessWidget {
  final IconData icon;
  final Color iconBg;
  final String title;
  final String subtitle;
  final VoidCallback? onTap;

  const _OptionTile({
    required this.icon,
    required this.iconBg,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.softPink,
      borderRadius: BorderRadius.circular(18),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              CircleAvatar(
                backgroundColor: iconBg,
                child: Icon(icon, color: Colors.white, size: 20),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
                    Text(subtitle,
                        style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: AppColors.deepPink),
            ],
          ),
        ),
      ),
    );
  }
}

