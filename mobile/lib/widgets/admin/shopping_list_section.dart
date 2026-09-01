import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../i18n/translate.dart';
import '../../models/party_demand_result.dart';
import '../../state/admin_providers.dart';
import '../../state/providers.dart';

/// Admin-Sektion für die Einkaufsliste (mirroring `render_shopping_list`,
/// getriggert durch `btn_create_shopping_list` - Unified Demand Pipeline
/// (`compute_party_demand`), ersetzt die früheren getrennten
/// Getränke-/Essen-Sektionen).
class ShoppingListSection extends ConsumerStatefulWidget {
  const ShoppingListSection({super.key});

  @override
  ConsumerState<ShoppingListSection> createState() => _ShoppingListSectionState();
}

class _ShoppingListSectionState extends ConsumerState<ShoppingListSection> {
  bool _computing = false;

  @override
  Widget build(BuildContext context) {
    final translationsAsync = ref.watch(translationsProvider('de'));
    final resultAsync = ref.watch(shoppingListProvider);
    final responsesAsync = ref.watch(adminResponsesProvider);

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

        return Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: ElevatedButton(
                    onPressed: _computing ? null : () => _compute(),
                    child: _computing
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Text(t('btn_create_shopping_list')),
                  ),
                ),
                const SizedBox(height: 16),
                resultAsync.when(
                  loading: () => const Center(child: CircularProgressIndicator()),
                  error: (err, stack) => Text('Einkaufsliste konnte nicht berechnet werden.\n$err'),
                  data: (result) {
                    if (result == null) return const SizedBox.shrink();
                    final startTimes = responsesAsync.maybeWhen(
                      data: (responses) => responses.map((r) => r.startTime).toList()..sort(),
                      orElse: () => <String>[],
                    );
                    return _ShoppingListResultView(
                      result: result,
                      startTimes: startTimes,
                      t: t,
                    );
                  },
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _compute() async {
    setState(() => _computing = true);
    try {
      await ref.read(shoppingListProvider.notifier).compute();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Berechnung fehlgeschlagen: $e')));
    } finally {
      if (mounted) setState(() => _computing = false);
    }
  }
}

/// Formatiert eine Zahl wie Pythons `:g`-Format (ganzzahlige Werte ohne
/// Nachkommastellen, sonst kompakt).
String _formatG(double value) {
  if (value == value.roundToDouble()) return value.toInt().toString();
  return value.toString();
}

class _ShoppingListResultView extends StatelessWidget {
  final PartyDemandResult result;
  final List<String> startTimes;
  final String Function(String, [Map<String, Object?>]) t;

  const _ShoppingListResultView({required this.result, required this.startTimes, required this.t});

  @override
  Widget build(BuildContext context) {
    final sortedIngredients = result.ingredientDemand.values.toList()
      ..sort((a, b) => a.name.compareTo(b.name));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // --- Gewünschte Startzeiten ---
        Text(
          t('times_header', {'n': startTimes.length}),
          style: Theme.of(context).textTheme.titleMedium,
        ),
        Text(startTimes.join(', ')),
        const SizedBox(height: 16),

        // --- Präferenzübersicht ---
        Text(t('item_overview_header'), style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (result.itemDemand.isEmpty)
          Text(t('no_item_demand'), style: Theme.of(context).textTheme.bodySmall)
        else
          for (final summary in result.itemDemand)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Text(
                '- ${summary.itemName} — ${summary.supporters} ${t('supporting_guests_label')}, '
                '${summary.expectedServings.toStringAsFixed(1)} ${t('expected_servings_label')}',
              ),
            ),

        const Divider(height: 32),

        // --- Ingredient Demand ---
        Text(t('ingredient_demand_header'), style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (sortedIngredients.isEmpty)
          Text(t('no_ingredient_demand'), style: Theme.of(context).textTheme.bodySmall)
        else
          for (final demand in sortedIngredients)
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: Text(
                '${demand.name} — ${demand.quantityAfterReserve.toStringAsFixed(2)} ${demand.unit}',
              ),
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (demand.family.isNotEmpty)
                        Text('${t('family_label')}: ${demand.family}'),
                      Text('${t('contributions_label')}:'),
                      for (final contribution in demand.contributions)
                        Text(
                          '　　${contribution.sourceItemName}: '
                          '${contribution.amount.toStringAsFixed(3)} ${contribution.unit}',
                        ),
                      Text(
                        '${t('raw_quantity_label')}: ${demand.rawQuantity.toStringAsFixed(3)} ${demand.unit}',
                      ),
                      Text('${t('reserve_label')}: ${(demand.reservePct * 100).toStringAsFixed(0)}%'),
                      Text(
                        '${t('qty_after_reserve_label')}: '
                        '${demand.quantityAfterReserve.toStringAsFixed(3)} ${demand.unit}',
                      ),
                    ],
                  ),
                ),
              ],
            ),

        const Divider(height: 32),

        // --- Purchase Plan ---
        Text(t('purchase_plan_header'), style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (result.purchasePlan.isEmpty)
          Text(t('no_purchase_plan'), style: Theme.of(context).textTheme.bodySmall)
        else
          for (final planItem in result.purchasePlan)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Text(
                '- ${planItem.name}: '
                '${planItem.skuBreakdown.isEmpty ? '–' : planItem.skuBreakdown.map((b) => '${b.count} × ${_formatG(b.size)} ${b.unit}'
                    '${b.packLabel.isNotEmpty ? ' (${b.packLabel})' : ''}').join(', ')} '
                '(${t('total_purchased_label')}: ${planItem.totalPurchasedQuantity.toStringAsFixed(2)} ${planItem.unit})',
              ),
            ),

        const Divider(height: 32),

        // --- Eisbedarf ---
        Text(t('ice_demand_label'), style: Theme.of(context).textTheme.titleMedium),
        Text('${result.iceDemandKg.toStringAsFixed(2)} kg'),

        const SizedBox(height: 16),

        // --- Review Issues ---
        if (result.reviewIssues.isNotEmpty) ...[
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: Text(t('review_issues_header', {'n': result.reviewIssues.length})),
            children: [
              for (final issue in result.reviewIssues)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Text(
                    '- [${issue.issueType}] ${issue.message}'
                    '${issue.guestName.isNotEmpty ? ' (${t('from_guest', {'name': issue.guestName})})' : ''}',
                  ),
                ),
            ],
          ),
        ] else
          Text(t('no_review_issues'), style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}
