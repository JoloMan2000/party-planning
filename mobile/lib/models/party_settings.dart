/// Antwort/Payload für `GET`/`POST /api/v1/admin/party-settings`
/// (mirroring `backend/app/schemas/admin.py::PartySettingsUpdate`).
class PartySettings {
  final String eventType;
  final String partyName;
  final String partyDate; // ISO "YYYY-MM-DD", darf leer sein
  final String partyStartTime; // "HH:MM", darf leer sein
  final double partyDurationHours;
  final String partyLocation;

  const PartySettings({
    required this.eventType,
    required this.partyName,
    required this.partyDate,
    required this.partyStartTime,
    required this.partyDurationHours,
    required this.partyLocation,
  });

  factory PartySettings.fromJson(Map<String, dynamic> json) {
    return PartySettings(
      eventType: json['event_type'] as String,
      partyName: (json['party_name'] as String?) ?? '',
      partyDate: (json['party_date'] as String?) ?? '',
      partyStartTime: (json['party_start_time'] as String?) ?? '',
      partyDurationHours: (json['party_duration_hours'] as num?)?.toDouble() ?? 7.0,
      partyLocation: (json['party_location'] as String?) ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'event_type': eventType,
        'party_name': partyName,
        'party_date': partyDate,
        'party_start_time': partyStartTime,
        'party_duration_hours': partyDurationHours,
        'party_location': partyLocation,
      };

  PartySettings copyWith({
    String? eventType,
    String? partyName,
    String? partyDate,
    String? partyStartTime,
    double? partyDurationHours,
    String? partyLocation,
  }) {
    return PartySettings(
      eventType: eventType ?? this.eventType,
      partyName: partyName ?? this.partyName,
      partyDate: partyDate ?? this.partyDate,
      partyStartTime: partyStartTime ?? this.partyStartTime,
      partyDurationHours: partyDurationHours ?? this.partyDurationHours,
      partyLocation: partyLocation ?? this.partyLocation,
    );
  }
}
