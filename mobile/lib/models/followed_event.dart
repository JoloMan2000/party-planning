/// Eine Zeile in `GET /api/v1/me/following/events`
/// (`backend/app/schemas/following.py::FollowedEventPublic`,
/// Social-Graph-Phase-5). Enthält nur veröffentlichte Events - Follows auf
/// inzwischen unveröffentlichte Partys blendet das Backend aus (nicht
/// gelöscht). `Follow Event` ist strikt getrennt von `Going`/`Maybe` -
/// reines Update-Interesse, kein Kalendereintrag.
class FollowedEvent {
  final String partyId;
  final String name;
  final DateTime? startsAt;
  final String location;
  final String eventType;
  final DateTime followedAt;

  const FollowedEvent({
    required this.partyId,
    required this.name,
    required this.startsAt,
    required this.location,
    required this.eventType,
    required this.followedAt,
  });

  factory FollowedEvent.fromJson(Map<String, dynamic> json) => FollowedEvent(
        partyId: json['party_id'] as String,
        name: json['name'] as String,
        startsAt: json['starts_at'] == null ? null : DateTime.parse(json['starts_at'] as String),
        location: (json['location'] as String?) ?? '',
        eventType: (json['event_type'] as String?) ?? '',
        followedAt: DateTime.parse(json['followed_at'] as String),
      );
}
