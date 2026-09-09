/// Spiegelbild der `relationship_status`-Werte aus
/// `backend/app/routers/social.py::_relationship_status`.
enum RelationshipStatus { self_, friends, requestSent, requestReceived, blocked, none_ }

const _relationshipStatusWireValues = {
  'self': RelationshipStatus.self_,
  'friends': RelationshipStatus.friends,
  'request_sent': RelationshipStatus.requestSent,
  'request_received': RelationshipStatus.requestReceived,
  'blocked': RelationshipStatus.blocked,
  'none': RelationshipStatus.none_,
};

RelationshipStatus relationshipStatusFromWire(String s) =>
    _relationshipStatusWireValues[s] ?? RelationshipStatus.none_;

/// `backend/app/schemas/social.py::SocialProfilePublic` - bewusst OHNE
/// E-Mail/Geburtsdatum/Standort (Spec §26).
class SocialProfile {
  final String userId;
  final String username;
  final String displayName;
  final String profileImage;
  final RelationshipStatus relationshipStatus;
  final int mutualFriendCount;

  const SocialProfile({
    required this.userId,
    required this.username,
    required this.displayName,
    required this.profileImage,
    required this.relationshipStatus,
    required this.mutualFriendCount,
  });

  factory SocialProfile.fromJson(Map<String, dynamic> json) => SocialProfile(
        userId: json['user_id'] as String,
        username: (json['username'] as String?) ?? '',
        displayName: json['display_name'] as String,
        profileImage: (json['profile_image'] as String?) ?? '',
        relationshipStatus: relationshipStatusFromWire(json['relationship_status'] as String),
        mutualFriendCount: (json['mutual_friend_count'] as int?) ?? 0,
      );
}
