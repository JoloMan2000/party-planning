import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../i18n/translate.dart';
import '../../state/admin_providers.dart';
import '../../state/providers.dart';

/// Admin-Sortiment-Empfehlungen (mirroring `render_recommendations_section`
/// in `"Party Planning.py"`): rein informativer Vorschlag für den Sortiment-
/// Aufbau basierend auf dem aktuell konfigurierten Event-Typ. Erzeugt
/// garantiert keine Demand/Preference und kauft/wählt nichts automatisch.
class RecommendationsSection extends ConsumerWidget {
  const RecommendationsSection({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final translationsAsync = ref.watch(translationsProvider('de'));
    final recommendationsAsync = ref.watch(adminRecommendationsProvider);

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

        return recommendationsAsync.when(
          loading: () => const Padding(
            padding: EdgeInsets.all(20),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (err, stack) => Padding(
            padding: const EdgeInsets.all(20),
            child: Text('Empfehlungen konnten nicht geladen werden.\n$err'),
          ),
          data: (recommendations) => Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    t('admin_recommendations_header', {'occasion': recommendations.occasionLabel}),
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 4),
                  Text(t('admin_recommendations_caption'), style: Theme.of(context).textTheme.bodySmall),
                  const SizedBox(height: 16),
                  for (final rec in recommendations.items)
                    ExpansionTile(
                      tilePadding: EdgeInsets.zero,
                      title: Text('${rec.itemName} — ${rec.totalScore.toStringAsFixed(2)}'),
                      children: [
                        Align(
                          alignment: Alignment.centerLeft,
                          child: Padding(
                            padding: const EdgeInsets.only(bottom: 12),
                            child: Text(rec.explanation, style: const TextStyle(fontFamily: 'monospace')),
                          ),
                        ),
                      ],
                    ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
