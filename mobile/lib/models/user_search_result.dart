import 'social_profile.dart';

/// Ein Suchtreffer (`backend/app/schemas/social.py::UserSearchResultPublic`).
class UserSearchResult {
  final String userId;
  final String username;
  final String displayName;
  final String profileImage;
  final RelationshipStatus relationshipStatus;

  const UserSearchResult({
    required this.userId,
    required this.username,
    required this.displayName,
    required this.profileImage,
    required this.relationshipStatus,
  });

  factory UserSearchResult.fromJson(Map<String, dynamic> json) => UserSearchResult(
        userId: json['user_id'] as String,
        username: (json['username'] as String?) ?? '',
        displayName: json['display_name'] as String,
        profileImage: (json['profile_image'] as String?) ?? '',
        relationshipStatus: relationshipStatusFromWire(json['relationship_status'] as String),
      );
}
