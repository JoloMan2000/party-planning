/// Nur die für die Admin-Playlist-Anzeige relevante Teilmenge von
/// `music_engine.domain.MusicPlanningResult` (mirroring
/// `render_music_playlist_section`'s angezeigte Felder).
class MusicPlanningResult {
  final int totalTracks;
  final int actualDurationMs;
  final double guestCoverage;
  final int requestedTracksSelected;
  final int requestedTracksTotal;
  final List<String> reviewIssues;
  final List<String> explanations;
  final List<MusicPhase> phases;
  final List<PlaylistSlot> playlist;

  const MusicPlanningResult({
    required this.totalTracks,
    required this.actualDurationMs,
    required this.guestCoverage,
    required this.requestedTracksSelected,
    required this.requestedTracksTotal,
    required this.reviewIssues,
    required this.explanations,
    required this.phases,
    required this.playlist,
  });

  factory MusicPlanningResult.fromJson(Map<String, dynamic> json) {
    return MusicPlanningResult(
      totalTracks: (json['total_tracks'] as num?)?.toInt() ?? 0,
      actualDurationMs: (json['actual_duration_ms'] as num?)?.toInt() ?? 0,
      guestCoverage: (json['guest_coverage'] as num?)?.toDouble() ?? 0.0,
      requestedTracksSelected: (json['requested_tracks_selected'] as num?)?.toInt() ?? 0,
      requestedTracksTotal: (json['requested_tracks_total'] as num?)?.toInt() ?? 0,
      reviewIssues: (json['review_issues'] as List? ?? []).map((e) => e as String).toList(),
      explanations: (json['explanations'] as List? ?? []).map((e) => e as String).toList(),
      phases: (json['phases'] as List? ?? [])
          .map((e) => MusicPhase.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
      playlist: (json['playlist'] as List? ?? [])
          .map((e) => PlaylistSlot.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
    );
  }
}

class MusicPhase {
  final String id;
  final String labelDe;
  final String labelEn;

  const MusicPhase({required this.id, required this.labelDe, required this.labelEn});

  factory MusicPhase.fromJson(Map<String, dynamic> json) {
    return MusicPhase(
      id: json['id'] as String,
      labelDe: (json['label_de'] as String?) ?? '',
      labelEn: (json['label_en'] as String?) ?? '',
    );
  }

  String label(String lang) {
    final value = lang == 'de' ? labelDe : labelEn;
    return value.isEmpty ? id : value;
  }
}

class PlaylistSlot {
  final int position;
  final String phaseId;
  final String trackId;
  final String trackTitle;
  final String trackArtist;
  final List<String> supportingGuests;
  final List<String> reasons;

  const PlaylistSlot({
    required this.position,
    required this.phaseId,
    required this.trackId,
    required this.trackTitle,
    required this.trackArtist,
    required this.supportingGuests,
    required this.reasons,
  });

  factory PlaylistSlot.fromJson(Map<String, dynamic> json) {
    return PlaylistSlot(
      position: (json['position'] as num?)?.toInt() ?? 0,
      phaseId: json['phase_id'] as String,
      trackId: json['track_id'] as String,
      trackTitle: (json['track_title'] as String?) ?? (json['track_id'] as String),
      trackArtist: (json['track_artist'] as String?) ?? '',
      supportingGuests: (json['supporting_guests'] as List? ?? []).map((e) => e as String).toList(),
      reasons: (json['reasons'] as List? ?? []).map((e) => e as String).toList(),
    );
  }

  String get displayTitle => trackArtist.isEmpty ? trackTitle : '$trackArtist – $trackTitle';
}
