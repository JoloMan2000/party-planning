import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/friend.dart';
import '../models/friend_invite_result.dart';
import '../state/auth_providers.dart';
import '../state/social_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Social-Graph-Phase-2: Freunde-Mehrfachauswahl zum Einladen in eine Party -
/// als `showModalBottomSheet` geöffnet (mirrort
/// `discover_screen.dart::_NotInterestedReasonSheet`), statt eines neuen
/// Screens/Boolean-Flags in `main.dart`'s Routing-Kette, da es sich um eine
/// transiente Aktion handelt. Erstes `Checkbox`-Vorkommen in dieser
/// Codebase - der bestehende Set-Toggle-Idiom
/// (`discovery_preferences_screen.dart`, `_PublishToDiscoverSection`) wird
/// hier auf eine Freundesliste statt Chips angewandt.
class FriendPickerSheet extends ConsumerStatefulWidget {
  final String partyId;
  const FriendPickerSheet({super.key, required this.partyId});

  @override
  ConsumerState<FriendPickerSheet> createState() => _FriendPickerSheetState();
}

class _FriendPickerSheetState extends ConsumerState<FriendPickerSheet> {
  final Set<String> _selected = {};
  bool _submitting = false;

  @override
  Widget build(BuildContext context) {
    final friendsAsync = ref.watch(friendsProvider);
    final guestsAsync = ref.watch(partyGuestsProvider(widget.partyId));

    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 20,
          right: 20,
          top: 20,
          bottom: MediaQuery.of(context).viewInsets.bottom + 20,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Invite Friends', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            Flexible(
              child: friendsAsync.when(
                loading: () => const Center(child: Padding(padding: EdgeInsets.all(20), child: CircularProgressIndicator())),
                error: (err, st) => const Padding(
                  padding: EdgeInsets.all(20),
                  child: Text('Failed to load friends.'),
                ),
                data: (friends) => guestsAsync.when(
                  loading: () => const Center(child: Padding(padding: EdgeInsets.all(20), child: CircularProgressIndicator())),
                  error: (err, st) => const Padding(
                    padding: EdgeInsets.all(20),
                    child: Text('Failed to load guest list.'),
                  ),
                  data: (guests) {
                    final memberIds = guests.guests.map((g) => g.userId).toSet();
                    final available = friends.where((f) => !memberIds.contains(f.userId)).toList();
                    if (available.isEmpty) {
                      return const Padding(
                        padding: EdgeInsets.symmetric(vertical: 20),
                        child: Text('All your friends are already invited, or you have no friends yet.'),
                      );
                    }
                    return ListView(
                      shrinkWrap: true,
                      children: available.map((f) => _SelectableFriendTile(
                            friend: f,
                            selected: _selected.contains(f.userId),
                            onChanged: (selected) => setState(() {
                              if (selected) {
                                _selected.add(f.userId);
                              } else {
                                _selected.remove(f.userId);
                              }
                            }),
                          )).toList(),
                    );
                  },
                ),
              ),
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _selected.isEmpty || _submitting ? null : _submit,
              child: _submitting
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : Text('Invite ${_selected.length} Friend${_selected.length == 1 ? '' : 's'}'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _submit() async {
    setState(() => _submitting = true);
    try {
      final result = await ref.read(inviteFriendsProvider.notifier).invite(widget.partyId, friendUserIds: _selected.toList());
      if (mounted) Navigator.pop(context, result);
    } catch (_) {
      if (mounted) setState(() => _submitting = false);
    }
  }
}

class _SelectableFriendTile extends StatelessWidget {
  final Friend friend;
  final bool selected;
  final ValueChanged<bool> onChanged;
  const _SelectableFriendTile({required this.friend, required this.selected, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.person)),
        title: Text(friend.displayName),
        subtitle: friend.username.isEmpty ? null : Text('@${friend.username}'),
        trailing: Checkbox(value: selected, onChanged: (v) => onChanged(v ?? false)),
        onTap: () => onChanged(!selected),
      ),
    );
  }
}

/// Baut eine kurze, für den User verständliche Zusammenfassung eines
/// `FriendInviteResponse` (z.B. "Invited 2 friends. 1 already invited.")
/// für die SnackBar nach dem Schließen von [FriendPickerSheet].
String summarizeFriendInviteResult(FriendInviteResponse result) {
  final invited = result.results.where((r) => r.status == FriendInviteItemStatus.invited).length;
  final alreadyInvited = result.results
      .where((r) => r.status == FriendInviteItemStatus.alreadyInvited || r.status == FriendInviteItemStatus.alreadyMember)
      .length;
  final notFriends = result.results.where((r) => r.status == FriendInviteItemStatus.notAFriend).length;

  final parts = <String>[];
  if (invited > 0) parts.add('Invited $invited friend${invited == 1 ? '' : 's'}.');
  if (alreadyInvited > 0) parts.add('$alreadyInvited already invited.');
  if (notFriends > 0) parts.add('$notFriends not a friend.');
  return parts.isEmpty ? 'No invites sent.' : parts.join(' ');
}
