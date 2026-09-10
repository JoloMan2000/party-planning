import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../geo/debounce.dart';
import '../models/search_results.dart';
import '../models/user_search_result.dart';
import '../state/auth_providers.dart';
import '../state/organizer_providers.dart';
import '../state/search_providers.dart';
import '../state/social_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Unified Search (Social-Graph-Phase-6) - eine Suche über People,
/// Organizers und Events. Erreichbar über das Lupen-Icon in der
/// `HomeShell`-AppBar. Suche-während-Tippen mit Debounce (mirrort
/// `FriendsScreen`). Zurück-Button setzt `showSearchProvider` zurück.
class SearchScreen extends ConsumerStatefulWidget {
  const SearchScreen({super.key});

  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen> {
  final _searchController = TextEditingController();
  final _searchDebouncer = Debouncer();

  @override
  void dispose() {
    _searchController.dispose();
    _searchDebouncer.dispose();
    super.dispose();
  }

  void _onSearchChanged(String query) {
    setState(() {});
    _searchDebouncer.run(() => ref.read(unifiedSearchProvider.notifier).search(query));
  }

  void _clearSearch() {
    _searchController.clear();
    ref.read(unifiedSearchProvider.notifier).clear();
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final resultsAsync = ref.watch(unifiedSearchProvider);
    final isSearching = _searchController.text.trim().length >= 2;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Search'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(showSearchProvider.notifier).state = false,
        ),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: TextField(
              controller: _searchController,
              autofocus: true,
              onChanged: _onSearchChanged,
              decoration: InputDecoration(
                hintText: 'Search people, organizers and events',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _searchController.text.isEmpty
                    ? null
                    : IconButton(icon: const Icon(Icons.clear), onPressed: _clearSearch),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
          ),
          Expanded(
            child: !isSearching
                ? const Center(child: Text('Type at least 2 characters to search.'))
                : resultsAsync.when(
                    loading: () => const Center(child: CircularProgressIndicator()),
                    error: (err, st) => const Center(child: Text('Search failed. Try again.')),
                    data: (results) => _ResultsList(results: results),
                  ),
          ),
        ],
      ),
    );
  }
}

class _ResultsList extends StatelessWidget {
  final SearchResults results;
  const _ResultsList({required this.results});

  @override
  Widget build(BuildContext context) {
    if (results.isEmpty) {
      return const Center(child: Text('No results.'));
    }
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        if (results.users.isNotEmpty) ...[
          const _SectionHeader('People'),
          for (final u in results.users) _UserResultTile(result: u),
        ],
        if (results.organizers.isNotEmpty) ...[
          const _SectionHeader('Organizers'),
          for (final o in results.organizers) _OrganizerResultTile(result: o),
        ],
        if (results.events.isNotEmpty) ...[
          const _SectionHeader('Events'),
          for (final e in results.events) _EventResultTile(result: e),
        ],
      ],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String label;
  const _SectionHeader(this.label);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 12, 4, 4),
      child: Text(label, style: Theme.of(context).textTheme.titleSmall),
    );
  }
}

class _UserResultTile extends ConsumerWidget {
  final UserSearchResult result;
  const _UserResultTile({required this.result});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.person)),
        title: Text(result.displayName),
        subtitle: result.username.isEmpty ? null : Text('@${result.username}'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => ref.read(selectedFriendProfileUserIdProvider.notifier).state = result.userId,
      ),
    );
  }
}

class _OrganizerResultTile extends ConsumerStatefulWidget {
  final OrganizerSearchResult result;
  const _OrganizerResultTile({required this.result});

  @override
  ConsumerState<_OrganizerResultTile> createState() => _OrganizerResultTileState();
}

class _OrganizerResultTileState extends ConsumerState<_OrganizerResultTile> {
  late bool _following = widget.result.isFollowing;
  bool _busy = false;

  Future<void> _toggle() async {
    setState(() => _busy = true);
    final messenger = ScaffoldMessenger.of(context);
    final notifier = ref.read(toggleOrganizerFollowProvider.notifier);
    try {
      if (_following) {
        await notifier.unfollow(widget.result.organizerId);
      } else {
        await notifier.follow(widget.result.organizerId);
      }
      if (mounted) setState(() => _following = !_following);
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to update follow. Please try again.')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = widget.result;
    final followerLabel = '${r.followerCount} follower${r.followerCount == 1 ? '' : 's'}';
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.groups)),
        title: Text(r.displayName),
        subtitle: Text(r.verified ? 'Verified · $followerLabel' : followerLabel),
        trailing: _following
            ? OutlinedButton(onPressed: _busy ? null : _toggle, child: const Text('Following'))
            : ElevatedButton(onPressed: _busy ? null : _toggle, child: const Text('Follow')),
        onTap: () => ref.read(selectedOrganizerIdProvider.notifier).state = r.organizerId,
      ),
    );
  }
}

class _EventResultTile extends ConsumerStatefulWidget {
  final EventSearchResult result;
  const _EventResultTile({required this.result});

  @override
  ConsumerState<_EventResultTile> createState() => _EventResultTileState();
}

class _EventResultTileState extends ConsumerState<_EventResultTile> {
  late bool _following = widget.result.isFollowing;
  bool _busy = false;

  Future<void> _toggle() async {
    setState(() => _busy = true);
    final messenger = ScaffoldMessenger.of(context);
    final notifier = ref.read(toggleEventFollowProvider.notifier);
    try {
      if (_following) {
        await notifier.unfollow(widget.result.partyId);
      } else {
        await notifier.follow(widget.result.partyId);
      }
      if (mounted) setState(() => _following = !_following);
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to update follow. Please try again.')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = widget.result;
    final parts = [
      if (r.startsAt != null) r.startsAt.toString() else if (r.location.isNotEmpty) r.location,
      if (r.organizerName.isNotEmpty) 'by ${r.organizerName}',
    ];
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.event)),
        title: Text(r.name),
        subtitle: parts.isEmpty ? null : Text(parts.join(' · ')),
        trailing: _following
            ? OutlinedButton(onPressed: _busy ? null : _toggle, child: const Text('Following'))
            : ElevatedButton(onPressed: _busy ? null : _toggle, child: const Text('Follow')),
        onTap: () => ref.read(selectedPartyIdProvider.notifier).state = r.partyId,
      ),
    );
  }
}
