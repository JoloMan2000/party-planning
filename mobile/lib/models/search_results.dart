import 'user_search_result.dart';

/// Ergebnis von `GET /api/v1/search` (Social-Graph-Phase-6,
/// `backend/app/schemas/social.py::SearchResponse`) - drei getrennte,
/// typisierte Trefferlisten. Die `users`-Liste nutzt das bestehende
/// `UserSearchResult`-Modell wieder.

/// Ein Organizer-Suchtreffer (`OrganizerSearchResultPublic`). `Organizer`
/// hat kein `username`/Foto (Phase 4 weggelassen), daher nur diese Felder.
class OrganizerSearchResult {
  final String organizerId;
  final String displayName;
  final bool verified;
  final int followerCount;
  final bool isFollowing;

  const OrganizerSearchResult({
    required this.organizerId,
    required this.displayName,
    required this.verified,
    required this.followerCount,
    required this.isFollowing,
  });

  factory OrganizerSearchResult.fromJson(Map<String, dynamic> json) => OrganizerSearchResult(
        organizerId: json['organizer_id'] as String,
        displayName: json['display_name'] as String,
        verified: (json['verified'] as bool?) ?? false,
        followerCount: (json['follower_count'] as int?) ?? 0,
        isFollowing: (json['is_following'] as bool?) ?? false,
      );
}

/// Ein Event-Suchtreffer (`EventSearchResultPublic`). `organizerName` ist
/// der Anzeigename des Host-Users (es gibt noch kein `Party.organizer_id`).
class EventSearchResult {
  final String partyId;
  final String name;
  final DateTime? startsAt;
  final String location;
  final String coverImage;
  final String eventType;
  final String organizerName;
  final bool isFollowing;

  const EventSearchResult({
    required this.partyId,
    required this.name,
    required this.startsAt,
    required this.location,
    required this.coverImage,
    required this.eventType,
    required this.organizerName,
    required this.isFollowing,
  });

  factory EventSearchResult.fromJson(Map<String, dynamic> json) => EventSearchResult(
        partyId: json['party_id'] as String,
        name: json['name'] as String,
        startsAt: json['starts_at'] == null ? null : DateTime.parse(json['starts_at'] as String),
        location: (json['location'] as String?) ?? '',
        coverImage: (json['cover_image'] as String?) ?? '',
        eventType: (json['event_type'] as String?) ?? '',
        organizerName: (json['organizer_name'] as String?) ?? '',
        isFollowing: (json['is_following'] as bool?) ?? false,
      );
}

class SearchResults {
  final List<UserSearchResult> users;
  final List<OrganizerSearchResult> organizers;
  final List<EventSearchResult> events;

  const SearchResults({
    required this.users,
    required this.organizers,
    required this.events,
  });

  bool get isEmpty => users.isEmpty && organizers.isEmpty && events.isEmpty;

  factory SearchResults.fromJson(Map<String, dynamic> json) => SearchResults(
        users: ((json['users'] as List?) ?? const [])
            .map((e) => UserSearchResult.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
        organizers: ((json['organizers'] as List?) ?? const [])
            .map((e) => OrganizerSearchResult.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
        events: ((json['events'] as List?) ?? const [])
            .map((e) => EventSearchResult.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
      );
}
