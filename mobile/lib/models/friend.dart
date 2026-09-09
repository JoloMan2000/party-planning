/// Ein bestätigter Freund (`backend/app/schemas/social.py::FriendPublic`).
class Friend {
  final String userId;
  final String username;
  final String displayName;
  final String profileImage;
  final DateTime friendsSince;

  const Friend({
    required this.userId,
    required this.username,
    required this.displayName,
    required this.profileImage,
    required this.friendsSince,
  });

  factory Friend.fromJson(Map<String, dynamic> json) => Friend(
        userId: json['user_id'] as String,
        username: (json['username'] as String?) ?? '',
        displayName: json['display_name'] as String,
        profileImage: (json['profile_image'] as String?) ?? '',
        friendsSince: DateTime.parse(json['friends_since'] as String),
      );
}
