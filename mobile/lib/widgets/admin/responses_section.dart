import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';

import '../../i18n/translate.dart';
import '../../models/guest_response.dart';
import '../../state/admin_providers.dart';
import '../../state/providers.dart';

/// Admin-Sektion für die Gäste-Antworten + CSV-Export (mirroring den
/// Antworten-Teil von `render_admin_view()`: `metric_responses` ->
/// `btn_csv`-Download -> `raw_responses_expander`). Der Einkaufslisten-Button
/// aus derselben Streamlit-Sektion ist bewusst eine eigene Sektion
/// (`ShoppingListSection`), damit beide unabhängig scrollbar/kollabierbar
/// bleiben.
class ResponsesSection extends ConsumerWidget {
  const ResponsesSection({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final translationsAsync = ref.watch(translationsProvider('de'));
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

        return responsesAsync.when(
          loading: () => const Padding(
            padding: EdgeInsets.all(20),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (err, stack) => Padding(
            padding: const EdgeInsets.all(20),
            child: Text('Antworten konnten nicht geladen werden.\n$err'),
          ),
          data: (responses) {
            if (responses.isEmpty) {
              return Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Text(t('no_responses_yet')),
                ),
              );
            }

            return Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(t('metric_responses'), style: Theme.of(context).textTheme.bodySmall),
                    Text('${responses.length}', style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 16),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: OutlinedButton.icon(
                        icon: const Icon(Icons.download, size: 18),
                        label: Text(t('btn_csv')),
                        onPressed: () => _exportCsv(ref),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(t('csv_help'), style: Theme.of(context).textTheme.bodySmall),
                    ),
                    const SizedBox(height: 8),
                    ExpansionTile(
                      tilePadding: EdgeInsets.zero,
                      title: Text(t('raw_responses_expander')),
                      children: [
                        for (final r in responses) _ResponseTile(response: r),
                      ],
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

  Future<void> _exportCsv(WidgetRef ref) async {
    final token = ref.read(adminAuthProvider).value;
    if (token == null) return;
    final csvBytes = await ref.read(apiClientProvider).getResponsesCsv(token);
    await Share.shareXFiles(
      [
        XFile.fromData(
          Uint8List.fromList(csvBytes),
          name: 'party_antworten.csv',
          mimeType: 'text/csv',
        ),
      ],
    );
  }
}

class _ResponseTile extends StatelessWidget {
  final GuestResponse response;

  const _ResponseTile({required this.response});

  @override
  Widget build(BuildContext context) {
    final drinks = response.drinksDisplay.isEmpty ? '–' : response.drinksDisplay.join(', ');
    final extraDrinks = response.drinksFreetext.isEmpty ? '' : ' + ${response.drinksFreetext}';
    final food = response.foodDisplay.isEmpty ? '–' : response.foodDisplay.join(', ');
    final extraFood = response.foodFreetext.isEmpty ? '' : ' + ${response.foodFreetext}';
    final songs = response.songsDisplay.isEmpty ? '–' : response.songsDisplay;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Text(
        '${response.name} – ${response.startTime} | $drinks$extraDrinks | $food$extraFood | $songs',
      ),
    );
  }
}
