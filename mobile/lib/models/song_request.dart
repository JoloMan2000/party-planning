/// Ein Songwunsch (Schritt 4 des Wizards), mirroring
/// `backend/app/schemas/guest.py::SongRequest`.
class SongRequest {
  final String artist;
  final String title;

  const SongRequest({required this.artist, required this.title});

  Map<String, dynamic> toJson() => {'artist': artist, 'title': title};
}
