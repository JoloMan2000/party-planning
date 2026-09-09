import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../geo/debounce.dart';
import '../models/friend.dart';
import '../models/friend_request.dart';
import '../models/social_profile.dart';
import '../models/user_search_result.dart';
import '../state/social_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Friends-Screen (Social-Graph-Phase-1) - Suche, Anfragen-Inbox, Freundes-
/// liste. Erreichbar über die "Friends"-Kachel auf `ProfileScreen` (kein
/// eigener Bottom-Nav-Tab, siehe Plan). Eigener `Scaffold`/`AppBar` mit
/// Zurück-Button, der `showFriendsProvider` zurücksetzt - exakt das Muster
/// von `SpotifyConnectScreen`/`ProfileScreen`.
class FriendsScreen extends ConsumerStatefulWidget {
  const FriendsScreen({super.key});

  @override
  ConsumerState<FriendsScreen> createState() => _FriendsScreenState();
}

class _FriendsScreenState extends ConsumerState<FriendsScreen> {
  final _searchController = TextEditingController();
  final _searchDebouncer = Debouncer();

  @override
  void dispose() {
    _searchController.dispose();
    _searchDebouncer.dispose();
    super.dispose();
  }

  void _onSearchChanged(String query) {
    setState(() {}); // damit der Body zwischen Suchergebnissen/Listen umschaltet
    _searchDebouncer.run(() => ref.read(userSearchProvider.notifier).search(query));
  }

  void _clearSearch() {
    _searchController.clear();
    ref.read(userSearchProvider.notifier).clear();
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final isSearching = _searchController.text.trim().length >= 2;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Friends'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(showFriendsProvider.notifier).state = false,
        ),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: TextField(
              controller: _searchController,
              onChanged: _onSearchChanged,
              decoration: InputDecoration(
                hintText: 'Search people by name or username',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _searchController.text.isEmpty
                    ? null
                    : IconButton(icon: const Icon(Icons.clear), onPressed: _clearSearch),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
          ),
          Expanded(child: isSearching ? const _SearchResultsList() : const _RequestsAndFriendsList()),
        ],
      ),
    );
  }
}

class _SearchResultsList extends ConsumerWidget {
  const _SearchResultsList();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final resultsAsync = ref.watch(userSearchProvider);
    return resultsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (err, st) => const Center(child: Text('Search failed. Try again.')),
      data: (results) {
        if (results.isEmpty) {
          return const Center(child: Text('No people found.'));
        }
        return ListView.builder(
          padding: const EdgeInsets.all(12),
          itemCount: results.length,
          itemBuilder: (context, i) => _SearchResultTile(result: results[i]),
        );
      },
    );
  }
}

class _SearchResultTile extends ConsumerWidget {
  final UserSearchResult result;
  const _SearchResultTile({required this.result});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sendState = ref.watch(sendFriendRequestProvider);
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.person)),
        title: Text(result.displayName),
        subtitle: result.username.isEmpty ? null : Text('@${result.username}'),
        trailing: _actionForStatus(context, ref, sendState.isLoading),
        onTap: () => ref.read(selectedFriendProfileUserIdProvider.notifier).state = result.userId,
      ),
    );
  }

  Widget? _actionForStatus(BuildContext context, WidgetRef ref, bool isLoading) {
    switch (result.relationshipStatus) {
      case RelationshipStatus.none_:
        return TextButton(
          onPressed: isLoading ? null : () => _sendRequest(context, ref),
          child: const Text('Add Friend'),
        );
      case RelationshipStatus.requestSent:
        return const Text('Requested');
      case RelationshipStatus.requestReceived:
        return const Text('Respond');
      case RelationshipStatus.friends:
        return const Icon(Icons.check, color: Colors.green);
      case RelationshipStatus.blocked:
        return null;
      case RelationshipStatus.self_:
        return null;
    }
  }

  Future<void> _sendRequest(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(sendFriendRequestProvider.notifier).send(result.userId);
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to send friend request. Please try again.')));
    }
  }
}

