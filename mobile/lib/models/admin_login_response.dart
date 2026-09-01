/// Antwort von `POST /api/v1/auth/admin/login`
/// (`backend/app/schemas/auth.py::AdminLoginResponse`).
class AdminLoginResponse {
  final String accessToken;
  final String tokenType;

  const AdminLoginResponse({required this.accessToken, required this.tokenType});

  factory AdminLoginResponse.fromJson(Map<String, dynamic> json) {
    return AdminLoginResponse(
      accessToken: json['access_token'] as String,
      tokenType: (json['token_type'] as String?) ?? 'bearer',
    );
  }
}
