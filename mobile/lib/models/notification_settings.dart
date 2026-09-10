/// Die fünf Notification-Kategorie-Schalter eines Users (Social-Graph-
/// Phase-8, `backend/app/schemas/notifications.py::NotificationSettingsPublic`).
/// Full-Replace beim Speichern (der Client hält stets alle fünf Werte) -
/// mirrort `SocialPrivacy` / `DiscoveryPreferences`.
class NotificationSettings {
  final bool friendRequests;
  final bool partyInvitations;
  final bool organizerUpdates;
  final bool followedEventUpdates;
  final bool nearbyDiscover;

  const NotificationSettings({
    required this.friendRequests,
    required this.partyInvitations,
    required this.organizerUpdates,
    required this.followedEventUpdates,
    required this.nearbyDiscover,
  });

  factory NotificationSettings.fromJson(Map<String, dynamic> json) => NotificationSettings(
        friendRequests: (json['friend_requests'] as bool?) ?? true,
        partyInvitations: (json['party_invitations'] as bool?) ?? true,
        organizerUpdates: (json['organizer_updates'] as bool?) ?? true,
        followedEventUpdates: (json['followed_event_updates'] as bool?) ?? true,
        nearbyDiscover: (json['nearby_discover'] as bool?) ?? true,
      );

  Map<String, dynamic> toJson() => {
        'friend_requests': friendRequests,
        'party_invitations': partyInvitations,
        'organizer_updates': organizerUpdates,
        'followed_event_updates': followedEventUpdates,
        'nearby_discover': nearbyDiscover,
      };

  NotificationSettings copyWith({
    bool? friendRequests,
    bool? partyInvitations,
    bool? organizerUpdates,
    bool? followedEventUpdates,
    bool? nearbyDiscover,
  }) =>
      NotificationSettings(
        friendRequests: friendRequests ?? this.friendRequests,
        partyInvitations: partyInvitations ?? this.partyInvitations,
        organizerUpdates: organizerUpdates ?? this.organizerUpdates,
        followedEventUpdates: followedEventUpdates ?? this.followedEventUpdates,
        nearbyDiscover: nearbyDiscover ?? this.nearbyDiscover,
      );
}
