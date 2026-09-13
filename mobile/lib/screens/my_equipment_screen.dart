import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/equipment_catalog_item.dart';
import '../models/equipment_inventory_item.dart';
import '../state/equipment_providers.dart';
import '../widgets/add_equipment_item_sheet.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Self-Service-Verwaltung des eigenen Equipment-Inventars (Equipment
/// Engine, Spec §108/§109 "My Equipment") - erreichbar über eine Kachel auf
/// `ProfileScreen`. Namen/Kategorien werden über einen Lookup in den
/// bereits geladenen Equipment-Katalog aufgelöst (`equipmentItemId` allein
/// ist nicht anzeigefreundlich).
class MyEquipmentScreen extends ConsumerWidget {
  const MyEquipmentScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final inventoryAsync = ref.watch(myEquipmentInventoryProvider);
    final catalogAsync = ref.watch(equipmentCatalogProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('My Equipment'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(showMyEquipmentProvider.notifier).state = false,
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _openAddSheet(context, ref),
        icon: const Icon(Icons.add),
        label: const Text('Add Equipment'),
      ),
      body: inventoryAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(myEquipmentInventoryProvider),
            child: const Text('Failed to load your equipment. Retry'),
          ),
        ),
        data: (inventory) {
          if (inventory.isEmpty) {
            return RefreshIndicator(
              onRefresh: () => ref.refresh(myEquipmentInventoryProvider.future),
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                children: const [
                  SizedBox(height: 200),
                  Center(child: Text("You haven't added any equipment yet.")),
                ],
              ),
            );
          }
          final catalogById = <String, EquipmentCatalogItem>{
            for (final item in catalogAsync.valueOrNull ?? const <EquipmentCatalogItem>[]) item.id: item,
          };
          return RefreshIndicator(
            onRefresh: () => ref.refresh(myEquipmentInventoryProvider.future),
            child: ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: inventory.length,
              itemBuilder: (context, i) => _InventoryTile(
                inventoryItem: inventory[i],
                catalogItem: catalogById[inventory[i].equipmentItemId],
              ),
            ),
          );
        },
      ),
    );
  }

  Future<void> _openAddSheet(BuildContext context, WidgetRef ref) async {
    final addedName = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const AddEquipmentItemSheet(),
    );
    if (addedName == null || !context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Added "$addedName" to your equipment.')));
  }
}

class _InventoryTile extends ConsumerWidget {
  final EquipmentInventoryItem inventoryItem;
  final EquipmentCatalogItem? catalogItem;

  const _InventoryTile({required this.inventoryItem, required this.catalogItem});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final name = catalogItem?.name ?? inventoryItem.equipmentItemId;
    final category = catalogItem?.categoryName;
    final quantityLabel = inventoryItem.quantity == inventoryItem.quantity.roundToDouble()
        ? inventoryItem.quantity.toInt().toString()
        : inventoryItem.quantity.toStringAsFixed(1);
    final subtitleParts = [
      'Qty: $quantityLabel',
      ?category,
      if (!inventoryItem.available) 'Unavailable',
    ];

    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.inventory_2_outlined)),
        title: Text(name),
        subtitle: Text(subtitleParts.join(' · ')),
        trailing: PopupMenuButton<String>(
          onSelected: (value) {
            if (value == 'edit') {
              _showEditDialog(context, ref);
            } else if (value == 'remove') {
              _confirmAndRemove(context, ref);
            }
          },
          itemBuilder: (context) => const [
            PopupMenuItem(value: 'edit', child: Text('Edit')),
            PopupMenuItem(value: 'remove', child: Text('Remove')),
          ],
        ),
      ),
    );
  }

  Future<void> _showEditDialog(BuildContext context, WidgetRef ref) async {
    final quantityController = TextEditingController(text: inventoryItem.quantity.toString());
    final conditionController = TextEditingController(text: inventoryItem.condition);
    final notesController = TextEditingController(text: inventoryItem.notes);
    var available = inventoryItem.available;

    final saved = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => AlertDialog(
          title: Text(catalogItem?.name ?? inventoryItem.equipmentItemId),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: quantityController,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Quantity'),
              ),
              TextField(
                controller: conditionController,
                decoration: const InputDecoration(labelText: 'Condition (optional)'),
              ),
              TextField(
                controller: notesController,
                decoration: const InputDecoration(labelText: 'Notes (optional)'),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Available for parties'),
                value: available,
                onChanged: (value) => setDialogState(() => available = value),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
            TextButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Save')),
          ],
        ),
      ),
    );
    if (saved != true || !context.mounted) return;

    final quantity = double.tryParse(quantityController.text.trim()) ?? inventoryItem.quantity;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(equipmentInventoryProvider.notifier).updateItem(
            inventoryItem.id,
            quantity: quantity,
            condition: conditionController.text.trim(),
            available: available,
            notes: notesController.text.trim(),
          );
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to save. Please try again.')));
    }
  }

  Future<void> _confirmAndRemove(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Remove this item?'),
        content: Text('Remove "${catalogItem?.name ?? inventoryItem.equipmentItemId}" from your equipment?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Remove')),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(equipmentInventoryProvider.notifier).remove(inventoryItem.id);
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to remove. Please try again.')));
    }
  }
}
