/// Ein Equipment-Katalog-Item (`backend/app/schemas/equipment.py::EquipmentCatalogItemPublic`).
/// Kategorie-Namen sind server-seitig aufgelöst - kein zweiter Lookup nötig.
class EquipmentCatalogItem {
  final String id;
  final String name;
  final String equipmentType; // durable | consumable | rental
  final String unit;
  final String categoryId;
  final String categoryName;
  final String? subcategoryId;
  final String? subcategoryName;
  final List<String> tags;

  const EquipmentCatalogItem({
    required this.id,
    required this.name,
    required this.equipmentType,
    required this.unit,
    required this.categoryId,
    required this.categoryName,
    required this.subcategoryId,
    required this.subcategoryName,
    required this.tags,
  });

  factory EquipmentCatalogItem.fromJson(Map<String, dynamic> json) => EquipmentCatalogItem(
        id: json['id'] as String,
        name: json['name'] as String,
        equipmentType: (json['equipment_type'] as String?) ?? 'consumable',
        unit: (json['unit'] as String?) ?? 'pcs',
        categoryId: json['category_id'] as String,
        categoryName: (json['category_name'] as String?) ?? '',
        subcategoryId: json['subcategory_id'] as String?,
        subcategoryName: json['subcategory_name'] as String?,
        tags: (json['tags'] as List?)?.cast<String>() ?? const [],
      );
}
