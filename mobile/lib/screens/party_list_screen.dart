import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/invitation.dart';
import '../models/party.dart';
import '../state/auth_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Authentifizierte Startseite: eigene Partys + eigene Einladungen in zwei
/// Tabs, mirroring den bestehenden Tab-losen Screens aber neu mit
/// `TabBar`/`TabBarView`, da hier erstmals zwei gleichrangige Listen
/// nebeneinander existieren.
class PartyListScreen extends ConsumerWidget {
  const PartyListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final userAsync = ref.watch(currentUserProvider);

    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: Text(userAsync.maybeWhen(
            data: (user) => 'Hi, ${user.displayName}',
            orElse: () => 'Party App',
          )),
          actions: [
            IconButton(
              icon: const Icon(Icons.logout),
              tooltip: 'Log out',
              onPressed: () => ref.read(authProvider.notifier).logout(),
            ),
          ],
          bottom: const TabBar(
            tabs: [
              Tab(text: 'My Parties'),
              Tab(text: 'My Invitations'),
            ],
          ),
        ),
        body: const TabBarView(
          children: [_MyPartiesTab(), _MyInvitationsTab()],
        ),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: () => ref.read(creatingPartyProvider.notifier).state = true,
          icon: const Icon(Icons.add),
          label: const Text('Create Party'),
        ),
      ),
    );
  }
}

class _MyPartiesTab extends ConsumerWidget {
  const _MyPartiesTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final partiesAsync = ref.watch(myPartiesProvider);
    return partiesAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (err, st) => Center(
        child: TextButton(
          onPressed: () => ref.invalidate(myPartiesProvider),
          child: const Text('Failed to load parties. Retry'),
        ),
      ),
      data: (parties) {
        if (parties.isEmpty) {
          return const Center(child: Text('No parties yet. Create one!'));
        }
        return ListView.builder(
          padding: const EdgeInsets.all(12),
          itemCount: parties.length,
          itemBuilder: (context, i) => _PartyTile(party: parties[i]),
        );
      },
    );
  }
}

class _PartyTile extends ConsumerWidget {
  final Party party;
  const _PartyTile({required this.party});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: ListTile(
        title: Text(party.name),
        subtitle: Text(
          party.startsAt != null ? party.startsAt.toString() : party.location,
        ),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => ref.read(selectedPartyIdProvider.notifier).state = party.id,
      ),
    );
  }
}

class _MyInvitationsTab extends ConsumerWidget {
  const _MyInvitationsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final invitationsAsync = ref.watch(myInvitationsProvider);
    return invitationsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (err, st) => Center(
        child: TextButton(
          onPressed: () => ref.invalidate(myInvitationsProvider),
          child: const Text('Failed to load invitations. Retry'),
        ),
      ),
      data: (invitations) {
        if (invitations.isEmpty) {
          return const Center(child: Text('No invitations yet.'));
        }
        return ListView.builder(
          padding: const EdgeInsets.all(12),
          itemCount: invitations.length,
          itemBuilder: (context, i) => _InvitationTile(invitation: invitations[i]),
        );
      },
    );
  }
}

class _InvitationTile extends ConsumerWidget {
  final Invitation invitation;
  const _InvitationTile({required this.invitation});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: ListTile(
        title: const Text('Invitation'),
        subtitle: Text('Status: ${invitation.status.name}'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => ref.read(selectedInvitationIdProvider.notifier).state = invitation.id,
      ),
    );
  }
}
