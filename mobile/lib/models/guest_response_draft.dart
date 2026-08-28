import 'song_request.dart';

/// Sammelt die Eingaben aus allen 4 Wizard-Schritten für
/// `POST /api/v1/guest/responses`, mirroring
/// `backend/app/schemas/guest.py::GuestResponseCreate`.
class GuestResponseDraft {
  final String name;
  final String startTime; // "HH:MM"
  final List<String> drinks;
  final String drinksFreetext;
  final List<String> food;
  final String foodFreetext;
  final List<SongRequest> songs;

  const GuestResponseDraft({
    required this.name,
    required this.startTime,
    required this.drinks,
    required this.drinksFreetext,
    required this.food,
    required this.foodFreetext,
    required this.songs,
  });

  Map<String, dynamic> toJson() => {
        'name': name,
        'start_time': startTime,
        'drinks': drinks,
        'drinks_freetext': drinksFreetext,
        'food': food,
        'food_freetext': foodFreetext,
        'songs': songs.map((s) => s.toJson()).toList(),
      };
}
