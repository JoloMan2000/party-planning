/// Eine gespeicherte Gäste-Antwort für die Admin-Ansicht (mirroring
/// `raw_responses_expander` in `render_admin_view`). Die `_display`-Felder
/// werden bereits server-seitig formatiert (siehe
/// `backend/app/routers/admin_responses.py::list_responses`), damit hier kein
/// eigener Katalog-Lookup nötig ist.
class GuestResponse {
  final String name;
  final String startTime;
  final List<String> drinksDisplay;
  final String drinksFreetext;
  final List<String> foodDisplay;
  final String foodFreetext;
  final String songsDisplay;
  final String submittedAt;

  const GuestResponse({
    required this.name,
    required this.startTime,
    required this.drinksDisplay,
    required this.drinksFreetext,
    required this.foodDisplay,
    required this.foodFreetext,
    required this.songsDisplay,
    required this.submittedAt,
  });

  factory GuestResponse.fromJson(Map<String, dynamic> json) {
    return GuestResponse(
      name: json['name'] as String,
      startTime: json['start_time'] as String,
      drinksDisplay: (json['drinks_display'] as List? ?? []).map((e) => e as String).toList(),
      drinksFreetext: (json['drinks_freetext'] as String?) ?? '',
      foodDisplay: (json['food_display'] as List? ?? []).map((e) => e as String).toList(),
      foodFreetext: (json['food_freetext'] as String?) ?? '',
      songsDisplay: (json['songs_display'] as String?) ?? '',
      submittedAt: (json['submitted_at'] as String?) ?? '',
    );
  }
}
