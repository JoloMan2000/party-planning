import 'package:flutter/material.dart';

import '../i18n/translate.dart';
import '../models/catalog_item.dart';

/// Kompakte, katalog-getriebene Mehrfachauswahl (mirroring
/// `render_catalog_picker()`): optionale "Empfohlen"-Sektion + "Beliebt"-
/// Sektion + Suche + nach Kategorie gruppierte Abschnitte - bewusst KEINE
/// hunderte Checkboxen untereinander.
///
/// Grouping-Entscheidung (siehe Phase-1-Plan-Docstring in
/// `backend/app/routers/catalog.py`: "die Mobile-App gruppiert client-seitig
/// selbst anhand von `category`"): die feingranulare Tab-Gruppierung aus dem
/// Streamlit-Original (`_DRINK_GROUP_ORDER` etc.) hat keine API-Entsprechung,
/// daher wird hier direkt nach dem rohen `category`-Feld gruppiert, mit
/// einem simplen "snake_case -> Title Case"-Label statt übersetzter
/// Gruppen-Header.
class CatalogPicker extends StatefulWidget {
  final List<CatalogItem> items;
  final List<String> recommendedIds;
  final String recommendedLabel;
  final List<String> selectedIds;
  final ValueChanged<List<String>> onChanged;
  final Map<String, String> translations;

  const CatalogPicker({
    super.key,
    required this.items,
    required this.selectedIds,
    required this.onChanged,
    required this.translations,
    this.recommendedIds = const [],
    this.recommendedLabel = '',
  });

  @override
  State<CatalogPicker> createState() => _CatalogPickerState();
}

class _CatalogPickerState extends State<CatalogPicker> {
  String _query = '';

  String _t(String key, [Map<String, Object?> params = const {}]) =>
      tr(widget.translations, key, params);

  void _toggle(String id) {
    final selected = {...widget.selectedIds};
    if (selected.contains(id)) {
      selected.remove(id);
    } else {
      selected.add(id);
    }
    widget.onChanged(selected.toList());
  }

  String _label(CatalogItem item, Set<String> recommendedSet) {
    final prefix = recommendedSet.contains(item.id) ? _t('recommended_item_prefix') : '';
    return '$prefix${item.displayName}';
  }

  String _categoryLabel(String category) {
    final words = category.split('_').where((w) => w.isNotEmpty);
    return words.map((w) => w[0].toUpperCase() + w.substring(1)).join(' ');
  }

  @override
  Widget build(BuildContext context) {
    final byId = {for (final item in widget.items) item.id: item};
    final recommendedSet = widget.recommendedIds.toSet();
    final selectedSet = widget.selectedIds.toSet();

    final popularItems = widget.items.where((i) => i.popular).toList()
      ..sort((a, b) => a.displayName.compareTo(b.displayName));

    final grouped = <String, List<CatalogItem>>{};
    for (final item in widget.items) {
      grouped.putIfAbsent(item.category, () => []).add(item);
    }
    final groupKeys = grouped.keys.toList()..sort();
    for (final list in grouped.values) {
      list.sort((a, b) => a.displayName.compareTo(b.displayName));
    }

    final recommendedInItems = widget.recommendedIds.where(byId.containsKey).toList();

    final query = _query.trim().toLowerCase();
    final searchResults = query.isEmpty
        ? const <CatalogItem>[]
        : (widget.items.where((i) => i.displayName.toLowerCase().contains(query)).toList()
          ..sort((a, b) => a.displayName.compareTo(b.displayName)));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (recommendedInItems.isNotEmpty) ...[
          Text(
            _t('recommended_for_label', {'occasion': widget.recommendedLabel}),
            style: Theme.of(context).textTheme.labelLarge,
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final id in recommendedInItems)
                FilterChip(
                  label: Text(byId[id]!.displayName),
                  selected: selectedSet.contains(id),
                  onSelected: (_) => _toggle(id),
                ),
            ],
          ),
          const SizedBox(height: 16),
        ],
        if (popularItems.isNotEmpty) ...[
          Text(_t('popular_label'), style: Theme.of(context).textTheme.labelLarge),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final item in popularItems)
                FilterChip(
                  label: Text(_label(item, recommendedSet)),
                  selected: selectedSet.contains(item.id),
                  onSelected: (_) => _toggle(item.id),
                ),
            ],
          ),
          const SizedBox(height: 16),
        ],
        Text(_t('catalog_search_label'), style: Theme.of(context).textTheme.labelLarge),
        const SizedBox(height: 6),
        TextField(
          decoration: InputDecoration(
            hintText: _t('catalog_search_placeholder'),
            prefixIcon: const Icon(Icons.search),
            isDense: true,
            border: const OutlineInputBorder(),
          ),
          onChanged: (value) => setState(() => _query = value),
        ),
        if (searchResults.isNotEmpty) ...[
          const SizedBox(height: 8),
          ...searchResults.map(
            (item) => CheckboxListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: Text(_label(item, recommendedSet)),
              value: selectedSet.contains(item.id),
              onChanged: (_) => _toggle(item.id),
            ),
          ),
        ],
        const SizedBox(height: 16),
        for (final groupKey in groupKeys)
          ExpansionTile(
            title: Text(_categoryLabel(groupKey)),
            tilePadding: EdgeInsets.zero,
            children: [
              for (final item in grouped[groupKey]!)
                CheckboxListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: Text(_label(item, recommendedSet)),
                  value: selectedSet.contains(item.id),
                  onChanged: (_) => _toggle(item.id),
                ),
            ],
          ),
      ],
    );
  }
}
