/// Antwort von `GET /api/v1/guest/party-info` - Party-Titel, Theme-Farben
/// und Kalender-Metadaten für den Wizard-Header und die Bestätigungsseite.
class PartyInfo {
  final String eventType;
  final String partyName;
  final String title;
  final Map<String, dynamic> theme;
  final String heroSubtitle;
  final String? metaDatetime;
  final bool hasScheduledDate;
  final String? googleCalendarUrl;

  const PartyInfo({
    required this.eventType,
    required this.partyName,
    required this.title,
    required this.theme,
    required this.heroSubtitle,
    required this.metaDatetime,
    required this.hasScheduledDate,
    required this.googleCalendarUrl,
  });

  factory PartyInfo.fromJson(Map<String, dynamic> json) {
    return PartyInfo(
      eventType: json['event_type'] as String,
      partyName: json['party_name'] as String,
      title: json['title'] as String,
      theme: (json['theme'] as Map?)?.cast<String, dynamic>() ?? const {},
      heroSubtitle: (json['hero_subtitle'] as String?) ?? '',
      metaDatetime: json['meta_datetime'] as String?,
      hasScheduledDate: (json['has_scheduled_date'] as bool?) ?? false,
      googleCalendarUrl: json['google_calendar_url'] as String?,
    );
  }
}
