import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../models/followed_event.dart';
import '../models/organizer.dart';
import '../state/auth_providers.dart';
import '../state/organizer_providers.dart';
import '../state/social_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Die Following-Liste eines ANDEREN Users (Social-Graph-Phase-7) - read-only
/// (keine Unfollow-Buttons), zwei Tabs. Serverseitig über dessen
/// `following_visibility` gegated: 403 -> erklärender Leerzustand (mirrort
/// `UserFriendsScreen`). Zurück-Button setzt
/// `viewingUserFollowingUserIdProvider` zurück.
class UserFollowingScreen extends ConsumerWidget {
  final String userId;
  const UserFollowingScreen({super.key, required this.userId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final displayName = ref.watch(socialProfileProvider(userId)).valueOrNull?.displayName;

    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: Text(displayName != null ? "$displayName's Following" : 'Following'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back),
            onPressed: () => ref.read(viewingUserFollowingUserIdProvider.notifier).state = null,
          ),
          bottom: const TabBar(
            tabs: [Tab(text: 'Organizers'), Tab(text: 'Events')],
          ),
        ),
        body: TabBarView(
          children: [
            _UserFollowedOrganizersTab(userId: userId),
            _UserFollowedEventsTab(userId: userId),
          ],
        ),
      ),
    );
  }
}

Widget _privateOrError(Object err, void Function() retry) {
  if (err is ApiException && err.statusCode == 403) {
    return const Center(
      child: Padding(
        padding: EdgeInsets.all(20),
        child: Text("This person's following list is private."),
      ),
    );
  }
  return Center(child: TextButton(onPressed: retry, child: const Text('Failed to load. Retry')));
}

class _UserFollowedOrganizersTab extends ConsumerWidget {
  final String userId;
  const _UserFollowedOrganizersTab({required this.userId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final organizersAsync = ref.watch(userFollowedOrganizersProvider(userId));
    return organizersAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (err, st) => _privateOrError(err, () => ref.invalidate(userFollowedOrganizersProvider(userId))),
      data: (organizers) {
        if (organizers.isEmpty) {
          return const Center(child: Text('Not following any organizers.'));
        }
        return ListView.builder(
          padding: const EdgeInsets.all(12),
          itemCount: organizers.length,
          itemBuilder: (context, i) => _OrganizerRow(organizer: organizers[i]),
        );
      },
    );
  }
}

class _OrganizerRow extends ConsumerWidget {
  final Organizer organizer;
  const _OrganizerRow({required this.organizer});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.groups)),
        title: Text(organizer.displayName),
        subtitle: Text(organizer.verificationStatus),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => ref.read(selectedOrganizerIdProvider.notifier).state = organizer.id,
      ),
    );
  }
}

class _UserFollowedEventsTab extends ConsumerWidget {
  final String userId;
  const _UserFollowedEventsTab({required this.userId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final eventsAsync = ref.watch(userFollowedEventsProvider(userId));
    return eventsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (err, st) => _privateOrError(err, () => ref.invalidate(userFollowedEventsProvider(userId))),
      data: (events) {
        if (events.isEmpty) {
          return const Center(child: Text('Not following any events.'));
        }
        return ListView.builder(
          padding: const EdgeInsets.all(12),
          itemCount: events.length,
          itemBuilder: (context, i) => _EventRow(event: events[i]),
        );
      },
    );
  }
}

class _EventRow extends ConsumerWidget {
  final FollowedEvent event;
  const _EventRow({required this.event});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.event)),
        title: Text(event.name),
        subtitle: Text(event.startsAt != null ? event.startsAt.toString() : event.location),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => ref.read(selectedPartyIdProvider.notifier).state = event.partyId,
      ),
    );
  }
}
