/// Antwort auf `POST /api/v1/discover/{partyId}/action`
/// (`backend/app/schemas/discover.py::DiscoverActionResponse`).
class DiscoverActionResult {
  final String partyId;
  final String action;
  final String reason;
  final String? membershipRole;
  final String? membershipRsvpStatus;

  const DiscoverActionResult({
    required this.partyId,
    required this.action,
    required this.reason,
    required this.membershipRole,
    required this.membershipRsvpStatus,
  });

  factory DiscoverActionResult.fromJson(Map<String, dynamic> json) => DiscoverActionResult(
        partyId: json['party_id'] as String,
        action: json['action'] as String,
        reason: (json['reason'] as String?) ?? '',
        membershipRole: json['membership_role'] as String?,
        membershipRsvpStatus: json['membership_rsvp_status'] as String?,
      );
}

/// Spiegelbild von `accounts.domain.DiscoverNotInterestedReason` - nur bei
/// `action == "not_interested"` gültig (siehe
/// `backend/app/routers/discover.py::act_on_discover_card`).
enum DiscoverNotInterestedReason { wrongVibe, tooFar, badTiming, notInterestedInOrganizer, other }

const _notInterestedReasonWireValues = {
  DiscoverNotInterestedReason.wrongVibe: 'wrong_vibe',
  DiscoverNotInterestedReason.tooFar: 'too_far',
  DiscoverNotInterestedReason.badTiming: 'bad_timing',
  DiscoverNotInterestedReason.notInterestedInOrganizer: 'not_interested_in_organizer',
  DiscoverNotInterestedReason.other: 'other',
};

extension DiscoverNotInterestedReasonWire on DiscoverNotInterestedReason {
  String get wireValue => _notInterestedReasonWireValues[this]!;

  String get label {
    switch (this) {
      case DiscoverNotInterestedReason.wrongVibe:
        return 'Not my vibe';
      case DiscoverNotInterestedReason.tooFar:
        return 'Too far away';
      case DiscoverNotInterestedReason.badTiming:
        return 'Bad timing';
      case DiscoverNotInterestedReason.notInterestedInOrganizer:
        return 'Not interested in this organizer';
      case DiscoverNotInterestedReason.other:
        return 'Other';
    }
  }
}
