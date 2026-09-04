import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../models/invitation.dart';
import '../state/auth_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Einladungsdetail + RSVP-Buttons (Akzeptieren/Vielleicht/Ablehnen statt
/// Swipe-Gesten, siehe Plan-Entscheidung #2). Kein optimistisches UI - nach
/// jeder Antwort wird neu geladen, da die servergeführte `version` für den
/// nächsten Versuch stimmen muss (siehe `RsvpNotifier`-Doc-Kommentar).
class InvitationDetailScreen extends ConsumerWidget {
  final String invitationId;
  const InvitationDetailScreen({super.key, required this.invitationId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final invitationAsync = ref.watch(invitationDetailProvider(invitationId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Invitation'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(selectedInvitationIdProvider.notifier).state = null,
        ),
      ),
      body: invitationAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(invitationDetailProvider(invitationId)),
            child: const Text('Failed to load invitation. Retry'),
          ),
        ),
        data: (invitation) => _InvitationBody(invitation: invitation),
      ),
    );
  }
}

class _InvitationBody extends ConsumerWidget {
  final Invitation invitation;
  const _InvitationBody({required this.invitation});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final partyAsync = ref.watch(partyDetailProvider(invitation.partyId));
    final rsvpState = ref.watch(rsvpProvider);
    final isLoading = rsvpState.isLoading;
    final isTerminal = invitation.status == InvitationStatus.revoked ||
        invitation.status == InvitationStatus.expired;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: partyAsync.when(
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (err, st) => const Text('Party info unavailable.'),
                data: (party) => Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(party.name, style: Theme.of(context).textTheme.titleLarge),
                    if (party.description.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Text(party.description),
                    ],
                    if (party.startsAt != null) ...[
                      const SizedBox(height: 8),
                      Text('When: ${party.startsAt}'),
                    ],
                    if (party.location.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Text('Where: ${party.location}'),
                    ],
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          if (invitation.invitationMessage.isNotEmpty) ...[
            Text('Message: ${invitation.invitationMessage}'),
            const SizedBox(height: 12),
          ],
          Text('Status: ${invitation.status.name}'),
          const SizedBox(height: 20),
          if (isTerminal)
            const Text('This invitation can no longer be updated.')
          else ...[
            ElevatedButton(
              onPressed: isLoading || invitation.status == InvitationStatus.accepted
                  ? null
                  : () => _respond(context, ref, 'accepted'),
              child: const Text('Accept'),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: isLoading || invitation.status == InvitationStatus.tentative
                  ? null
                  : () => _respond(context, ref, 'tentative'),
              child: const Text('Maybe'),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: isLoading || invitation.status == InvitationStatus.declined
                  ? null
                  : () => _respond(context, ref, 'declined'),
              child: const Text('Decline'),
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _respond(BuildContext context, WidgetRef ref, String status) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(rsvpProvider.notifier).respond(
            invitation.id,
            status: status,
            version: invitation.version,
          );
    } on ApiException catch (e) {
      if (e.statusCode == 409) {
        ref.invalidate(invitationDetailProvider(invitation.id));
        messenger.showSnackBar(
          const SnackBar(content: Text('This invitation changed - please try again.')),
        );
      } else if (e.statusCode == 422) {
        messenger.showSnackBar(
          const SnackBar(content: Text('This invitation can no longer be updated.')),
        );
      } else {
        messenger.showSnackBar(
          const SnackBar(content: Text('Failed to update RSVP. Please try again.')),
        );
      }
    }
  }
}
