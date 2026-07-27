import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/theme_provider.dart';
import '../services/drive_service.dart';
import '../theme/app_theme.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  bool _driveConnected = false;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _refreshDriveStatus();
  }

  Future<void> _refreshDriveStatus() async {
    final connected = await DriveService.isConnected();
    if (mounted) {
      setState(() {
        _driveConnected = connected;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final themeProvider = context.watch<ThemeProvider>();
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          gradient: isDark ? AppColors.bgGradientDark : AppColors.bgGradientLight,
        ),
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
            children: [
              Row(
                children: [
                  IconButton(
                    icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                  const Text("Profile",
                      style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
                ],
              ),
              const SizedBox(height: 16),

              // Profile header card
              Container(
                padding: const EdgeInsets.all(22),
                decoration: BoxDecoration(
                  gradient: AppColors.pinkGradient,
                  borderRadius: BorderRadius.circular(26),
                  boxShadow: AppShadows.button,
                ),
                child: Row(
                  children: [
                    Container(
                      width: 60,
                      height: 60,
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.2),
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 2),
                      ),
                      child: const Icon(Icons.person_rounded, color: Colors.white, size: 30),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text("Reels Saver User",
                              style: TextStyle(
                                  color: Colors.white, fontWeight: FontWeight.w800, fontSize: 16)),
                          const SizedBox(height: 4),
                          Text(
                            _loading
                                ? "Checking Drive status..."
                                : (_driveConnected
                                    ? (DriveService.connectedEmail ?? "Drive connected")
                                    : "Drive not connected"),
                            style: TextStyle(color: Colors.white.withOpacity(0.85), fontSize: 12.5),
                          ),
                        ],
                      ),
                    ),
                    Icon(
                      _driveConnected ? Icons.check_circle_rounded : Icons.circle_outlined,
                      color: Colors.white,
                      size: 22,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 28),

              _SectionLabel("Appearance"),
              _GroupCard(
                children: [
                  SwitchListTile(
                    title: const Text("Dark Mode", style: TextStyle(fontWeight: FontWeight.w600)),
                    subtitle: const Text("Switch between light and dark theme",
                        style: TextStyle(fontSize: 12)),
                    value: themeProvider.isDark,
                    onChanged: (val) => themeProvider.toggleTheme(val),
                    secondary: _IconBadge(
                      icon: themeProvider.isDark ? Icons.dark_mode_rounded : Icons.light_mode_rounded,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 24),

              _SectionLabel("Storage"),
              _GroupCard(
                children: [
                  ListTile(
                    leading: const _IconBadge(icon: Icons.add_to_drive_rounded),
                    title: const Text("Google Drive", style: TextStyle(fontWeight: FontWeight.w600)),
                    subtitle: Text(
                      _driveConnected ? 'Connected — saving into "TikTok" folder' : "Not connected",
                      style: const TextStyle(fontSize: 12),
                    ),
                    trailing: _loading
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : _PillButton(
                            label: _driveConnected ? "Disconnect" : "Connect",
                            filled: !_driveConnected,
                            onTap: () async {
                              setState(() => _loading = true);
                              if (_driveConnected) {
                                await DriveService.disconnect();
                              } else {
                                await DriveService.connect();
                              }
                              await _refreshDriveStatus();
                            },
                          ),
                  ),
                ],
              ),
              const SizedBox(height: 24),

              _SectionLabel("About"),
              _GroupCard(
                children: [
                  ListTile(
                    leading: const _IconBadge(icon: Icons.info_outline_rounded),
                    title: const Text("Version", style: TextStyle(fontWeight: FontWeight.w600)),
                    subtitle: const Text("1.0.0", style: TextStyle(fontSize: 12)),
                  ),
                  Divider(height: 1, indent: 68, endIndent: 16, color: Theme.of(context).dividerColor),
                  ListTile(
                    leading: const _IconBadge(icon: Icons.privacy_tip_outlined),
                    title: const Text("Privacy Policy", style: TextStyle(fontWeight: FontWeight.w600)),
                    trailing: const Icon(Icons.chevron_right_rounded, size: 20),
                    onTap: () {},
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _GroupCard extends StatelessWidget {
  final List<Widget> children;
  const _GroupCard({required this.children});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).cardTheme.color,
        borderRadius: BorderRadius.circular(22),
        boxShadow: AppShadows.soft,
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(children: children),
    );
  }
}

class _IconBadge extends StatelessWidget {
  final IconData icon;
  const _IconBadge({required this.icon});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 40,
      height: 40,
      decoration: BoxDecoration(
        gradient: AppColors.pinkGradient,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Icon(icon, color: Colors.white, size: 20),
    );
  }
}

class _PillButton extends StatelessWidget {
  final String label;
  final bool filled;
  final VoidCallback onTap;
  const _PillButton({required this.label, required this.filled, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: filled ? AppColors.primaryPink : Colors.transparent,
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: filled
              ? null
              : BoxDecoration(
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: AppColors.error.withOpacity(0.4)),
                ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w700,
              color: filled ? Colors.white : AppColors.error,
            ),
          ),
        ),
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  final String text;
  const _SectionLabel(this.text);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 6, bottom: 10),
      child: Text(
        text,
        style: const TextStyle(
          fontWeight: FontWeight.w700,
          color: AppColors.primaryPink,
          fontSize: 12.5,
          letterSpacing: 0.4,
        ),
      ),
    );
  }
}
