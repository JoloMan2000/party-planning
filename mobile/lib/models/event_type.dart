/// Ein wählbarer Event-Typ aus `GET /api/v1/admin/party-settings/event-types`
/// (mirroring `event_theme.EVENT_TYPES`).
class EventType {
  final String id;
  final String emoji;
  final String labelDe;
  final String labelEn;
  final String defaultTitle;

  const EventType({
    required this.id,
    required this.emoji,
    required this.labelDe,
    required this.labelEn,
    required this.defaultTitle,
  });

  factory EventType.fromJson(Map<String, dynamic> json) {
    return EventType(
      id: json['id'] as String,
      emoji: json['emoji'] as String,
      labelDe: json['label_de'] as String,
      labelEn: json['label_en'] as String,
      defaultTitle: json['default_title'] as String,
    );
  }

  String label(String lang) => lang == 'de' ? labelDe : labelEn;
}
