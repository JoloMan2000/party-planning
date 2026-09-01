import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../i18n/translate.dart';
import '../../models/derived_party_context.dart';
import '../../state/admin_providers.dart';
import '../../state/providers.dart';

const _countrySourceLabelKeys = {
  'admin_override': 'party_context_country_source_admin',
  'geocoded': 'party_context_country_source_geocoded',
};

/// Rein informatives Read-Only-Dashboard der abgeleiteten Party-Wahrheit
/// (mirroring `render_party_context_dashboard` in `"Party Planning.py"`) -
/// zeigt WAS aus den Party-Context-Eingaben abgeleitet wurde, verändert
/// selbst nichts.
class PartyContextDashboardSection extends ConsumerWidget {
  const PartyContextDashboardSection({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final translationsAsync = ref.watch(translationsProvider('de'));
    final derivedAsync = ref.watch(derivedPartyContextProvider);

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

        return derivedAsync.when(
          loading: () => const Padding(
            padding: EdgeInsets.all(20),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (err, stack) => Padding(
            padding: const EdgeInsets.all(20),
            child: Text('Context-Dashboard konnte nicht geladen werden.\n$err'),
          ),
          data: (derived) => Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t('party_context_dashboard_header'), style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 24,
                    runSpacing: 12,
                    children: [
                      _Metric(
                        label: t('party_context_season_label'),
                        value: t(seasonLabelKeys[derived.season] ?? derived.season),
                      ),
                      _Metric(
                        label: t('party_context_daypart_label'),
                        value: t(daypartLabelKeys[derived.daypartPrimary] ?? derived.daypartPrimary),
                      ),
                      _Metric(
                        label: t('party_context_temperature_class_label'),
                        value: t(temperatureClassLabelKeys[derived.temperatureClass] ?? derived.temperatureClass),
                      ),
                      _Metric(
                        label: t('party_context_group_size_label'),
                        value: t(groupSizeLabelKeys[derived.groupSizeClass] ?? derived.groupSizeClass),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Text('${t('party_context_constraints_label')}:',
                      style: const TextStyle(fontWeight: FontWeight.bold)),
                  if (derived.operationalConstraints.isEmpty)
                    Text(t('party_context_constraints_none'), style: Theme.of(context).textTheme.bodySmall)
                  else
                    Text((derived.operationalConstraints.toList()..sort())
                        .map((c) => c.replaceAll('_', ' '))
                        .join(', ')),
                  const SizedBox(height: 16),
                  Text('${t('party_context_country_label')}:',
                      style: const TextStyle(fontWeight: FontWeight.bold)),
                  if (derived.countryCode.isEmpty)
                    Text(t('party_context_country_none'), style: Theme.of(context).textTheme.bodySmall)
                  else
                    Text(
                      '${derived.countryName} (${derived.countryCode}) — '
                      '${t(_countrySourceLabelKeys[derived.countrySource] ?? 'party_context_country_source_unknown')}',
                    ),
                  const SizedBox(height: 16),
                  ExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    title: Text(t('party_context_explanations_expander')),
                    children: [
                      for (final explanation in derived.explanations)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 2),
                          child: Text('- $explanation'),
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

class _Metric extends StatelessWidget {
  final String label;
  final String value;

  const _Metric({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Theme.of(context).textTheme.bodySmall),
        Text(value, style: Theme.of(context).textTheme.titleMedium),
      ],
    );
  }
}
