import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/app_notification.dart';
import '../state/auth_providers.dart';

// TODO(i18n): English-only strings for now, mirroring the deliberate Phase-3
// scope decision on the other screens.

/// Freie `kind`-Strings des Backends -> Icon. `notifications.kind` ist
/// bewusst kein Enum (siehe `backend/app/routers/notifications.py`), daher
/// hier ein tolerant fallendes `switch` (unbekannt -> Glocke).
IconData _iconForKind(String kind) {
  switch (kind) {
    case 'invitation':
      return Icons.mail;
    case 'rsvp':
      return Icons.how_to_reg;
    case 'friend_request_received':
      return Icons.person_add;
    case 'friend_request_accepted':
      return Icons.people;
    case 'organizer_new_event':
      return Icons.campaign;
    case 'event_updated':
      return Icons.edit_calendar;
    case 'event_cancelled':
      return Icons.event_busy;
    case 'co_host_promoted':
      return Icons.workspace_premium;
    case 'location_changed':
      return Icons.location_on;
    case 'discover_join':
      return Icons.celebration;
    default:
      return Icons.notifications;
  }
}

/// Notification-Inbox (Phase 5) - tippt eine Notification an, um zur
/// zugehörigen Party zu navigieren (sofern `party_id` gesetzt), und
/// markiert sie dabei als gelesen.
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
            return RefreshIndicator(
              onRefresh: () => ref.refresh(notificationsProvider.future),
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                children: const [
                  SizedBox(height: 200),
                  Center(child: Text('No notifications yet.')),
                ],
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: () => ref.refresh(notificationsProvider.future),
            child: ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: notifications.length,
              itemBuilder: (context, i) => _NotificationTile(notification: notifications[i]),
            ),
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
        leading: Icon(_iconForKind(notification.kind)),
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
