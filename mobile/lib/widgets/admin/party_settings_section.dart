import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../i18n/translate.dart';
import '../../models/event_type.dart';
import '../../models/party_settings.dart';
import '../../state/admin_providers.dart';
import '../../state/providers.dart';

/// Admin-Sektion "Party-Einstellungen" (mirroring
/// `render_party_settings_section` in `"Party Planning.py"`): Event-Typ,
/// Party-Name, Datum, Startzeit, Dauer, Ort - beeinflusst nur Optik/Text,
/// nicht den Getränke-/Essenskatalog.
class PartySettingsSection extends ConsumerStatefulWidget {
  const PartySettingsSection({super.key});

  @override
  ConsumerState<PartySettingsSection> createState() => _PartySettingsSectionState();
}

class _PartySettingsSectionState extends ConsumerState<PartySettingsSection> {
  final _nameController = TextEditingController();
  final _locationController = TextEditingController();
  final _durationController = TextEditingController();
  String? _eventType;
  DateTime? _date;
  TimeOfDay _time = const TimeOfDay(hour: 19, minute: 0);
  bool _initialized = false;
  bool _saving = false;

  @override
  void dispose() {
    _nameController.dispose();
    _locationController.dispose();
    _durationController.dispose();
    super.dispose();
  }

  void _initFrom(PartySettings settings) {
    if (_initialized) return;
    _initialized = true;
    _nameController.text = settings.partyName;
    _locationController.text = settings.partyLocation;
    _durationController.text = settings.partyDurationHours.toString();
    _eventType = settings.eventType;
    _date = settings.partyDate.isEmpty ? null : DateTime.tryParse(settings.partyDate);
    if (settings.partyStartTime.isNotEmpty) {
      final parts = settings.partyStartTime.split(':');
      _time = TimeOfDay(hour: int.parse(parts[0]), minute: int.parse(parts[1]));
    }
  }

  @override
  Widget build(BuildContext context) {
    final translationsAsync = ref.watch(translationsProvider('de'));
    final settingsAsync = ref.watch(partySettingsProvider);
    final eventTypesAsync = ref.watch(eventTypesProvider);

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
            child: Text('Party-Settings konnten nicht geladen werden.\n$err'),
          ),
          data: (settings) {
            _initFrom(settings);

            return Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(t('party_settings_header'), style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 16),
                    eventTypesAsync.when(
                      loading: () => const LinearProgressIndicator(),
                      error: (err, stack) => Text('Event-Typen konnten nicht geladen werden.\n$err'),
                      data: (eventTypes) => _EventTypeDropdown(
                        eventTypes: eventTypes,
                        value: _eventType,
                        label: t('event_type_label'),
                        onChanged: (value) => setState(() => _eventType = value),
                      ),
                    ),
                    const SizedBox(height: 16),
                    TextField(
                      controller: _nameController,
                      decoration: InputDecoration(
                        labelText: t('party_name_label'),
                        border: const OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 16),
                    InkWell(
                      onTap: () async {
                        final picked = await showDatePicker(
                          context: context,
                          initialDate: _date ?? DateTime.now(),
                          firstDate: DateTime(2000),
                          lastDate: DateTime(2100),
                        );
                        if (picked != null) setState(() => _date = picked);
                      },
                      child: InputDecorator(
                        decoration: InputDecoration(
                          labelText: t('party_date_label'),
                          border: const OutlineInputBorder(),
                        ),
                        child: Text(_date == null
                            ? ''
                            : '${_date!.year.toString().padLeft(4, '0')}-${_date!.month.toString().padLeft(2, '0')}-${_date!.day.toString().padLeft(2, '0')}'),
                      ),
                    ),
                    const SizedBox(height: 16),
                    InkWell(
                      onTap: () async {
                        final picked = await showTimePicker(context: context, initialTime: _time);
                        if (picked != null) setState(() => _time = picked);
                      },
                      child: InputDecorator(
                        decoration: InputDecoration(
                          labelText: t('party_start_time_label'),
                          border: const OutlineInputBorder(),
                        ),
                        child: Text(
                          '${_time.hour.toString().padLeft(2, '0')}:${_time.minute.toString().padLeft(2, '0')}',
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    TextField(
                      controller: _durationController,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      decoration: InputDecoration(
                        labelText: t('party_duration_label'),
                        border: const OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 16),
                    TextField(
                      controller: _locationController,
                      decoration: InputDecoration(
                        labelText: t('party_location_label'),
                        border: const OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 20),
                    Align(
                      alignment: Alignment.centerRight,
                      child: ElevatedButton(
                        onPressed: _saving || _eventType == null ? null : () => _save(t),
                        child: _saving
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : Text(t('btn_save_party_settings')),
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
    final duration = double.tryParse(_durationController.text.replaceAll(',', '.')) ?? 7.0;
    final settings = PartySettings(
      eventType: _eventType!,
      partyName: _nameController.text,
      partyDate: _date == null
          ? ''
          : '${_date!.year.toString().padLeft(4, '0')}-${_date!.month.toString().padLeft(2, '0')}-${_date!.day.toString().padLeft(2, '0')}',
      partyStartTime: '${_time.hour.toString().padLeft(2, '0')}:${_time.minute.toString().padLeft(2, '0')}',
      partyDurationHours: duration,
      partyLocation: _locationController.text,
    );

    setState(() => _saving = true);
    try {
      final resetHappened = await ref.read(partySettingsProvider.notifier).save(settings);
      if (!mounted) return;
      setState(() => _saving = false);
      final message = resetHappened ? t('party_settings_reset_notice') : t('party_settings_saved');
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    } catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Speichern fehlgeschlagen: $e')));
    }
  }
}

class _EventTypeDropdown extends StatelessWidget {
  final List<EventType> eventTypes;
  final String? value;
  final String label;
  final ValueChanged<String?> onChanged;

  const _EventTypeDropdown({
    required this.eventTypes,
    required this.value,
    required this.label,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return DropdownButtonFormField<String>(
      initialValue: value,
      decoration: InputDecoration(labelText: label, border: const OutlineInputBorder()),
      items: [
        for (final eventType in eventTypes)
          DropdownMenuItem(
            value: eventType.id,
            child: Text('${eventType.emoji} ${eventType.label('de')}'),
          ),
      ],
      onChanged: onChanged,
    );
  }
}
