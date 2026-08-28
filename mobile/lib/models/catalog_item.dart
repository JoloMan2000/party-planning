/// Ein Katalog-Eintrag (Getränk oder Essen), wie er von
/// `GET /api/v1/catalog/drinks|food` geliefert wird.
///
/// Backend liefert je nach zugrundeliegendem Typ (`DirectConsumable` vs.
/// `Recipe`, siehe `party_engine/domain.py`) unterschiedliche Zusatzfelder
/// (z.B. `abv`/`contains_caffeine` bei Getränken, `is_vegetarian`/
/// `is_vegan`/`contains_alcohol` bei Rezepten). Statt für jeden Untertyp ein
/// eigenes Modell zu pflegen, werden hier nur die für die UI relevanten,
/// gemeinsamen Felder typisiert und der Rest lose aus dem JSON gelesen -
/// mirroring, wie der Streamlit-Katalog-Picker (`render_catalog_picker()`)
/// nur `id`/`name`/`category`/`popular`/`tags` wirklich benötigt.
class CatalogItem {
  final String id;
  final String name;
  final String displayName;
  final String category;
  final String demandGroup;
  final List<String> tags;
  final bool popular;
  final bool isVegetarian;
  final bool isVegan;
  final bool containsAlcohol;
  final bool containsCaffeine;
  final double abv;

  const CatalogItem({
    required this.id,
    required this.name,
    required this.displayName,
    required this.category,
    required this.demandGroup,
    required this.tags,
    required this.popular,
    required this.isVegetarian,
    required this.isVegan,
    required this.containsAlcohol,
    required this.containsCaffeine,
    required this.abv,
  });

  factory CatalogItem.fromJson(Map<String, dynamic> json) {
    return CatalogItem(
      id: json['id'] as String,
      name: json['name'] as String,
      displayName: (json['display_name'] as String?) ?? json['name'] as String,
      category: (json['category'] as String?) ?? '',
      demandGroup: (json['demand_group'] as String?) ?? '',
      tags: ((json['tags'] as List?) ?? const []).map((e) => e.toString()).toList(),
      popular: (json['popular'] as bool?) ?? false,
      isVegetarian: (json['is_vegetarian'] as bool?) ?? true,
      isVegan: (json['is_vegan'] as bool?) ?? false,
      containsAlcohol: (json['contains_alcohol'] as bool?) ?? ((json['abv'] as num?) ?? 0) > 0,
      containsCaffeine: (json['contains_caffeine'] as bool?) ?? false,
      abv: ((json['abv'] as num?) ?? 0).toDouble(),
    );
  }
}
