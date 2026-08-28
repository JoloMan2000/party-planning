/// Ein Sprach-Eintrag aus `GET /api/v1/translations/languages`
/// (`primary_languages`/`extra_languages`).
class LanguageOption {
  final String code;
  final String name;
  final String emoji;

  const LanguageOption({required this.code, required this.name, required this.emoji});

  factory LanguageOption.fromJson(Map<String, dynamic> json) {
    return LanguageOption(
      code: json['code'] as String,
      name: json['name'] as String,
      emoji: (json['emoji'] as String?) ?? '',
    );
  }
}

/// Vollständige Antwort von `GET /api/v1/translations/languages`.
class LanguagesResponse {
  final String defaultLanguage;
  final List<LanguageOption> primaryLanguages;
  final List<LanguageOption> extraLanguages;

  const LanguagesResponse({
    required this.defaultLanguage,
    required this.primaryLanguages,
    required this.extraLanguages,
  });

  factory LanguagesResponse.fromJson(Map<String, dynamic> json) {
    return LanguagesResponse(
      defaultLanguage: json['default_language'] as String,
      primaryLanguages: ((json['primary_languages'] as List?) ?? const [])
          .map((e) => LanguageOption.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
      extraLanguages: ((json['extra_languages'] as List?) ?? const [])
          .map((e) => LanguageOption.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
    );
  }
}
