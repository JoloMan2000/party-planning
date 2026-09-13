import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/equipment_demand_result.dart';
import '../../state/equipment_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase). Deliberately NOT using
// the older `translations`/`t('...')` catalog wiring (`shopping_list_section.dart`'s
// pattern) - that system is Food/Beverage-specific; every other screen built
// since Social Graph Phase 1 hardcodes English strings instead.

/// Admin-Sektion für den Equipment-Bedarf (Equipment Engine Phase 1) -
/// strukturell verbatim mirrort `ShoppingListSection`: Button triggert
/// `POST /admin/equipment-demand` (mirrort `compute_shopping_list`), Ergebnis
/// startet `null` (noch nicht berechnet) bis zum ersten Klick. Rechnet mit
/// den Phase-1-Default-Overrides (leer) - zeigt echten, gästezahl-skalierten,
/// gegen das Host-Inventar genetteten Bedarf für die Always-On-Baseline-
/// Items (Geschirr/Bar/Reinigung). Manuelle Steuerung der Phase-1-
/// Platzhalter-Parameter (`selected_item_ids`/`station_activity_interest`/
/// `capacity_need_overrides`) ist bewusst kein Teil dieser Phase (siehe
/// Plan) - die werden erst mit der echten Activities-/Beverage-Integration
/// sinnvoll UI-fähig.
class EquipmentSection extends ConsumerStatefulWidget {
  final String partyId;

  const EquipmentSection({super.key, required this.partyId});

  @override
  ConsumerState<EquipmentSection> createState() => _EquipmentSectionState();
}

class _EquipmentSectionState extends ConsumerState<EquipmentSection> {
  bool _computing = false;

  @override
  Widget build(BuildContext context) {
    final resultAsync = ref.watch(equipmentDemandProvider(widget.partyId));

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Equipment & Supplies', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerLeft,
              child: ElevatedButton(
                onPressed: _computing ? null : () => _compute(),
                child: _computing
                    ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Calculate Equipment Plan'),
              ),
            ),
            const SizedBox(height: 16),
            resultAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (err, stack) => Text('Failed to calculate equipment plan.\n$err'),
              data: (result) {
                if (result == null) return const SizedBox.shrink();
                return _EquipmentResultView(result: result);
              },
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _compute() async {
    setState(() => _computing = true);
    try {
      await ref.read(equipmentDemandProvider(widget.partyId).notifier).compute();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Calculation failed: $e')));
    } finally {
      if (mounted) setState(() => _computing = false);
    }
  }
}

/// Formatiert eine Zahl ohne unnötige Nachkommastellen (mirrort
/// `shopping_list_section.dart`'s `_formatG`).
String _formatQty(double value) {
  if (value == value.roundToDouble()) return value.toInt().toString();
  return value.toStringAsFixed(1);
}

class _EquipmentResultView extends StatelessWidget {
  final EquipmentDemandResult result;

  const _EquipmentResultView({required this.result});

  @override
  Widget build(BuildContext context) {
    final sortedDemand = result.demand.values.toList()..sort((a, b) => a.name.compareTo(b.name));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Required Equipment', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        if (sortedDemand.isEmpty)
          const Text('No equipment needed yet.')
        else
          for (final demand in sortedDemand) _DemandRow(demand: demand),
        if (result.purchasePlan.isNotEmpty) ...[
          const Divider(height: 32),
          Text('To Buy', style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 8),
          for (final planItem in result.purchasePlan)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Text(
                '- ${planItem.name}: '
                '${planItem.skuBreakdown.isEmpty ? '${_formatQty(planItem.totalPurchasedQuantity)} ${planItem.unit}' : planItem.skuBreakdown.map((b) => '${b.count} × ${b.packLabel.isNotEmpty ? b.packLabel : '${_formatQty(b.size)} ${b.unit}'}').join(', ')}',
              ),
            ),
        ],
        if (result.reviewIssues.isNotEmpty) ...[
          const SizedBox(height: 16),
          Card(
            color: Theme.of(context).colorScheme.errorContainer,
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Needs review', style: Theme.of(context).textTheme.titleSmall),
                  const SizedBox(height: 4),
                  for (final issue in result.reviewIssues) Text('- ${issue.message}'),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _DemandRow extends StatelessWidget {
  final EquipmentDemand demand;

  const _DemandRow({required this.demand});

  @override
  Widget build(BuildContext context) {
    final required = _formatQty(math.max(demand.quantityAfterReserve, 0));
    final available = _formatQty(demand.existingQuantity);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Text('${demand.name} — Required: $required · Available: $available'),
          ),
          if (demand.isCovered)
            const Chip(
              label: Text('✓ Covered'),
              visualDensity: VisualDensity.compact,
              backgroundColor: Colors.green,
              labelStyle: TextStyle(color: Colors.white),
            )
          else
            Chip(
              label: Text('Missing: ${_formatQty(demand.missingQuantity)}'),
              visualDensity: VisualDensity.compact,
              backgroundColor: Colors.orange,
              labelStyle: const TextStyle(color: Colors.white),
            ),
        ],
      ),
    );
  }
}
