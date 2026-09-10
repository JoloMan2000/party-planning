/// Ein Organizer (`backend/app/schemas/organizers.py::OrganizerPublic`,
/// Social-Graph-Phase-4). Ein von einem User besessenes, ggf. admin-
/// verifiziertes Veranstalter-Profil - Discover-Publishing ist an einen
/// verifizierten Organizer gebunden (löste `User.is_verified` ab).
///
/// [myRole] ist nur dort befüllt, wo die eigene Mitgliedschaft des Callers
/// ohnehin bekannt ist (`GET /organizers/mine`, `GET /organizers/{id}`) -
/// bei gefolgten Organizern anderer Nutzer ist es `null`.
class Organizer {
  final String id;
  final String ownerUserId;
  final String displayName;
  final String organizerType;
  final String verificationStatus;
  final String description;
  final String websiteUrl;
  final String? myRole;
  final DateTime createdAt;
  final DateTime updatedAt;

  const Organizer({
    required this.id,
    required this.ownerUserId,
    required this.displayName,
    required this.organizerType,
    required this.verificationStatus,
    required this.description,
    required this.websiteUrl,
    required this.myRole,
    required this.createdAt,
    required this.updatedAt,
  });

  bool get isVerified => verificationStatus == 'verified';

  factory Organizer.fromJson(Map<String, dynamic> json) => Organizer(
        id: json['id'] as String,
        ownerUserId: json['owner_user_id'] as String,
        displayName: json['display_name'] as String,
        organizerType: (json['organizer_type'] as String?) ?? '',
        verificationStatus: (json['verification_status'] as String?) ?? 'unverified',
        description: (json['description'] as String?) ?? '',
        websiteUrl: (json['website_url'] as String?) ?? '',
        myRole: json['my_role'] as String?,
        createdAt: DateTime.parse(json['created_at'] as String),
        updatedAt: DateTime.parse(json['updated_at'] as String),
      );
}
