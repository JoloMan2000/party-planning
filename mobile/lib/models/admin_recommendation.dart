/// Ein empfohlenes Katalog-Item mit Score + Erklärung (mirroring
/// `admin_recommendations.py::get_admin_recommendations`'s
/// `{"item": ..., "score": ..., "explanation": ...}`-Einträge).
class AdminRecommendation {
  final String itemId;
  final String itemName;
  final double totalScore;
  final String explanation;

  const AdminRecommendation({
    required this.itemId,
    required this.itemName,
    required this.totalScore,
    required this.explanation,
  });

  factory AdminRecommendation.fromJson(Map<String, dynamic> json) {
    final item = (json['item'] as Map).cast<String, dynamic>();
    final score = (json['score'] as Map).cast<String, dynamic>();
    return AdminRecommendation(
      itemId: item['id'] as String,
      itemName: item['name'] as String,
      totalScore: (score['total_score'] as num).toDouble(),
      explanation: json['explanation'] as String,
    );
  }
}

/// Antwort von `GET /api/v1/admin/recommendations`.
class AdminRecommendationsResponse {
  final String occasionLabel;
  final List<AdminRecommendation> items;

  const AdminRecommendationsResponse({required this.occasionLabel, required this.items});

  factory AdminRecommendationsResponse.fromJson(Map<String, dynamic> json) {
    return AdminRecommendationsResponse(
      occasionLabel: json['occasion_label'] as String,
      items: (json['items'] as List)
          .map((e) => AdminRecommendation.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
    );
  }
}