class _RequestsAndFriendsList extends ConsumerWidget {
  const _RequestsAndFriendsList();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final requestsAsync = ref.watch(friendRequestsProvider);
    final friendsAsync = ref.watch(friendsProvider);

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(friendRequestsProvider);
        ref.invalidate(friendsProvider);
      },
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          requestsAsync.when(
            loading: () => const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator()),
            ),
            error: (err, st) => TextButton(
              onPressed: () => ref.invalidate(friendRequestsProvider),
              child: const Text('Failed to load requests. Retry'),
            ),
            data: (inbox) => _RequestsSection(inbox: inbox),
          ),
          const SizedBox(height: 20),
          const Text('Your Friends', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          const SizedBox(height: 8),
          friendsAsync.when(
            loading: () => const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator()),
            ),
            error: (err, st) => TextButton(
              onPressed: () => ref.invalidate(friendsProvider),
              child: const Text('Failed to load friends. Retry'),
            ),
            data: (friends) {
              if (friends.isEmpty) {
                return const Padding(
                  padding: EdgeInsets.symmetric(vertical: 20),
                  child: Center(child: Text('No friends yet. Search for people above.')),
                );
              }
              return Column(children: friends.map((f) => _FriendTile(friend: f)).toList());
            },
          ),
        ],
      ),
    );
  }
}

class _RequestsSection extends ConsumerWidget {
  final FriendRequestsInbox inbox;
  const _RequestsSection({required this.inbox});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (inbox.incoming.isEmpty && inbox.outgoing.isEmpty) {
      return const SizedBox.shrink();
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Friend Requests', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
        const SizedBox(height: 8),
        ...inbox.incoming.map((r) => _IncomingRequestTile(request: r)),
        ...inbox.outgoing.map((r) => _OutgoingRequestTile(request: r)),
      ],
    );
  }
}

class _IncomingRequestTile extends ConsumerWidget {
  final FriendRequest request;
  const _IncomingRequestTile({required this.request});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final respondState = ref.watch(respondFriendRequestProvider);
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.person)),
        title: Text(request.otherDisplayName),
        subtitle: request.otherUsername.isEmpty ? null : Text('@${request.otherUsername}'),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            IconButton(
              icon: const Icon(Icons.check, color: Colors.green),
              onPressed: respondState.isLoading ? null : () => _respond(context, ref, accept: true),
            ),
            IconButton(
              icon: const Icon(Icons.close, color: Colors.red),
              onPressed: respondState.isLoading ? null : () => _respond(context, ref, accept: false),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _respond(BuildContext context, WidgetRef ref, {required bool accept}) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      if (accept) {
        await ref.read(respondFriendRequestProvider.notifier).accept(request.id);
      } else {
        await ref.read(respondFriendRequestProvider.notifier).decline(request.id);
      }
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to respond. Please try again.')));
    }
  }
}

class _OutgoingRequestTile extends ConsumerWidget {
  final FriendRequest request;
  const _OutgoingRequestTile({required this.request});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cancelState = ref.watch(cancelFriendRequestProvider);
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.person)),
        title: Text(request.otherDisplayName),
        subtitle: const Text('Requested'),
        trailing: TextButton(
          onPressed: cancelState.isLoading ? null : () => _cancel(context, ref),
          child: const Text('Cancel'),
        ),
      ),
    );
  }

  Future<void> _cancel(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(cancelFriendRequestProvider.notifier).cancel(request.id);
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to cancel. Please try again.')));
    }
  }
}

class _FriendTile extends ConsumerWidget {
  final Friend friend;
  const _FriendTile({required this.friend});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.person)),
        title: Text(friend.displayName),
        subtitle: friend.username.isEmpty ? null : Text('@${friend.username}'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => ref.read(selectedFriendProfileUserIdProvider.notifier).state = friend.userId,
      ),
    );
  }
}
