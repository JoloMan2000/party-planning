import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/notification_settings.dart';
import '../state/notification_settings_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Social-Graph-Phase-8: pro-Kategorie-Schalter für In-App-Benachrichtigungen.
/// Struktureller Klon von `SocialPrivacyScreen` (gleiches
/// `_initialized`/`_saving`/`_seedFrom`/`_save`-Muster, nur `SwitchListTile`s).
/// Erreichbar über eine Kachel auf `ProfileScreen`.
class NotificationSettingsScreen extends ConsumerStatefulWidget {
  const NotificationSettingsScreen({super.key});

  @override
  ConsumerState<NotificationSettingsScreen> createState() => _NotificationSettingsScreenState();
}

class _NotificationSettingsScreenState extends ConsumerState<NotificationSettingsScreen> {
  bool _initialized = false;
  bool _saving = false;

  bool _friendRequests = true;
  bool _partyInvitations = true;
  bool _organizerUpdates = true;
  bool _followedEventUpdates = true;
  bool _nearbyDiscover = true;

  void _seedFrom(NotificationSettings settings) {
    if (_initialized) return;
    _initialized = true;
    _friendRequests = settings.friendRequests;
    _partyInvitations = settings.partyInvitations;
    _organizerUpdates = settings.organizerUpdates;
    _followedEventUpdates = settings.followedEventUpdates;
    _nearbyDiscover = settings.nearbyDiscover;
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final current = ref.read(notificationSettingsProvider).valueOrNull ??
          const NotificationSettings(
            friendRequests: true,
            partyInvitations: true,
            organizerUpdates: true,
            followedEventUpdates: true,
            nearbyDiscover: true,
          );
      await ref.read(notificationSettingsProvider.notifier).save(
            current.copyWith(
              friendRequests: _friendRequests,
              partyInvitations: _partyInvitations,
              organizerUpdates: _organizerUpdates,
              followedEventUpdates: _followedEventUpdates,
              nearbyDiscover: _nearbyDiscover,
            ),
          );
      if (mounted) messenger.showSnackBar(const SnackBar(content: Text('Notification settings saved.')));
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to save. Please try again.')));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final settingsAsync = ref.watch(notificationSettingsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Notification Settings'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(showNotificationSettingsProvider.notifier).state = false,
        ),
      ),
      body: settingsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(notificationSettingsProvider),
            child: const Text('Failed to load settings. Retry'),
          ),
        ),
        data: (settings) {
          _seedFrom(settings);
          return SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Friend requests'),
                  value: _friendRequests,
                  onChanged: (v) => setState(() => _friendRequests = v),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Party invitations'),
                  value: _partyInvitations,
                  onChanged: (v) => setState(() => _partyInvitations = v),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Updates from organizers I follow'),
                  value: _organizerUpdates,
                  onChanged: (v) => setState(() => _organizerUpdates = v),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Updates about events I follow'),
                  value: _followedEventUpdates,
                  onChanged: (v) => setState(() => _followedEventUpdates = v),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Nearby events in Discover'),
                  value: _nearbyDiscover,
                  onChanged: (v) => setState(() => _nearbyDiscover = v),
                ),
                const SizedBox(height: 20),
                ElevatedButton(
                  onPressed: _saving ? null : _save,
                  child: _saving
                      ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('Save'),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
