import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../models/friend.dart';
import '../state/social_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Social-Graph-Phase-3: minimale Ansicht der Freundesliste eines ANDEREN
/// Users - bewusst schlank (keine Suche, keine Aktionen), da ohne diesen
/// Screen die `friend_list_visibility`-Einstellung enforced, aber für
/// niemanden je sichtbar wäre (siehe Plan). Bei 403 (Liste privat) zeigt
/// dieser Screen einen erklärenden Leerzustand statt eines generischen
/// Fehlers - mirrort `ProfileScreen`'s 404-Sonderfall-Handling.
class UserFriendsScreen extends ConsumerWidget {
  final String userId;
  const UserFriendsScreen({super.key, required this.userId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final friendsAsync = ref.watch(userFriendsProvider(userId));
    // Nutzt den bereits (beim Aufruf des Profils) geladenen socialProfileProvider
    // fürs Anzeige-Namen im Titel, statt den Namen extra durch die
    // Navigations-State-Provider durchzureichen - viewingUserFriendsUserIdProvider
    // trägt bewusst nur die userId, mirrort selectedFriendProfileUserIdProvider.
    final displayName = ref.watch(socialProfileProvider(userId)).valueOrNull?.displayName;

    return Scaffold(
      appBar: AppBar(
        title: Text(displayName != null ? '$displayName\'s Friends' : 'Friends'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(viewingUserFriendsUserIdProvider.notifier).state = null,
        ),
      ),
      body: friendsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) {
          if (err is ApiException && err.statusCode == 403) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: Text('This person\'s friend list is private.'),
              ),
            );
          }
          return Center(
            child: TextButton(
              onPressed: () => ref.invalidate(userFriendsProvider(userId)),
              child: const Text('Failed to load friends. Retry'),
            ),
          );
        },
        data: (friends) {
          if (friends.isEmpty) {
            return const Center(child: Text('No friends yet.'));
          }
          return ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: friends.length,
            itemBuilder: (context, i) => _FriendListTile(friend: friends[i]),
          );
        },
      ),
    );
  }
}

class _FriendListTile extends StatelessWidget {
  final Friend friend;
  const _FriendListTile({required this.friend});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.person)),
        title: Text(friend.displayName),
        subtitle: friend.username.isEmpty ? null : Text('@${friend.username}'),
      ),
    );
  }
}
