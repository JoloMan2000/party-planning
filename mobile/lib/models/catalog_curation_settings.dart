import 'catalog_item.dart';

/// Admin-Einstellungen zur Einschränkung der Gäste-Auswahl (mirroring
/// `party_engine.domain.CatalogCurationSettings`, geliefert von
/// `GET /api/v1/admin/catalog-curation`).
class CatalogCurationSettings {
  final bool enabled;
  final List<String> curatedItemIds;

  const CatalogCurationSettings({required this.enabled, required this.curatedItemIds});

  factory CatalogCurationSettings.fromJson(Map<String, dynamic> json) {
    return CatalogCurationSettings(
      enabled: json['enabled'] as bool? ?? false,
      curatedItemIds: ((json['curated_item_ids'] as List?) ?? const []).map((e) => e.toString()).toList(),
    );
  }
}

/// Der vollständige, ungefilterte Getränke-/Speisenkatalog fürs Kurations-
/// Formular (mirroring `_drink_items(catalog, apply_curation=False)`/
/// `_food_items(..., apply_curation=False)`, geliefert von
/// `GET /api/v1/admin/catalog-curation/items`).
class CuratableCatalog {
  final List<CatalogItem> drinks;
  final List<CatalogItem> food;

  const CuratableCatalog({required this.drinks, required this.food});

  factory CuratableCatalog.fromJson(Map<String, dynamic> json) {
    return CuratableCatalog(
      drinks: ((json['drinks'] as List?) ?? const [])
          .map((e) => CatalogItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      food: ((json['food'] as List?) ?? const [])
          .map((e) => CatalogItem.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}
