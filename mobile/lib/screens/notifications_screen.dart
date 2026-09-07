import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/app_notification.dart';
import '../state/auth_providers.dart';

// TODO(i18n): English-only strings for now, mirroring the deliberate Phase-3
// scope decision on the other screens.

/// Notification-Inbox (Phase 5) - tippt eine Notification an, um zur
/// zugehörigen Invitation (`kind == "invitation"`) bzw. Party
/// (`kind == "rsvp"`) zu navigieren, und markiert sie dabei als gelesen.
class NotificationsScreen extends ConsumerWidget {
  const NotificationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notificationsAsync = ref.watch(notificationsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(showNotificationsProvider.notifier).state = false,
        ),
      ),
      body: notificationsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(notificationsProvider),
            child: const Text('Failed to load notifications. Retry'),
          ),
        ),
        data: (notifications) {
          if (notifications.isEmpty) {
            return const Center(child: Text('No notifications yet.'));
          }
          return ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: notifications.length,
            itemBuilder: (context, i) => _NotificationTile(notification: notifications[i]),
          );
        },
      ),
    );
  }
}

class _NotificationTile extends ConsumerWidget {
  final AppNotification notification;
  const _NotificationTile({required this.notification});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      color: notification.read ? null : Theme.of(context).colorScheme.primaryContainer,
      child: ListTile(
        leading: Icon(notification.kind == 'invitation' ? Icons.mail : Icons.how_to_reg),
        title: Text(notification.message),
        subtitle: Text(notification.createdAt.toString()),
        onTap: () => _handleTap(ref),
      ),
    );
  }

  Future<void> _handleTap(WidgetRef ref) async {
    if (!notification.read) {
      await ref.read(markNotificationReadProvider.notifier).markRead(notification.id);
    }
    ref.read(showNotificationsProvider.notifier).state = false;
    final partyId = notification.partyId;
    if (partyId == null) return;
    ref.read(selectedPartyIdProvider.notifier).state = partyId;
  }
}
