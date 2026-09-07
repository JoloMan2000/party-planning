import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/party.dart';
import '../state/auth_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// "My Parties"-Tab - seit dem Bottom-Nav-Umbau (Discover-MVP-Plan) ein bares
/// Body-Widget ohne eigenen `Scaffold`/`AppBar`/`TabBar`/FAB (die leben jetzt
/// gemeinsam in `HomeShell`), gehostet von deren `IndexedStack`.
class PartyListScreen extends ConsumerWidget {
  const PartyListScreen({super.key});

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
          return RefreshIndicator(
            onRefresh: () => ref.refresh(myPartiesProvider.future),
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              children: const [
                SizedBox(height: 200),
                Center(child: Text('No parties yet. Create one!')),
              ],
            ),
          );
        }
        return RefreshIndicator(
          onRefresh: () => ref.refresh(myPartiesProvider.future),
          child: ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: parties.length,
            itemBuilder: (context, i) => _PartyTile(party: parties[i]),
          ),
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
