/// Mirrort `backend/app/schemas/profile.py::ProfilePublic`
/// (`GET/PATCH /api/v1/me/profile`, `POST .../birth-date-correction`).
///
/// Bewusst OHNE `toJson()` - die beiden Schreibpfade (`PATCH` für
/// Gender/Bio, `POST birth-date-correction` für das Geburtsdatum) senden
/// je einen eigenen, kleinen Request-Body, den `ApiClient` inline baut
/// (siehe `updateProfile`/`correctBirthDate`). Ein generisches `toJson()`
/// würde dazu verleiten, versehentlich `birth_date` in ein `PATCH`
/// mitzuschicken - das Backend ignoriert das zwar (Pydantic verwirft
/// unbekannte Felder), aber es sollte hier gar nicht erst möglich sein.
class Profile {
  final String userId;
  final DateTime birthDate;
  final int age;
  final String gender;
  final String bio;
  final DateTime? onboardingCompletedAt;
  final int profileCompletionVersion;

  const Profile({
    required this.userId,
    required this.birthDate,
    required this.age,
    this.gender = '',
    this.bio = '',
    this.onboardingCompletedAt,
    this.profileCompletionVersion = 0,
  });

  factory Profile.fromJson(Map<String, dynamic> json) => Profile(
        userId: json['user_id'] as String,
        birthDate: DateTime.parse(json['birth_date'] as String),
        age: json['age'] as int,
        gender: (json['gender'] as String?) ?? '',
        bio: (json['bio'] as String?) ?? '',
        onboardingCompletedAt: json['onboarding_completed_at'] == null
            ? null
            : DateTime.parse(json['onboarding_completed_at'] as String),
        profileCompletionVersion: (json['profile_completion_version'] as int?) ?? 0,
      );
}
