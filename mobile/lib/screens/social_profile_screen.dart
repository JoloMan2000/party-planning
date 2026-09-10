import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/social_profile.dart';
import '../state/organizer_providers.dart';
import '../state/social_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Profil-Ansicht eines anderen Users (Social-Graph-Phase-1) - erreicht von
/// Suchergebnissen und der Freundesliste. Zeigt genau EIN Action-Set,
/// abhängig von `relationshipStatus` (siehe
/// `backend/app/schemas/social.py::SocialProfilePublic`). Eigener
/// `Scaffold`/`AppBar` mit Zurück-Button, der die Auswahl zurücksetzt -
/// mirrort `PartyDetailScreen`.
class SocialProfileScreen extends ConsumerWidget {
  final String userId;
  const SocialProfileScreen({super.key, required this.userId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profileAsync = ref.watch(socialProfileProvider(userId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Profile'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(selectedFriendProfileUserIdProvider.notifier).state = null,
        ),
      ),
      body: profileAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(socialProfileProvider(userId)),
            child: const Text('Failed to load profile. Retry'),
          ),
        ),
        data: (profile) => Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              const SizedBox(height: 12),
              const CircleAvatar(radius: 40, child: Icon(Icons.person, size: 40)),
              const SizedBox(height: 16),
              Text(profile.displayName, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
              if (profile.username.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text('@${profile.username}', style: const TextStyle(color: Colors.grey)),
              ],
              if (profile.mutualFriendCount > 0) ...[
                const SizedBox(height: 4),
                Text(
                  '${profile.mutualFriendCount} mutual friend${profile.mutualFriendCount == 1 ? '' : 's'}',
                  style: const TextStyle(color: Colors.grey),
                ),
              ],
              if (profile.relationshipStatus != RelationshipStatus.self_) ...[
                const SizedBox(height: 8),
                // Social-Graph-Phase-3: Sichtbarkeit wird server-seitig via
                // 403 in GET /users/{id}/friends durchgesetzt - client-seitig
                // wird der Link immer gezeigt statt eines fünften
                // Privacy-Felds nur fürs Ausblenden (siehe Plan).
                TextButton(
                  onPressed: () => ref.read(viewingUserFriendsUserIdProvider.notifier).state = profile.userId,
                  child: const Text('View friends'),
                ),
                // Social-Graph-Phase-7: Sichtbarkeit wird server-seitig via
                // 403 auf GET /users/{id}/following/* durchgesetzt (gemäß
                // following_visibility) - der Link wird immer gezeigt.
                TextButton(
                  onPressed: () => ref.read(viewingUserFollowingUserIdProvider.notifier).state = profile.userId,
                  child: const Text('View following'),
                ),
              ],
              const SizedBox(height: 16),
              _ActionSection(profile: profile),
            ],
          ),
        ),
      ),
    );
  }
}

class _ActionSection extends ConsumerWidget {
  final SocialProfile profile;
  const _ActionSection({required this.profile});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    switch (profile.relationshipStatus) {
      case RelationshipStatus.self_:
        return const SizedBox.shrink();
      case RelationshipStatus.none_:
        return _AddFriendButton(profile: profile);
      case RelationshipStatus.requestSent:
        return const Text('Friend request sent', style: TextStyle(color: Colors.grey));
      case RelationshipStatus.requestReceived:
        return _IncomingRequestButtons(profile: profile);
      case RelationshipStatus.friends:
        return _FriendActions(profile: profile);
      case RelationshipStatus.blocked:
        return _UnblockButton(profile: profile);
    }
  }
}

class _AddFriendButton extends ConsumerWidget {
  final SocialProfile profile;
  const _AddFriendButton({required this.profile});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sendState = ref.watch(sendFriendRequestProvider);
    return ElevatedButton.icon(
      icon: const Icon(Icons.person_add),
      label: const Text('Add Friend'),
      onPressed: sendState.isLoading
          ? null
          : () async {
              final messenger = ScaffoldMessenger.of(context);
              try {
                await ref.read(sendFriendRequestProvider.notifier).send(profile.userId);
              } catch (_) {
                messenger.showSnackBar(
                  const SnackBar(content: Text('Failed to send friend request. Please try again.')),
                );
              }
            },
    );
  }
}

class _IncomingRequestButtons extends ConsumerWidget {
  final SocialProfile profile;
  const _IncomingRequestButtons({required this.profile});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final inboxAsync = ref.watch(friendRequestsProvider);
    return inboxAsync.when(
      loading: () => const CircularProgressIndicator(),
      error: (err, st) => const Text('Failed to load request.'),
      data: (inbox) {
        final incoming = inbox.incoming.where((r) => r.otherUserId == profile.userId).toList();
        if (incoming.isEmpty) return const SizedBox.shrink();
        final requestId = incoming.first.id;
        final respondState = ref.watch(respondFriendRequestProvider);
        return Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ElevatedButton(
              onPressed: respondState.isLoading ? null : () => _respond(context, ref, requestId, accept: true),
              child: const Text('Accept'),
            ),
            const SizedBox(width: 12),
            OutlinedButton(
              onPressed: respondState.isLoading ? null : () => _respond(context, ref, requestId, accept: false),
              child: const Text('Decline'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _respond(BuildContext context, WidgetRef ref, String requestId, {required bool accept}) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      if (accept) {
        await ref.read(respondFriendRequestProvider.notifier).accept(requestId);
      } else {
        await ref.read(respondFriendRequestProvider.notifier).decline(requestId);
      }
      ref.invalidate(socialProfileProvider(profile.userId));
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to respond. Please try again.')));
    }
  }
}

class _FriendActions extends ConsumerWidget {
  final SocialProfile profile;
  const _FriendActions({required this.profile});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final removeState = ref.watch(removeFriendProvider);
    return Column(
      children: [
        const Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [Icon(Icons.check_circle, color: Colors.green), SizedBox(width: 8), Text('Friends')],
        ),
        const SizedBox(height: 16),
        OutlinedButton(
          onPressed: removeState.isLoading ? null : () => _confirmRemove(context, ref),
          child: const Text('Remove Friend'),
        ),
        TextButton(
          onPressed: () => _confirmBlock(context, ref),
          child: const Text('Block', style: TextStyle(color: Colors.red)),
        ),
      ],
    );
  }

  Future<void> _confirmRemove(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Remove ${profile.displayName}?'),
        content: const Text('You will no longer be friends.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Remove')),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(removeFriendProvider.notifier).remove(profile.userId);
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to remove friend. Please try again.')));
    }
  }

  Future<void> _confirmBlock(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Block ${profile.displayName}?'),
        content: const Text('This ends your friendship and prevents future friend requests.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Block')),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(blockUserProvider.notifier).block(profile.userId);
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to block. Please try again.')));
    }
  }
}

class _UnblockButton extends ConsumerWidget {
  final SocialProfile profile;
  const _UnblockButton({required this.profile});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final unblockState = ref.watch(unblockUserProvider);
    return Column(
      children: [
        const Text('Blocked', style: TextStyle(color: Colors.red)),
        const SizedBox(height: 12),
        OutlinedButton(
          onPressed: unblockState.isLoading
              ? null
              : () async {
                  final messenger = ScaffoldMessenger.of(context);
                  try {
                    await ref.read(unblockUserProvider.notifier).unblock(profile.userId);
                  } catch (_) {
                    messenger.showSnackBar(
                      const SnackBar(content: Text('Failed to unblock. Please try again.')),
                    );
                  }
                },
          child: const Text('Unblock'),
        ),
      ],
    );
  }
}
