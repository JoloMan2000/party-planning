import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../models/party.dart';
import '../models/party_guests_response.dart';
import '../state/auth_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Party-Detail: Host/Co-Host sehen Gästeliste + Invite-Formular, einfache
/// Gäste sehen nur die Party-Infos (Unterscheidung über 403 auf
/// `partyGuestsProvider`, siehe Plan - keine explizite Rollen-Prüfung
/// client-seitig, da `GET /parties/{id}` die eigene Rolle nicht mitliefert).
class PartyDetailScreen extends ConsumerWidget {
  final String partyId;
  const PartyDetailScreen({super.key, required this.partyId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final partyAsync = ref.watch(partyDetailProvider(partyId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Party'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(selectedPartyIdProvider.notifier).state = null,
        ),
      ),
      body: partyAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(partyDetailProvider(partyId)),
            child: const Text('Failed to load party. Retry'),
          ),
        ),
        data: (party) => SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _PartyHeader(party: party),
              const SizedBox(height: 20),
              _GuestsSection(partyId: partyId),
            ],
          ),
        ),
      ),
    );
  }
}

class _PartyHeader extends StatelessWidget {
  final Party party;
  const _PartyHeader({required this.party});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
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
    );
  }
}

class _GuestsSection extends ConsumerWidget {
  final String partyId;
  const _GuestsSection({required this.partyId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final guestsAsync = ref.watch(partyGuestsProvider(partyId));

    return guestsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (err, st) {
        if (err is ApiException && err.statusCode == 403) {
          // Guest ohne Host-/Co-Host-Rolle: kein Fehler, nur eingeschränkte Sicht.
          return const SizedBox.shrink();
        }
        return Center(
          child: TextButton(
            onPressed: () => ref.invalidate(partyGuestsProvider(partyId)),
            child: const Text('Failed to load guest list. Retry'),
          ),
        );
      },
      data: (guests) => _HostGuestsView(partyId: partyId, guests: guests),
    );
  }
}

class _HostGuestsView extends ConsumerStatefulWidget {
  final String partyId;
  final PartyGuestsResponse guests;
  const _HostGuestsView({required this.partyId, required this.guests});

  @override
  ConsumerState<_HostGuestsView> createState() => _HostGuestsViewState();
}

class _HostGuestsViewState extends ConsumerState<_HostGuestsView> {
  final _emailController = TextEditingController();
  String? _inviteError;

  @override
  void dispose() {
    _emailController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final inviteState = ref.watch(inviteGuestProvider);
    final isLoading = inviteState.isLoading;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Guests', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: widget.guests.counts.entries
              .map((e) => Chip(label: Text('${e.key}: ${e.value}')))
              .toList(),
        ),
        const SizedBox(height: 8),
        ...widget.guests.guests.map(
          (g) => ListTile(
            title: Text(g.displayName),
            subtitle: Text('${g.email} · ${g.role}'),
            trailing: Text(g.rsvpStatus),
          ),
        ),
        const SizedBox(height: 16),
        Text('Invite a guest', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        TextField(
          controller: _emailController,
          keyboardType: TextInputType.emailAddress,
          decoration: const InputDecoration(
            labelText: 'Guest email',
            border: OutlineInputBorder(),
          ),
        ),
        if (_inviteError != null) ...[
          const SizedBox(height: 8),
          Text(
            _inviteError!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ],
        const SizedBox(height: 8),
        ElevatedButton(
          onPressed: isLoading ? null : _submitInvite,
          child: isLoading
              ? const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Invite'),
        ),
      ],
    );
  }

  Future<void> _submitInvite() async {
    final email = _emailController.text.trim();
    if (email.isEmpty) {
      setState(() => _inviteError = 'Please enter an email address.');
      return;
    }
    setState(() => _inviteError = null);
    try {
      await ref.read(inviteGuestProvider.notifier).invite(widget.partyId, invitedUserEmail: email);
      _emailController.clear();
      ref.invalidate(partyGuestsProvider(widget.partyId));
    } on ApiException catch (e) {
      setState(() {
        if (e.statusCode == 404) {
          _inviteError = 'No account found for this email.';
        } else if (e.statusCode == 409) {
          _inviteError = 'This person is already invited.';
        } else {
          _inviteError = 'Failed to invite. Please try again.';
        }
      });
    }
  }
}
