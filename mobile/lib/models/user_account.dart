/// Öffentliches User-Profil (`backend/app/schemas/auth.py::UserPublic`).
/// Enthält bewusst kein Passwort-Hash-Feld - das Backend liefert es nie mit.
class UserAccount {
  final String id;
  final String email;
  final String displayName;
  final String profileImage;
  final DateTime createdAt;

  const UserAccount({
    required this.id,
    required this.email,
    required this.displayName,
    required this.profileImage,
    required this.createdAt,
  });

  factory UserAccount.fromJson(Map<String, dynamic> json) => UserAccount(
        id: json['id'] as String,
        email: json['email'] as String,
        displayName: json['display_name'] as String,
        profileImage: (json['profile_image'] as String?) ?? '',
        createdAt: DateTime.parse(json['created_at'] as String),
      );
}
