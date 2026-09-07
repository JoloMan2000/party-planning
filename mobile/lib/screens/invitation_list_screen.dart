import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/invitation.dart';
import '../state/auth_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// "My Invites"-Tab, extrahiert aus dem alten `PartyListScreen`
/// (Bottom-Nav-Umbau, siehe Discover-MVP-Plan) - bare Body-Widget ohne
/// eigenen `Scaffold`/`AppBar`, gehostet von `HomeShell`'s `IndexedStack`.
class InvitationListScreen extends ConsumerWidget {
  const InvitationListScreen({super.key});

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
