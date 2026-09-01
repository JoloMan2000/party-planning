/// Admin-Steuerparameter für die Playlist-Generierung (mirroring nur die im
/// Admin-UI editierbare Teilmenge von `music_engine.domain.AdminMusicSettings`,
/// siehe `backend/app/schemas/admin.py::MusicSettingsUpdate`).
class MusicAdminSettings {
  final double partyIntensity;
  final double mainstreamDiscovery;
  final double guestRequestPriority;
  final bool explicitAllowed;
  final int maxTracksPerArtist;

  const MusicAdminSettings({
    required this.partyIntensity,
    required this.mainstreamDiscovery,
    required this.guestRequestPriority,
    required this.explicitAllowed,
    required this.maxTracksPerArtist,
  });

  factory MusicAdminSettings.fromJson(Map<String, dynamic> json) {
    return MusicAdminSettings(
      partyIntensity: (json['party_intensity'] as num?)?.toDouble() ?? 0.5,
      mainstreamDiscovery: (json['mainstream_discovery'] as num?)?.toDouble() ?? 0.7,
      guestRequestPriority: (json['guest_request_priority'] as num?)?.toDouble() ?? 0.7,
      explicitAllowed: (json['explicit_allowed'] as bool?) ?? true,
      maxTracksPerArtist: (json['max_tracks_per_artist'] as num?)?.toInt() ?? 3,
    );
  }

  Map<String, dynamic> toJson() => {
        'party_intensity': partyIntensity,
        'mainstream_discovery': mainstreamDiscovery,
        'guest_request_priority': guestRequestPriority,
        'explicit_allowed': explicitAllowed,
        'max_tracks_per_artist': maxTracksPerArtist,
      };
}
