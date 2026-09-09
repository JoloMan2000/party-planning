import 'social_profile.dart';

/// Ein Suchtreffer (`backend/app/schemas/social.py::UserSearchResultPublic`).
class UserSearchResult {
  final String userId;
  final String username;
  final String displayName;
  final String profileImage;
  final RelationshipStatus relationshipStatus;
  final int mutualFriendCount;

  const UserSearchResult({
    required this.userId,
    required this.username,
    required this.displayName,
    required this.profileImage,
    required this.relationshipStatus,
    required this.mutualFriendCount,
  });

  factory UserSearchResult.fromJson(Map<String, dynamic> json) => UserSearchResult(
        userId: json['user_id'] as String,
        username: (json['username'] as String?) ?? '',
        displayName: json['display_name'] as String,
        profileImage: (json['profile_image'] as String?) ?? '',
        relationshipStatus: relationshipStatusFromWire(json['relationship_status'] as String),
        mutualFriendCount: (json['mutual_friend_count'] as int?) ?? 0,
      );
}
