import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/notification_settings.dart';
import 'auth_providers.dart';
import 'providers.dart';

/// Social Graph Phase 8 (Notification-Kategorie-Schalter) - siehe
/// `backend/app/routers/notification_settings.py`.

/// Mirrort `SocialPrivacyNotifier` in `social_providers.dart` exakt:
/// `build()` lädt, `save()` PUTet den vollständigen Datensatz.
class NotificationSettingsNotifier extends AsyncNotifier<NotificationSettings> {
  @override
  Future<NotificationSettings> build() async {
    final token = ref.watch(requiredAccessTokenProvider);
    return ref.watch(apiClientProvider).getNotificationSettings(token, onRefresh(ref));
  }

  Future<void> save(NotificationSettings settings) async {
    final token = ref.read(requiredAccessTokenProvider);
    final saved = await ref.read(apiClientProvider).updateNotificationSettings(token, onRefresh(ref), settings);
    state = AsyncData(saved);
  }
}

final notificationSettingsProvider =
    AsyncNotifierProvider<NotificationSettingsNotifier, NotificationSettings>(NotificationSettingsNotifier.new);

/// Navigations-Flag (mirrort `showSocialPrivacyProvider`).
final showNotificationSettingsProvider = StateProvider<bool>((ref) => false);
