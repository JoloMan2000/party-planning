import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/followed_event.dart';
import '../models/organizer.dart';
import '../state/auth_providers.dart';
import '../state/organizer_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// "Following" (Social-Graph-Phase-5) - zwei Tabs: gefolgte Organizer und
/// gefolgte Events. Erreichbar über eine Kachel auf `ProfileScreen`. Erster
/// `DefaultTabController`/`TabBar`-Einsatz der Codebase (reines Flutter, kein
/// Paket). Zurück-Button setzt `showFollowingProvider` zurück.
class FollowingScreen extends ConsumerWidget {
  const FollowingScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Following'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back),
            onPressed: () => ref.read(showFollowingProvider.notifier).state = false,
          ),
          bottom: const TabBar(
            tabs: [Tab(text: 'Organizers'), Tab(text: 'Events')],
          ),
        ),
        body: const TabBarView(
          children: [_FollowedOrganizersTab(), _FollowedEventsTab()],
        ),
      ),
    );
  }
}

class _FollowedOrganizersTab extends ConsumerWidget {
  const _FollowedOrganizersTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final organizersAsync = ref.watch(followedOrganizersProvider);
    return organizersAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (err, st) => Center(
        child: TextButton(
          onPressed: () => ref.invalidate(followedOrganizersProvider),
          child: const Text('Failed to load. Retry'),
        ),
      ),
      data: (organizers) {
        if (organizers.isEmpty) {
          return const Center(child: Text("You're not following any organizers."));
        }
        return RefreshIndicator(
          onRefresh: () => ref.refresh(followedOrganizersProvider.future),
          child: ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: organizers.length,
            itemBuilder: (context, i) => _FollowedOrganizerTile(organizer: organizers[i]),
          ),
        );
      },
    );
  }
}

class _FollowedOrganizerTile extends ConsumerWidget {
  final Organizer organizer;
  const _FollowedOrganizerTile({required this.organizer});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final toggleState = ref.watch(toggleOrganizerFollowProvider);
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.groups)),
        title: Text(organizer.displayName),
        subtitle: Text(organizer.verificationStatus),
        trailing: TextButton(
          onPressed: toggleState.isLoading ? null : () => _unfollow(context, ref),
          child: const Text('Unfollow'),
        ),
        onTap: () => ref.read(selectedOrganizerIdProvider.notifier).state = organizer.id,
      ),
    );
  }

  Future<void> _unfollow(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(toggleOrganizerFollowProvider.notifier).unfollow(organizer.id);
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to unfollow. Please try again.')));
    }
  }
}

class _FollowedEventsTab extends ConsumerWidget {
  const _FollowedEventsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final eventsAsync = ref.watch(followedEventsProvider);
    return eventsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (err, st) => Center(
        child: TextButton(
          onPressed: () => ref.invalidate(followedEventsProvider),
          child: const Text('Failed to load. Retry'),
        ),
      ),
      data: (events) {
        if (events.isEmpty) {
          return const Center(child: Text("You're not following any events."));
        }
        return RefreshIndicator(
          onRefresh: () => ref.refresh(followedEventsProvider.future),
          child: ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: events.length,
            itemBuilder: (context, i) => _FollowedEventTile(event: events[i]),
          ),
        );
      },
    );
  }
}

class _FollowedEventTile extends ConsumerWidget {
  final FollowedEvent event;
  const _FollowedEventTile({required this.event});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final toggleState = ref.watch(toggleEventFollowProvider);
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.event)),
        title: Text(event.name),
        subtitle: Text(event.startsAt != null ? event.startsAt.toString() : event.location),
        trailing: TextButton(
          onPressed: toggleState.isLoading ? null : () => _unfollow(context, ref),
          child: const Text('Unfollow'),
        ),
        onTap: () => ref.read(selectedPartyIdProvider.notifier).state = event.partyId,
      ),
    );
  }

  Future<void> _unfollow(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(toggleEventFollowProvider.notifier).unfollow(event.partyId);
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to unfollow. Please try again.')));
    }
  }
}
