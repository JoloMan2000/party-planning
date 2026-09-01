import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../i18n/translate.dart';
import '../../models/party_context_override.dart';
import '../../state/admin_providers.dart';
import '../../state/providers.dart';

/// Admin-Sektion "Context-Overrides" (mirroring
/// `render_party_context_overrides_section` in `"Party Planning.py"`):
/// erlaubt gezieltes Überschreiben einzelner abgeleiteter Top-Level-Felder
/// (z.B. "Zelt mit Heizung -> temperature_class warm trotz Winter").
/// Overrides sind stärker als abgeleitete Defaults.
class PartyContextOverridesSection extends ConsumerStatefulWidget {
  const PartyContextOverridesSection({super.key});

  @override
  ConsumerState<PartyContextOverridesSection> createState() => _PartyContextOverridesSectionState();
}

class _PartyContextOverridesSectionState extends ConsumerState<PartyContextOverridesSection> {
  String _chosenKey = overrideKeyOptions.keys.first;
  String _chosenValue = overrideKeyOptions.values.first.first;
  final _reasonController = TextEditingController();
  bool _adding = false;

  @override
  void dispose() {
    _reasonController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final translationsAsync = ref.watch(translationsProvider('de'));
    final overridesAsync = ref.watch(partyContextOverridesProvider);

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

        return overridesAsync.when(
          loading: () => const Padding(
            padding: EdgeInsets.all(20),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (err, stack) => Padding(
            padding: const EdgeInsets.all(20),
            child: Text('Overrides konnten nicht geladen werden.\n$err'),
          ),
          data: (overrides) {
            final valueOptions = overrideKeyOptions[_chosenKey]!;
            if (!valueOptions.contains(_chosenValue)) {
              _chosenValue = valueOptions.first;
            }
            final valueLabelKeys = overrideValueLabelKeys[_chosenKey]!;

            return Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(t('party_context_override_header'), style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 4),
                    Text(t('party_context_override_caption'), style: Theme.of(context).textTheme.bodySmall),
                    const SizedBox(height: 16),
                    if (overrides.isEmpty)
                      Text(t('party_context_overrides_none'), style: Theme.of(context).textTheme.bodySmall)
                    else
                      for (final override in overrides)
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text(
                            '${override.key} = ${override.value}'
                            '${override.reason != null ? ' (${override.reason})' : ''}',
                          ),
                          trailing: IconButton(
                            icon: const Icon(Icons.delete_outline),
                            onPressed: () =>
                                ref.read(partyContextOverridesProvider.notifier).remove(override.key),
                          ),
                        ),
                    const Divider(),
                    const SizedBox(height: 8),
                    DropdownButtonFormField<String>(
                      initialValue: _chosenKey,
                      decoration: InputDecoration(
                        labelText: t('override_key_label'),
                        border: const OutlineInputBorder(),
                      ),
                      items: [
                        for (final key in overrideKeyOptions.keys)
                          DropdownMenuItem(value: key, child: Text(t(overrideKeyLabelKeys[key]!))),
                      ],
                      onChanged: (value) => setState(() {
                        _chosenKey = value ?? _chosenKey;
                        _chosenValue = overrideKeyOptions[_chosenKey]!.first;
                      }),
                    ),
                    const SizedBox(height: 16),
                    DropdownButtonFormField<String>(
                      initialValue: _chosenValue,
                      decoration: InputDecoration(
                        labelText: t('override_value_label'),
                        border: const OutlineInputBorder(),
                      ),
                      items: [
                        for (final value in valueOptions)
                          DropdownMenuItem(value: value, child: Text(t(valueLabelKeys[value]!))),
                      ],
                      onChanged: (value) => setState(() => _chosenValue = value ?? _chosenValue),
                    ),
                    const SizedBox(height: 16),
                    TextField(
                      controller: _reasonController,
                      decoration: InputDecoration(
                        labelText: t('override_reason_label'),
                        border: const OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 20),
                    Align(
                      alignment: Alignment.centerRight,
                      child: ElevatedButton(
                        onPressed: _adding ? null : () => _add(t),
                        child: _adding
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : Text(t('btn_add_override')),
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

  Future<void> _add(String Function(String, [Map<String, Object?>]) t) async {
    setState(() => _adding = true);
    try {
      final reason = _reasonController.text.trim();
      await ref
          .read(partyContextOverridesProvider.notifier)
          .add(_chosenKey, _chosenValue, reason.isEmpty ? null : reason);
      if (!mounted) return;
      _reasonController.clear();
      setState(() => _adding = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t('override_added'))));
    } catch (e) {
      if (!mounted) return;
      setState(() => _adding = false);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Hinzufügen fehlgeschlagen: $e')));
    }
  }
}
