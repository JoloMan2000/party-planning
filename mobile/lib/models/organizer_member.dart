/// Eine Organizer-Mitgliedschaft
/// (`backend/app/schemas/organizers.py::OrganizerMemberPublic`,
/// Social-Graph-Phase-4). [role] ist einer der fünf `OrganizerRole`-Werte
/// (`owner`, `admin`, `editor`, `viewer`, `member`).
class OrganizerMember {
  final String organizerId;
  final String userId;
  final String role;
  final DateTime createdAt;
  final DateTime updatedAt;

  const OrganizerMember({
    required this.organizerId,
    required this.userId,
    required this.role,
    required this.createdAt,
    required this.updatedAt,
  });

  factory OrganizerMember.fromJson(Map<String, dynamic> json) => OrganizerMember(
        organizerId: json['organizer_id'] as String,
        userId: json['user_id'] as String,
        role: json['role'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
        updatedAt: DateTime.parse(json['updated_at'] as String),
      );
}
