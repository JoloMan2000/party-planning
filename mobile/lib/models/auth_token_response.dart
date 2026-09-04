import 'user_account.dart';

/// Antwort von `POST /api/v1/auth/{signup,login,refresh}`
/// (`backend/app/schemas/auth.py::AuthTokenResponse`).
class AuthTokenResponse {
  final String accessToken;
  final String refreshToken;
  final String tokenType;
  final UserAccount user;

  const AuthTokenResponse({
    required this.accessToken,
    required this.refreshToken,
    required this.tokenType,
    required this.user,
  });

  factory AuthTokenResponse.fromJson(Map<String, dynamic> json) => AuthTokenResponse(
        accessToken: json['access_token'] as String,
        refreshToken: json['refresh_token'] as String,
        tokenType: (json['token_type'] as String?) ?? 'bearer',
        user: UserAccount.fromJson((json['user'] as Map).cast<String, dynamic>()),
      );
}
