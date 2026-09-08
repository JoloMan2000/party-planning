/// Mirrort `backend/app/schemas/spotify.py::SpotifyStatusResponse`
/// (`GET /api/v1/me/music-provider/spotify/status`).
class SpotifyStatus {
  final bool connected;
  final String? spotifyUserId;
  final DateTime? connectedAt;

  const SpotifyStatus({
    required this.connected,
    this.spotifyUserId,
    this.connectedAt,
  });

  factory SpotifyStatus.fromJson(Map<String, dynamic> json) => SpotifyStatus(
        connected: json['connected'] as bool,
        spotifyUserId: json['spotify_user_id'] as String?,
        connectedAt: json['connected_at'] == null ? null : DateTime.parse(json['connected_at'] as String),
      );
}
