/// Antwort auf `POST /api/v1/parties/{id}/co-hosts`
/// (`backend/app/schemas/accounts.py::CoHostPromoteResponse`, Social-Graph-Phase-2).
class CoHostPromoteResult {
  final String userId;
  final String partyId;
  final String role;
  final bool alreadyCoHost;

  const CoHostPromoteResult({
    required this.userId,
    required this.partyId,
    required this.role,
    required this.alreadyCoHost,
  });

  factory CoHostPromoteResult.fromJson(Map<String, dynamic> json) => CoHostPromoteResult(
        userId: json['user_id'] as String,
        partyId: json['party_id'] as String,
        role: json['role'] as String,
        alreadyCoHost: (json['already_co_host'] as bool?) ?? false,
      );
}
