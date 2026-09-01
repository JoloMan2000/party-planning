import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../i18n/translate.dart';
import '../../state/admin_providers.dart';
import '../../state/providers.dart';
import '../catalog_picker.dart';

/// Admin-Sektion zur Limitierung der Gäste-Auswahl auf eine "engere Auswahl"
/// (mirroring `render_catalog_curation_section`): ist die Limitierung
/// aktiviert UND mindestens ein Getränk/Gericht ausgewählt, sehen Gäste in
/// Schritt 2/3 des Fragebogens NUR noch diese Items (Backend wendet
/// `filter_items_by_curation()` bereits serverseitig auf
/// `GET /api/v1/catalog/drinks|food` an). Wiederverwendet den bestehenden
/// `CatalogPicker` (gleiche Suche/Gruppierung wie im Gäste-Fragebogen),
/// diesmal gespeist vom ungefilterten Katalog
/// (`GET /api/v1/admin/catalog-curation/items`) mit vorbelegter Auswahl aus
/// den gespeicherten Settings.
class CatalogCurationSection extends ConsumerStatefulWidget {
  const CatalogCurationSection({super.key});

  @override
  ConsumerState<CatalogCurationSection> createState() => _CatalogCurationSectionState();
}

class _CatalogCurationSectionState extends ConsumerState<CatalogCurationSection> {
  bool _seeded = false;
  bool _enabled = false;
  List<String> _selectedDrinks = [];
  List<String> _selectedFood = [];
  bool _saving = false;

  @override
  Widget build(BuildContext context) {
    final translationsAsync = ref.watch(translationsProvider('de'));
    final settingsAsync = ref.watch(catalogCurationProvider);
    final catalogAsync = ref.watch(curatableCatalogProvider);

    return translationsAsync.when(
      loading: () => const Padding(
        padding: EdgeInsets.all(20),
        child: Center(child: CircularProgressIndicator()),
      ),
      error: (err, stack) => Padding(
        padding: const EdgeInsets.all(20),
        child: Text('Übersetzungen konnten nicht geladen werden.\n$err'),
      ),
      data: (translations) {
        String t(String key, [Map<String, Object?> params = const {}]) =>
            tr(translations, key, params);

        return settingsAsync.when(
          loading: () => const Padding(
            padding: EdgeInsets.all(20),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (err, stack) => Padding(
            padding: const EdgeInsets.all(20),
            child: Text('Kurations-Einstellungen konnten nicht geladen werden.\n$err'),
          ),
          data: (settings) {
            if (!_seeded) {
              _enabled = settings.enabled;
              _selectedDrinks = List.of(settings.curatedItemIds);
              _selectedFood = List.of(settings.curatedItemIds);
              _seeded = true;
            }

            return Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: ExpansionTile(
                  tilePadding: EdgeInsets.zero,
                  title: Text(t('catalog_curation_header'), style: Theme.of(context).textTheme.titleMedium),
                  children: [
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text(t('catalog_curation_caption'), style: Theme.of(context).textTheme.bodySmall),
                    ),
                    const SizedBox(height: 8),
                    CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      controlAffinity: ListTileControlAffinity.leading,
                      title: Text(t('catalog_curation_enabled_label')),
                      value: _enabled,
                      onChanged: (value) => setState(() => _enabled = value ?? _enabled),
                    ),
                    if (_enabled && _selectedDrinks.isEmpty && _selectedFood.isEmpty)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        child: Text(
                          t('catalog_curation_empty_warning'),
                          style: TextStyle(color: Theme.of(context).colorScheme.error),
                        ),
                      ),
                    const SizedBox(height: 12),
                    catalogAsync.when(
                      loading: () => const Padding(
                        padding: EdgeInsets.symmetric(vertical: 24),
                        child: Center(child: CircularProgressIndicator()),
                      ),
                      error: (err, stack) => Text('Katalog konnte nicht geladen werden.\n$err'),
                      data: (catalog) => Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            t('catalog_curation_drinks_label'),
                            style: Theme.of(context).textTheme.titleSmall,
                          ),
                          const SizedBox(height: 8),
                          CatalogPicker(
                            items: catalog.drinks,
                            selectedIds: _selectedDrinks,
                            onChanged: (ids) => setState(() => _selectedDrinks = ids),
                            translations: translations,
                          ),
                          const SizedBox(height: 20),
                          Text(
                            t('catalog_curation_food_label'),
                            style: Theme.of(context).textTheme.titleSmall,
                          ),
                          const SizedBox(height: 8),
                          CatalogPicker(
                            items: catalog.food,
                            selectedIds: _selectedFood,
                            onChanged: (ids) => setState(() => _selectedFood = ids),
                            translations: translations,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 20),
                    Align(
                      alignment: Alignment.centerRight,
                      child: ElevatedButton(
                        onPressed: _saving ? null : () => _save(t),
                        child: _saving
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : Text(t('btn_save_catalog_curation')),
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  Future<void> _save(String Function(String, [Map<String, Object?>]) t) async {
    setState(() => _saving = true);
    try {
      final curatedItemIds = {..._selectedDrinks, ..._selectedFood}.toList();
      await ref.read(catalogCurationProvider.notifier).save(_enabled, curatedItemIds);
      if (!mounted) return;
      setState(() => _saving = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t('catalog_curation_saved'))));
    } catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Speichern fehlgeschlagen: $e')));
    }
  }
}
