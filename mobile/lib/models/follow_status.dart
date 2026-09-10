// Follow-Status-Antworten der Following-Domain (Social-Graph-Phase-5,
// `backend/app/schemas/following.py`). `following` ist immer aus Sicht des
// aufrufenden Users; `followerCount` die serverseitige Gesamtzahl.

/// Antwort auf `POST`/`GET /api/v1/organizers/{id}/follow[ers]`
/// (`OrganizerFollowStatusResponse`).
class OrganizerFollowStatus {
  final String organizerId;
  final int followerCount;
  final bool following;

  const OrganizerFollowStatus({
    required this.organizerId,
    required this.followerCount,
    required this.following,
  });

  factory OrganizerFollowStatus.fromJson(Map<String, dynamic> json) => OrganizerFollowStatus(
        organizerId: json['organizer_id'] as String,
        followerCount: (json['follower_count'] as int?) ?? 0,
        following: (json['following'] as bool?) ?? false,
      );
}

/// Antwort auf `POST`/`GET /api/v1/events/{party_id}/follow[ers]`
/// (`EventFollowStatusResponse`). Event = eine veröffentlichte Party,
/// adressiert über [partyId].
class EventFollowStatus {
  final String partyId;
  final int followerCount;
  final bool following;

  const EventFollowStatus({
    required this.partyId,
    required this.followerCount,
    required this.following,
  });

  factory EventFollowStatus.fromJson(Map<String, dynamic> json) => EventFollowStatus(
        partyId: json['party_id'] as String,
        followerCount: (json['follower_count'] as int?) ?? 0,
        following: (json['following'] as bool?) ?? false,
      );
}
