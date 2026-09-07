/// Antwort auf `POST /api/v1/discover/{partyId}/action`
/// (`backend/app/schemas/discover.py::DiscoverActionResponse`).
class DiscoverActionResult {
  final String partyId;
  final String action;
  final String? membershipRole;
  final String? membershipRsvpStatus;

  const DiscoverActionResult({
    required this.partyId,
    required this.action,
    required this.membershipRole,
    required this.membershipRsvpStatus,
  });

  factory DiscoverActionResult.fromJson(Map<String, dynamic> json) => DiscoverActionResult(
        partyId: json['party_id'] as String,
        action: json['action'] as String,
        membershipRole: json['membership_role'] as String?,
        membershipRsvpStatus: json['membership_rsvp_status'] as String?,
      );
}
