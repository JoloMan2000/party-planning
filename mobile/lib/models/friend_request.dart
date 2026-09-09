/// Spiegelbild von `social.domain.FriendRequestStatus`.
enum FriendRequestStatus { pending, accepted, declined, cancelled, expired }

FriendRequestStatus friendRequestStatusFromWire(String s) => FriendRequestStatus.values.firstWhere(
      (v) => v.name == s,
      orElse: () => FriendRequestStatus.pending,
    );

/// Eine Freundschaftsanfrage, aus Sicht des jeweils aufrufenden Users
/// (`direction`/`other*`-Felder - siehe
/// `backend/app/schemas/social.py::FriendRequestPublic`).
class FriendRequest {
  final String id;
  final String direction; // "incoming" | "outgoing"
  final FriendRequestStatus status;
  final int version;
  final String otherUserId;
  final String otherUsername;
  final String otherDisplayName;
  final String otherProfileImage;
  final DateTime createdAt;
  final DateTime? respondedAt;

  const FriendRequest({
    required this.id,
    required this.direction,
    required this.status,
    required this.version,
    required this.otherUserId,
    required this.otherUsername,
    required this.otherDisplayName,
    required this.otherProfileImage,
    required this.createdAt,
    required this.respondedAt,
  });

  factory FriendRequest.fromJson(Map<String, dynamic> json) => FriendRequest(
        id: json['id'] as String,
        direction: json['direction'] as String,
        status: friendRequestStatusFromWire(json['status'] as String),
        version: json['version'] as int,
        otherUserId: json['other_user_id'] as String,
        otherUsername: (json['other_username'] as String?) ?? '',
        otherDisplayName: json['other_display_name'] as String,
        otherProfileImage: (json['other_profile_image'] as String?) ?? '',
        createdAt: DateTime.parse(json['created_at'] as String),
        respondedAt: json['responded_at'] == null ? null : DateTime.parse(json['responded_at'] as String),
      );
}

/// `GET /me/friend-requests` (`FriendRequestsInboxResponse`).
class FriendRequestsInbox {
  final List<FriendRequest> incoming;
  final List<FriendRequest> outgoing;

  const FriendRequestsInbox({required this.incoming, required this.outgoing});

  factory FriendRequestsInbox.fromJson(Map<String, dynamic> json) => FriendRequestsInbox(
        incoming: (json['incoming'] as List)
            .map((e) => FriendRequest.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
        outgoing: (json['outgoing'] as List)
            .map((e) => FriendRequest.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
      );
}
