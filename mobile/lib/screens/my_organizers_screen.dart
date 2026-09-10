import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/organizer.dart';
import '../state/organizer_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// "My Organizers" (Social-Graph-Phase-4) - die Organizer, in denen der User
/// Mitglied ist (jede Rolle). Erreichbar über eine Kachel auf
/// `ProfileScreen`. Eigener `Scaffold`/`AppBar` mit Zurück-Button, der
/// `showMyOrganizersProvider` zurücksetzt - Muster von `FriendsScreen`.
class MyOrganizersScreen extends ConsumerWidget {
  const MyOrganizersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final organizersAsync = ref.watch(myOrganizersProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('My Organizers'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(showMyOrganizersProvider.notifier).state = false,
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => ref.read(creatingOrganizerProvider.notifier).state = true,
        icon: const Icon(Icons.add),
        label: const Text('Create Organizer'),
      ),
      body: organizersAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(myOrganizersProvider),
            child: const Text('Failed to load organizers. Retry'),
          ),
        ),
        data: (organizers) {
          if (organizers.isEmpty) {
            return RefreshIndicator(
              onRefresh: () => ref.refresh(myOrganizersProvider.future),
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                children: const [
                  SizedBox(height: 200),
                  Center(child: Text('No organizers yet. Create one!')),
                ],
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: () => ref.refresh(myOrganizersProvider.future),
            child: ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: organizers.length,
              itemBuilder: (context, i) => _OrganizerTile(organizer: organizers[i]),
            ),
          );
        },
      ),
    );
  }
}

class _OrganizerTile extends ConsumerWidget {
  final Organizer organizer;
  const _OrganizerTile({required this.organizer});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final role = organizer.myRole;
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.groups)),
        title: Text(organizer.displayName),
        subtitle: Text(
          role == null ? organizer.verificationStatus : '${organizer.verificationStatus} · $role',
        ),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => ref.read(selectedOrganizerIdProvider.notifier).state = organizer.id,
      ),
    );
  }
}
