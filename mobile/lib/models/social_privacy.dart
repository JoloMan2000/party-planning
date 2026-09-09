/// Social-Graph-Phase-3 - Verhaltens-Policies, die steuern, was ANDERE User
/// über einen sehen/tun dürfen (`backend/app/schemas/social.py::SocialPrivacyPublic`).
class SocialPrivacy {
  final String friendListVisibility; // "nobody" | "friends" | "everyone"
  final String friendRequestPrivacy; // "nobody" | "everyone"
  final bool discoverableByUsername;
  final bool discoverableByName;

  const SocialPrivacy({
    required this.friendListVisibility,
    required this.friendRequestPrivacy,
    required this.discoverableByUsername,
    required this.discoverableByName,
  });

  factory SocialPrivacy.fromJson(Map<String, dynamic> json) => SocialPrivacy(
        friendListVisibility: json['friend_list_visibility'] as String,
        friendRequestPrivacy: json['friend_request_privacy'] as String,
        discoverableByUsername: json['discoverable_by_username'] as bool,
        discoverableByName: json['discoverable_by_name'] as bool,
      );

  Map<String, dynamic> toJson() => {
        'friend_list_visibility': friendListVisibility,
        'friend_request_privacy': friendRequestPrivacy,
        'discoverable_by_username': discoverableByUsername,
        'discoverable_by_name': discoverableByName,
      };

  SocialPrivacy copyWith({
    String? friendListVisibility,
    String? friendRequestPrivacy,
    bool? discoverableByUsername,
    bool? discoverableByName,
  }) =>
      SocialPrivacy(
        friendListVisibility: friendListVisibility ?? this.friendListVisibility,
        friendRequestPrivacy: friendRequestPrivacy ?? this.friendRequestPrivacy,
        discoverableByUsername: discoverableByUsername ?? this.discoverableByUsername,
        discoverableByName: discoverableByName ?? this.discoverableByName,
      );
}
