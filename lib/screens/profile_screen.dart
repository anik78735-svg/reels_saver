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

    return Scaffold(
      appBar: AppBar(title: const Text("Profile")),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Row(
                children: [
                  const CircleAvatar(
                    radius: 30,
                    backgroundColor: AppColors.primaryPink,
                    child: Icon(Icons.person, color: Colors.white, size: 30),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text("Reels Saver User",
                            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                        Text(
                          _loading
                              ? "Checking Drive status..."
                              : (_driveConnected
                                  ? (DriveService.connectedEmail ?? "Drive connected")
                                  : "Drive not connected"),
                          style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),

          _SectionLabel("Appearance"),
          Card(
            child: SwitchListTile(
              title: const Text("Dark Mode"),
              subtitle: const Text("Switch between light and dark theme"),
              value: themeProvider.isDark,
              onChanged: (val) => themeProvider.toggleTheme(val),
              secondary: Icon(
                themeProvider.isDark ? Icons.dark_mode : Icons.light_mode,
                color: AppColors.primaryPink,
              ),
            ),
          ),
          const SizedBox(height: 20),

          _SectionLabel("Storage"),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.add_to_drive, color: AppColors.primaryPink),
                  title: const Text("Google Drive"),
                  subtitle: Text(_driveConnected
                      ? 'Connected — saving into "TikTok" folder'
                      : "Not connected"),
                  trailing: _loading
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : TextButton(
                          onPressed: () async {
                            setState(() => _loading = true);
                            if (_driveConnected) {
                              await DriveService.disconnect();
                            } else {
                              await DriveService.connect();
                            }
                            await _refreshDriveStatus();
                          },
                          child: Text(_driveConnected ? "Disconnect" : "Connect"),
                        ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),

          _SectionLabel("About"),
          Card(
            child: Column(
              children: const [
                ListTile(
                  leading: Icon(Icons.info_outline, color: AppColors.primaryPink),
                  title: Text("Version"),
                  subtitle: Text("1.0.0"),
                ),
                Divider(height: 1),
                ListTile(
                  leading: Icon(Icons.privacy_tip_outlined, color: AppColors.primaryPink),
                  title: Text("Privacy Policy"),
                ),
              ],
            ),
          ),
        ],
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
      padding: const EdgeInsets.only(left: 4, bottom: 8),
      child: Text(
        text,
        style: const TextStyle(
          fontWeight: FontWeight.bold,
          color: AppColors.deepPink,
          fontSize: 13,
        ),
      ),
    );
  }
}
