/// Ein wählbarer Eintrag aus den öffentlichen Discovery-Katalogen
/// (`GET /api/v1/catalogs/event-interests` bzw. `.../interest-tags`,
/// `backend/app/schemas/profile.py::CatalogItemPublic`) - bewusst schlank
/// und getrennt vom unverwandten Drinks/Food-`catalog_item.dart`.
class DiscoveryCatalogItem {
  final String id;
  final String labelDe;
  final String labelEn;
  final String emoji;

  const DiscoveryCatalogItem({
    required this.id,
    required this.labelDe,
    required this.labelEn,
    required this.emoji,
  });

  factory DiscoveryCatalogItem.fromJson(Map<String, dynamic> json) => DiscoveryCatalogItem(
        id: json['id'] as String,
        labelDe: json['label_de'] as String,
        labelEn: json['label_en'] as String,
        emoji: (json['emoji'] as String?) ?? '',
      );

  String label(String lang) => lang == 'de' ? labelDe : labelEn;
}
