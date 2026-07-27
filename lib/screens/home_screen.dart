import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show Clipboard, ClipboardData, HapticFeedback;
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
  final List<VideoInfo> _recent = [];

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
      setState(() {
        _videoInfo = info;
        _recent.insert(0, info);
        if (_recent.length > 5) _recent.removeLast();
      });
      HapticFeedback.lightImpact();
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
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          gradient: isDark ? AppColors.bgGradientDark : AppColors.bgGradientLight,
        ),
        child: SafeArea(
          child: CustomScrollView(
            slivers: [
              _buildHeader(context),
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildUrlCard(context),
                      const SizedBox(height: 28),
                      if (_videoInfo != null) ...[
                        _sectionTitle("Ready to save"),
                        const SizedBox(height: 12),
                        _buildPreviewCard(_videoInfo!),
                        const SizedBox(height: 28),
                      ],
                      if (_recent.length > 1) ...[
                        _sectionTitle("Recent"),
                        const SizedBox(height: 12),
                        ..._recent.skip(1).map((v) => _buildRecentTile(v)),
                      ],
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                gradient: AppColors.pinkGradient,
                borderRadius: BorderRadius.circular(14),
                boxShadow: AppShadows.button,
              ),
              child: const Icon(Icons.video_collection_rounded,
                  color: Colors.white, size: 24),
            ),
            const SizedBox(width: 12),
            const Expanded(
              child: Text(
                "Reels Saver",
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
              ),
            ),
            _CircleIconButton(
              icon: Icons.person_outline_rounded,
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const ProfileScreen()),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _sectionTitle(String text) {
    return Text(
      text,
      style: TextStyle(
        fontSize: 13,
        fontWeight: FontWeight.w700,
        color: AppColors.primaryPink,
        letterSpacing: 0.3,
      ),
    );
  }

  Widget _buildUrlCard(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: Theme.of(context).cardTheme.color,
        borderRadius: BorderRadius.circular(26),
        boxShadow: AppShadows.soft,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            "Paste a video link",
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 6),
          Text(
            "Instagram, Facebook, or TikTok — we'll fetch it for you.",
            style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
          ),
          const SizedBox(height: 20),
          TextField(
            controller: _urlController,
            keyboardType: TextInputType.url,
            style: const TextStyle(fontSize: 14),
            decoration: InputDecoration(
              hintText: "https://www.instagram.com/reel/...",
              prefixIcon: const Icon(Icons.link_rounded, color: AppColors.primaryPink),
              suffixIcon: IconButton(
                icon: const Icon(Icons.content_paste_rounded, size: 20, color: AppColors.deepPink),
                onPressed: () async {
                  final data = await Clipboard.getData('text/plain');
                  if (data?.text != null) {
                    _urlController.text = data!.text!;
                    setState(() => _errorText = null);
                  }
                },
              ),
            ),
          ),
          AnimatedSize(
            duration: const Duration(milliseconds: 200),
            child: _errorText != null
                ? Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: Row(
                      children: [
                        const Icon(Icons.error_outline_rounded, size: 16, color: AppColors.error),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(_errorText!,
                              style: const TextStyle(color: AppColors.error, fontSize: 12.5)),
                        ),
                      ],
                    ),
                  )
                : const SizedBox.shrink(),
          ),
          const SizedBox(height: 18),
          SizedBox(
            width: double.infinity,
            height: 54,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: _loading ? null : AppColors.pinkGradient,
                color: _loading ? Colors.grey.shade300 : null,
                borderRadius: BorderRadius.circular(18),
                boxShadow: _loading ? [] : AppShadows.button,
              ),
              child: Material(
                color: Colors.transparent,
                child: InkWell(
                  borderRadius: BorderRadius.circular(18),
                  onTap: _loading ? null : _fetchVideo,
                  child: Center(
                    child: _loading
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(
                              strokeWidth: 2.4,
                              color: Colors.white,
                            ),
                          )
                        : const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(Icons.search_rounded, color: Colors.white, size: 20),
                              SizedBox(width: 8),
                              Text(
                                "Fetch Video",
                                style: TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 16,
                                ),
                              ),
                            ],
                          ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPreviewCard(VideoInfo info) {
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).cardTheme.color,
        borderRadius: BorderRadius.circular(24),
        boxShadow: AppShadows.soft,
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (info.thumbnail != null)
            AspectRatio(
              aspectRatio: 16 / 9,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Image.network(
                    info.thumbnail!,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => Container(color: AppColors.softPink),
                  ),
                  Positioned(
                    bottom: 0,
                    left: 0,
                    right: 0,
                    child: Container(
                      height: 60,
                      decoration: const BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [Colors.transparent, Colors.black45],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  info.title ?? info.caption ?? "Video ready to save",
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
                ),
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: () => _showDownloadOptions(info),
                    icon: const Icon(Icons.file_download_outlined, size: 18),
                    label: const Text("Download Options"),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRecentTile(VideoInfo info) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: Theme.of(context).cardTheme.color,
        borderRadius: BorderRadius.circular(18),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        leading: ClipRRect(
          borderRadius: BorderRadius.circular(10),
          child: info.thumbnail != null
              ? Image.network(info.thumbnail!, width: 44, height: 44, fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => _fallbackThumb())
              : _fallbackThumb(),
        ),
        title: Text(
          info.title ?? info.caption ?? "Video",
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
        ),
        trailing: IconButton(
          icon: const Icon(Icons.file_download_outlined, color: AppColors.primaryPink, size: 20),
          onPressed: () => _showDownloadOptions(info),
        ),
      ),
    );
  }

  Widget _fallbackThumb() {
    return Container(
      width: 44,
      height: 44,
      color: AppColors.lightPink,
      child: const Icon(Icons.play_arrow_rounded, color: AppColors.primaryPink),
    );
  }
}

