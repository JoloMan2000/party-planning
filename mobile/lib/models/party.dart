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
  final DateTime createdAt;
  final DateTime updatedAt;

  const Party({
    required this.id,
    required this.hostUserId,
    required this.name,
    required this.description,
    required this.startsAt,
    required this.location,
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
        createdAt: DateTime.parse(json['created_at'] as String),
        updatedAt: DateTime.parse(json['updated_at'] as String),
      );
}
