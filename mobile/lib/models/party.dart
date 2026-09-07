/// Eine Account-basierte Party (`backend/app/schemas/accounts.py::PartyPublic`)
/// - bewusst getrennt vom alten Singleton-`PartySettings`-Modell des
/// anonymen Gast-Wizards (siehe Phase-3-Plan Entscheidung #3).
class Party {
  final String id;
  final String hostUserId;
  final String name;
  final String description;
  final DateTime? startsAt;
  final String location;
  final String coverImage;
  final bool isPublished;
  final String eventType;
  final List<String> interestTags;
  final int maxGuests;
  final bool hostIsVerified;
  final String? myDiscoverAction;
  final DateTime createdAt;
  final DateTime updatedAt;

  const Party({
    required this.id,
    required this.hostUserId,
    required this.name,
    required this.description,
    required this.startsAt,
    required this.location,
    this.coverImage = '',
    this.isPublished = false,
    this.eventType = '',
    this.interestTags = const [],
    this.maxGuests = 0,
    this.hostIsVerified = false,
    this.myDiscoverAction,
    required this.createdAt,
    required this.updatedAt,
  });

  factory Party.fromJson(Map<String, dynamic> json) => Party(
        id: json['id'] as String,
        hostUserId: json['host_user_id'] as String,
        name: json['name'] as String,
        description: (json['description'] as String?) ?? '',
        startsAt: json['starts_at'] == null ? null : DateTime.parse(json['starts_at'] as String),
        location: (json['location'] as String?) ?? '',
        coverImage: (json['cover_image'] as String?) ?? '',
        isPublished: (json['is_published'] as bool?) ?? false,
        eventType: (json['event_type'] as String?) ?? '',
        interestTags: (json['interest_tags'] as List?)?.cast<String>() ?? const [],
        maxGuests: (json['max_guests'] as int?) ?? 0,
        hostIsVerified: (json['host_is_verified'] as bool?) ?? false,
        myDiscoverAction: json['my_discover_action'] as String?,
        createdAt: DateTime.parse(json['created_at'] as String),
        updatedAt: DateTime.parse(json['updated_at'] as String),
      );
}