class _CircleIconButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  const _CircleIconButton({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Theme.of(context).cardTheme.color,
      shape: const CircleBorder(),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Icon(icon, color: AppColors.primaryPink, size: 22),
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
  bool _success = false;
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
      HapticFeedback.mediumImpact();
      setState(() {
        _success = true;
        _statusMessage = kIsWeb
            ? "Download started in your browser"
            : "Saved to your gallery";
      });
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
      HapticFeedback.mediumImpact();
      setState(() {
        _success = true;
        _statusMessage = 'Saved to Drive → "TikTok" folder';
      });
    } catch (e) {
      setState(() => _statusMessage = "Failed: ${e.toString().replaceFirst("Exception: ", "")}");
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 16,
        bottom: MediaQuery.of(context).viewInsets.bottom + 28,
      ),
      decoration: BoxDecoration(
        color: isDark ? AppColors.darkCard : AppColors.white,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(30)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.15),
            blurRadius: 30,
            offset: const Offset(0, -8),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 42,
              height: 5,
              margin: const EdgeInsets.only(bottom: 20),
              decoration: BoxDecoration(
                color: Colors.grey.withOpacity(0.3),
                borderRadius: BorderRadius.circular(4),
              ),
            ),
          ),
          Row(
            children: [
              Container(
                width: 34,
                height: 34,
                decoration: BoxDecoration(
                  gradient: AppColors.pinkGradient,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.save_alt_rounded, color: Colors.white, size: 18),
              ),
              const SizedBox(width: 12),
              const Text(
                "Choose how to save",
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
              ),
            ],
          ),
          const SizedBox(height: 20),

          _OptionTile(
            icon: Icons.download_rounded,
            gradient: AppColors.pinkGradient,
            title: kIsWeb ? "Download to device" : "Save to Gallery",
            subtitle: "Direct download, no account needed",
            onTap: _busy ? null : _saveToGallery,
          ),
          const SizedBox(height: 12),

          if (_checkingConnection)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 16),
              child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
            )
          else if (_driveConnected)
            _OptionTile(
              icon: Icons.add_to_drive_rounded,
              gradient: const LinearGradient(colors: [Color(0xFF34A853), Color(0xFF1E7E34)]),
              title: "Save to Drive",
              subtitle: 'Goes into your "TikTok" folder',
              onTap: _busy ? null : _saveToDrive,
            )
          else
            _OptionTile(
              icon: Icons.link_rounded,
              gradient: LinearGradient(colors: [Colors.grey.shade500, Colors.grey.shade700]),
              title: "Connect Google Drive",
              subtitle: "Connect once to enable Drive saving",
              onTap: _busy ? null : _connectDrive,
            ),

          AnimatedSize(
            duration: const Duration(milliseconds: 200),
            child: _busy
                ? const Padding(
                    padding: EdgeInsets.only(top: 20),
                    child: Center(child: CircularProgressIndicator()),
                  )
                : _statusMessage != null
                    ? Padding(
                        padding: const EdgeInsets.only(top: 18),
                        child: Row(
                          children: [
                            Icon(
                              _success ? Icons.check_circle_rounded : Icons.error_outline_rounded,
                              color: _success ? AppColors.success : AppColors.error,
                              size: 18,
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                _statusMessage!,
                                style: TextStyle(
                                  color: _success ? AppColors.success : AppColors.error,
                                  fontWeight: FontWeight.w600,
                                  fontSize: 13.5,
                                ),
                              ),
                            ),
                          ],
                        ),
                      )
                    : const SizedBox.shrink(),
          ),
        ],
      ),
    );
  }
}

class _OptionTile extends StatelessWidget {
  final IconData icon;
  final Gradient gradient;
  final String title;
  final String subtitle;
  final VoidCallback? onTap;

  const _OptionTile({
    required this.icon,
    required this.gradient,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Material(
      color: isDark ? AppColors.darkCard2 : AppColors.softPink,
      borderRadius: BorderRadius.circular(18),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(gradient: gradient, borderRadius: BorderRadius.circular(13)),
                child: Icon(icon, color: Colors.white, size: 20),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14.5)),
                    const SizedBox(height: 2),
                    Text(subtitle,
                        style: TextStyle(fontSize: 12, color: Colors.grey.shade500)),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right_rounded, color: AppColors.primaryPink),
            ],
          ),
        ),
      ),
    );
  }
}
