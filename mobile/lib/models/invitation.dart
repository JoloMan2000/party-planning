/// Spiegelbild von `accounts.domain.RsvpStatus` (auch der Invitation-
/// Status selbst nutzt dieselben Werte, siehe `InvitationPublic.status`).
enum InvitationStatus { pending, accepted, tentative, declined, revoked, expired }

InvitationStatus invitationStatusFromWire(String s) => InvitationStatus.values.firstWhere(
      (v) => v.name == s,
      orElse: () => InvitationStatus.pending,
    );

/// Eine Einladung (`backend/app/schemas/accounts.py::InvitationPublic`).
class Invitation {
  final String id;
  final String partyId;
  final String hostUserId;
  final String invitedUserId;
  final InvitationStatus status;
  final String invitationMessage;
  final int version;
  final DateTime createdAt;
  final DateTime? viewedAt;
  final DateTime? respondedAt;

  const Invitation({
    required this.id,
    required this.partyId,
    required this.hostUserId,
    required this.invitedUserId,
    required this.status,
    required this.invitationMessage,
    required this.version,
    required this.createdAt,
    required this.viewedAt,
    required this.respondedAt,
  });

  factory Invitation.fromJson(Map<String, dynamic> json) => Invitation(
        id: json['id'] as String,
        partyId: json['party_id'] as String,
        hostUserId: json['host_user_id'] as String,
        invitedUserId: json['invited_user_id'] as String,
        status: invitationStatusFromWire(json['status'] as String),
        invitationMessage: (json['invitation_message'] as String?) ?? '',
        version: json['version'] as int,
        createdAt: DateTime.parse(json['created_at'] as String),
        viewedAt: json['viewed_at'] == null ? null : DateTime.parse(json['viewed_at'] as String),
        respondedAt: json['responded_at'] == null ? null : DateTime.parse(json['responded_at'] as String),
      );
}
