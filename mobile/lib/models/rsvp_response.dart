/// Antwort von `PUT /api/v1/invitations/{id}/rsvp`
/// (`backend/app/schemas/accounts.py::RsvpResponse`).
class RsvpResponse {
  final String invitationId;
  final String partyId;
  final String status;
  final DateTime? respondedAt;
  final int version;

  const RsvpResponse({
    required this.invitationId,
    required this.partyId,
    required this.status,
    required this.respondedAt,
    required this.version,
  });

  factory RsvpResponse.fromJson(Map<String, dynamic> json) => RsvpResponse(
        invitationId: json['invitation_id'] as String,
        partyId: json['party_id'] as String,
        status: json['status'] as String,
        respondedAt: json['responded_at'] == null ? null : DateTime.parse(json['responded_at'] as String),
        version: json['version'] as int,
      );
}
