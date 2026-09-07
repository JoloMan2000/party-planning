/// Eine Karte im Discover-Swipe-Deck (`backend/app/schemas/discover.py::DiscoverCardPublic`).
class DiscoverCard {
  final String partyId;
  final String name;
  final String description;
  final DateTime? startsAt;
  final String location;
  final String coverImage;
  final String eventType;
  final List<String> interestTags;
  final String hostDisplayName;
  final double matchScore;

  const DiscoverCard({
    required this.partyId,
    required this.name,
    required this.description,
    required this.startsAt,
    required this.location,
    required this.coverImage,
    required this.eventType,
    required this.interestTags,
    required this.hostDisplayName,
    required this.matchScore,
  });

  factory DiscoverCard.fromJson(Map<String, dynamic> json) => DiscoverCard(
        partyId: json['party_id'] as String,
        name: json['name'] as String,
        description: (json['description'] as String?) ?? '',
        startsAt: json['starts_at'] == null ? null : DateTime.parse(json['starts_at'] as String),
        location: (json['location'] as String?) ?? '',
        coverImage: (json['cover_image'] as String?) ?? '',
        eventType: (json['event_type'] as String?) ?? '',
        interestTags: (json['interest_tags'] as List?)?.cast<String>() ?? const [],
        hostDisplayName: (json['host_display_name'] as String?) ?? '',
        matchScore: (json['match_score'] as num).toDouble(),
      );
}
