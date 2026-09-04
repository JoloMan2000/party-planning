/// Ein Gast in der Gästeliste (`backend/app/schemas/accounts.py::GuestListEntry`).
class GuestListEntry {
  final String userId;
  final String displayName;
  final String email;
  final String role;
  final String rsvpStatus;
  final DateTime joinedAt;

  const GuestListEntry({
    required this.userId,
    required this.displayName,
    required this.email,
    required this.role,
    required this.rsvpStatus,
    required this.joinedAt,
  });

  factory GuestListEntry.fromJson(Map<String, dynamic> json) => GuestListEntry(
        userId: json['user_id'] as String,
        displayName: json['display_name'] as String,
        email: json['email'] as String,
        role: json['role'] as String,
        rsvpStatus: json['rsvp_status'] as String,
        joinedAt: DateTime.parse(json['joined_at'] as String),
      );
}

/// Antwort von `GET /api/v1/parties/{id}/guests`
/// (`backend/app/schemas/accounts.py::PartyGuestsResponse`).
class PartyGuestsResponse {
  final List<GuestListEntry> guests;
  final Map<String, int> counts;

  const PartyGuestsResponse({required this.guests, required this.counts});

  factory PartyGuestsResponse.fromJson(Map<String, dynamic> json) => PartyGuestsResponse(
        guests: (json['guests'] as List)
            .map((e) => GuestListEntry.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
        counts: (json['counts'] as Map).cast<String, int>(),
      );
}
