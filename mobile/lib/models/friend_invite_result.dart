/// Spiegelbild der `status`-Werte aus
/// `backend/app/routers/parties.py::invite_friends`.
enum FriendInviteItemStatus { invited, notAFriend, alreadyMember, alreadyInvited }

const _friendInviteStatusWireValues = {
  'invited': FriendInviteItemStatus.invited,
  'not_a_friend': FriendInviteItemStatus.notAFriend,
  'already_member': FriendInviteItemStatus.alreadyMember,
  'already_invited': FriendInviteItemStatus.alreadyInvited,
};

FriendInviteItemStatus friendInviteItemStatusFromWire(String s) =>
    _friendInviteStatusWireValues[s] ?? FriendInviteItemStatus.notAFriend;

/// Ein Ergebnis-Eintrag aus `POST /parties/{id}/invitations/friends`
/// (Social-Graph-Phase-2) - ein schlechter Eintrag bricht den Batch nicht
/// ab, jede angefragte `friend_user_id` bekommt ihr eigenes Ergebnis.
class FriendInviteResultItem {
  final String userId;
  final FriendInviteItemStatus status;
  final String? invitationId;

  const FriendInviteResultItem({required this.userId, required this.status, required this.invitationId});

  factory FriendInviteResultItem.fromJson(Map<String, dynamic> json) => FriendInviteResultItem(
        userId: json['user_id'] as String,
        status: friendInviteItemStatusFromWire(json['status'] as String),
        invitationId: json['invitation_id'] as String?,
      );
}

class FriendInviteResponse {
  final List<FriendInviteResultItem> results;

  const FriendInviteResponse({required this.results});

  factory FriendInviteResponse.fromJson(Map<String, dynamic> json) => FriendInviteResponse(
        results: (json['results'] as List)
            .map((e) => FriendInviteResultItem.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
      );
}
