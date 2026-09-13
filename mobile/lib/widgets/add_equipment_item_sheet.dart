import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../models/equipment_catalog_item.dart';
import '../state/equipment_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Equipment-Katalog durchsuchen und EIN Item zum eigenen Inventar
/// hinzufügen - als `showModalBottomSheet` geöffnet (mirrort
/// `FriendPickerSheet`). Suche ist rein client-seitiges Substring-Matching
/// über den bereits geladenen Katalog (mirrort `CatalogPicker`'s Muster -
/// kein API-Call pro Tastenanschlag). Tippen auf ein Item fügt es SOFORT
/// mit `quantity=1` hinzu (kein zweistufiger Mengen-Dialog) - die Menge
/// lässt sich danach über `MyEquipmentScreen`'s Edit-Dialog anpassen.
/// Bei Erfolg schließt sich das Sheet mit dem Item-Namen als Ergebnis
/// (Caller zeigt die Erfolgs-SnackBar); bei Fehlern (z.B. 409 = schon im
/// Inventar) bleibt das Sheet offen und zeigt die Fehlermeldung inline.
class AddEquipmentItemSheet extends ConsumerStatefulWidget {
  const AddEquipmentItemSheet({super.key});

  @override
  ConsumerState<AddEquipmentItemSheet> createState() => _AddEquipmentItemSheetState();
}

class _AddEquipmentItemSheetState extends ConsumerState<AddEquipmentItemSheet> {
  final _searchController = TextEditingController();
  String? _addingItemId;

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _addItem(EquipmentCatalogItem item) async {
    setState(() => _addingItemId = item.id);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(equipmentInventoryProvider.notifier).add(item.id);
      if (mounted) Navigator.pop(context, item.name);
    } catch (e) {
      final message = e is ApiException && e.statusCode == 409
          ? 'You already have "${item.name}" in your inventory.'
          : 'Failed to add. Please try again.';
      messenger.showSnackBar(SnackBar(content: Text(message)));
    } finally {
      if (mounted) setState(() => _addingItemId = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final catalogAsync = ref.watch(equipmentCatalogProvider);
    final query = _searchController.text.trim().toLowerCase();

    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 20,
          right: 20,
          top: 20,
          bottom: MediaQuery.of(context).viewInsets.bottom + 20,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Add Equipment', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            TextField(
              controller: _searchController,
              autofocus: true,
              onChanged: (_) => setState(() {}),
              decoration: InputDecoration(
                hintText: 'Search equipment',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _searchController.text.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () => setState(() => _searchController.clear()),
                      ),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
            const SizedBox(height: 12),
            Flexible(
              child: catalogAsync.when(
                loading: () => const Center(child: Padding(padding: EdgeInsets.all(20), child: CircularProgressIndicator())),
                error: (err, st) => const Padding(
                  padding: EdgeInsets.all(20),
                  child: Text('Failed to load the equipment catalog.'),
                ),
                data: (items) {
                  if (query.isNotEmpty) {
                    final results = items.where((i) => i.name.toLowerCase().contains(query)).toList()
                      ..sort((a, b) => a.name.compareTo(b.name));
                    if (results.isEmpty) {
                      return const Padding(
                        padding: EdgeInsets.symmetric(vertical: 20),
                        child: Text('No matching equipment.'),
                      );
                    }
                    return ListView(
                      shrinkWrap: true,
                      children: results.map((item) => _EquipmentPickTile(
                            item: item,
                            busy: _addingItemId == item.id,
                            onTap: () => _addItem(item),
                          )).toList(),
                    );
                  }

                  final grouped = <String, List<EquipmentCatalogItem>>{};
                  for (final item in items) {
                    grouped.putIfAbsent(item.categoryName, () => []).add(item);
                  }
                  final groupKeys = grouped.keys.toList()..sort();
                  for (final key in groupKeys) {
                    grouped[key]!.sort((a, b) => a.name.compareTo(b.name));
                  }

                  return ListView(
                    shrinkWrap: true,
                    children: [
                      for (final key in groupKeys)
                        ExpansionTile(
                          title: Text(key),
                          tilePadding: EdgeInsets.zero,
                          children: [
                            for (final item in grouped[key]!)
                              _EquipmentPickTile(
                                item: item,
                                busy: _addingItemId == item.id,
                                onTap: () => _addItem(item),
                              ),
                          ],
                        ),
                    ],
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _EquipmentPickTile extends StatelessWidget {
  final EquipmentCatalogItem item;
  final bool busy;
  final VoidCallback onTap;

  const _EquipmentPickTile({required this.item, required this.busy, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return ListTile(
      dense: true,
      contentPadding: EdgeInsets.zero,
      title: Text(item.name),
      subtitle: Text(item.equipmentType),
      trailing: busy
          ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
          : const Icon(Icons.add_circle_outline),
      onTap: busy ? null : onTap,
    );
  }
}
