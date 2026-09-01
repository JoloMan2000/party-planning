import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../i18n/translate.dart';
import '../../models/party_context.dart';
import '../../state/admin_providers.dart';
import '../../state/providers.dart';

const _weatherConditionOptions = ['', 'sunny', 'cloudy', 'rain', 'snow', 'windy'];
const _weatherConditionLabelKeys = {
  '': 'weather_condition_none',
  'sunny': 'weather_condition_sunny',
  'cloudy': 'weather_condition_cloudy',
  'rain': 'weather_condition_rain',
  'snow': 'weather_condition_snow',
  'windy': 'weather_condition_windy',
};
const _indoorOutdoorOptions = ['indoor', 'outdoor', 'mixed'];
const _indoorOutdoorLabelKeys = {
  'indoor': 'indoor_outdoor_indoor',
  'outdoor': 'indoor_outdoor_outdoor',
  'mixed': 'indoor_outdoor_mixed',
};

/// Admin-Sektion "Party-Kontext" (mirroring `render_party_context_section` in
/// `"Party Planning.py"`): Location-Typ, Indoor/Outdoor, Länder-Override,
/// Infrastruktur-Checkboxen, Sitzplatz-Anteil, Wetter - fließt in Getränke-/
/// Essens-/Musik-Empfehlungen ein. Anlass/Datum/Startzeit/Dauer kommen bereits
/// aus der Party-Settings-Sektion und werden hier NICHT erneut abgefragt.
class PartyContextSection extends ConsumerStatefulWidget {
  const PartyContextSection({super.key});

  @override
  ConsumerState<PartyContextSection> createState() => _PartyContextSectionState();
}

class _PartyContextSectionState extends ConsumerState<PartyContextSection> {
  String? _locationType;
  String _indoorOutdoor = 'outdoor';
  String _countryCode = '';
  bool _hasGrill = false;
  bool _hasKitchen = false;
  bool _hasFridge = false;
  bool _hasFreezer = false;
  bool _hasIceMachine = false;
  bool _hasBar = false;
  bool _hasCoffeeMachine = false;
  bool _hasPower = false;
  bool _hasRunningWater = false;
  bool _dancingPossible = false;
  bool _neighborsSensitive = false;
  bool _volumeLimited = false;
  bool _selfService = true;
  double _seatingRatioPct = 0;
  String _weatherCondition = '';
  double _expectedTemperatureC = 20;
  bool _initialized = false;
  bool _saving = false;

  void _initFrom(PartyContext ctx) {
    if (_initialized) return;
    _initialized = true;
    _locationType = ctx.locationType;
    _indoorOutdoor = ctx.indoorOutdoor;
    _countryCode = ctx.countryCode;
    _hasGrill = ctx.hasGrill;
    _hasKitchen = ctx.hasKitchen;
    _hasFridge = ctx.hasFridge;
    _hasFreezer = ctx.hasFreezer;
    _hasIceMachine = ctx.hasIceMachine;
    _hasBar = ctx.hasBar;
    _hasCoffeeMachine = ctx.hasCoffeeMachine;
    _hasPower = ctx.hasPower;
    _hasRunningWater = ctx.hasRunningWater;
    _dancingPossible = ctx.dancingPossible;
    _neighborsSensitive = ctx.neighborsSensitive;
    _volumeLimited = ctx.musicVolumeLimit != null;
    _selfService = ctx.selfService;
    _seatingRatioPct = (ctx.seatingRatio ?? 0.0) * 100;
    _weatherCondition = ctx.weatherCondition ?? '';
    _expectedTemperatureC = ctx.expectedTemperatureC ?? 20;
  }

  @override
  Widget build(BuildContext context) {
    final translationsAsync = ref.watch(translationsProvider('de'));
    final contextAsync = ref.watch(partyContextProvider);
    final metadataAsync = ref.watch(partyContextMetadataProvider);

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

        return contextAsync.when(
          loading: () => const Padding(
            padding: EdgeInsets.all(20),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (err, stack) => Padding(
            padding: const EdgeInsets.all(20),
            child: Text('Party-Kontext konnte nicht geladen werden.\n$err'),
          ),
          data: (ctx) {
            _initFrom(ctx);

            return metadataAsync.when(
              loading: () => const Padding(
                padding: EdgeInsets.all(20),
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (err, stack) => Padding(
                padding: const EdgeInsets.all(20),
                child: Text('Stammdaten konnten nicht geladen werden.\n$err'),
              ),
              data: (metadata) => Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(t('party_context_header'), style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 4),
                      Text(t('party_context_caption'), style: Theme.of(context).textTheme.bodySmall),
                      const SizedBox(height: 16),
                      DropdownButtonFormField<String>(
                        initialValue: metadata.locationTypes.any((l) => l.id == _locationType)
                            ? _locationType
                            : null,
                        decoration: InputDecoration(
                          labelText: t('party_context_location_type_label'),
                          border: const OutlineInputBorder(),
                        ),
                        items: [
                          for (final loc in metadata.locationTypes)
                            DropdownMenuItem(value: loc.id, child: Text(loc.label('de'))),
                        ],
                        onChanged: (value) => setState(() => _locationType = value),
                      ),
                      const SizedBox(height: 16),
                      DropdownButtonFormField<String>(
                        initialValue: _indoorOutdoor,
                        decoration: InputDecoration(
                          labelText: t('party_context_indoor_outdoor_label'),
                          border: const OutlineInputBorder(),
                        ),
                        items: [
                          for (final key in _indoorOutdoorOptions)
                            DropdownMenuItem(value: key, child: Text(t(_indoorOutdoorLabelKeys[key]!))),
                        ],
                        onChanged: (value) => setState(() => _indoorOutdoor = value ?? _indoorOutdoor),
                      ),
                      const SizedBox(height: 16),
                      DropdownButtonFormField<String>(
                        initialValue: _countryCode,
                        decoration: InputDecoration(
                          labelText: t('party_context_country_override_label'),
                          border: const OutlineInputBorder(),
                        ),
                        items: [
                          DropdownMenuItem(value: '', child: Text(t('country_override_auto'))),
                          for (final country in metadata.countries)
                            DropdownMenuItem(
                              value: country.code,
                              child: Text('${country.code} — ${country.name}'),
                            ),
                        ],
                        onChanged: (value) => setState(() => _countryCode = value ?? ''),
                      ),
                      const SizedBox(height: 4),
                      Text(t('party_context_country_override_caption'),
                          style: Theme.of(context).textTheme.bodySmall),
                      const SizedBox(height: 16),
                      Text(t('party_context_infrastructure_label'),
                          style: Theme.of(context).textTheme.titleSmall),
                      CheckboxListTile(
                        value: _hasGrill,
                        title: Text(t('has_grill_label')),
                        onChanged: (v) => setState(() => _hasGrill = v ?? false),
                      ),
                      CheckboxListTile(
                        value: _hasKitchen,
                        title: Text(t('has_kitchen_label')),
                        onChanged: (v) => setState(() => _hasKitchen = v ?? false),
                      ),
                      CheckboxListTile(
                        value: _hasFridge,
                        title: Text(t('has_fridge_label')),
                        onChanged: (v) => setState(() => _hasFridge = v ?? false),
                      ),
                      CheckboxListTile(
                        value: _hasFreezer,
                        title: Text(t('has_freezer_label')),
                        onChanged: (v) => setState(() => _hasFreezer = v ?? false),
                      ),
                      CheckboxListTile(
                        value: _hasIceMachine,
                        title: Text(t('has_ice_machine_label')),
                        onChanged: (v) => setState(() => _hasIceMachine = v ?? false),
                      ),
                      CheckboxListTile(
                        value: _hasBar,
                        title: Text(t('has_bar_label')),
                        onChanged: (v) => setState(() => _hasBar = v ?? false),
                      ),
                      CheckboxListTile(
                        value: _hasCoffeeMachine,
                        title: Text(t('has_coffee_machine_label')),
                        onChanged: (v) => setState(() => _hasCoffeeMachine = v ?? false),
                      ),
                      CheckboxListTile(
                        value: _hasPower,
                        title: Text(t('has_power_label')),
                        onChanged: (v) => setState(() => _hasPower = v ?? false),
                      ),
                      CheckboxListTile(
                        value: _hasRunningWater,
                        title: Text(t('has_running_water_label')),
                        onChanged: (v) => setState(() => _hasRunningWater = v ?? false),
                      ),
                      const Divider(),
                      CheckboxListTile(
                        value: _dancingPossible,
                        title: Text(t('dancing_possible_label')),
                        onChanged: (v) => setState(() => _dancingPossible = v ?? false),
                      ),
                      CheckboxListTile(
                        value: _neighborsSensitive,
                        title: Text(t('neighbors_sensitive_label')),
                        onChanged: (v) => setState(() => _neighborsSensitive = v ?? false),
                      ),
                      CheckboxListTile(
                        value: _volumeLimited,
                        title: Text(t('music_volume_limit_label')),
                        onChanged: (v) => setState(() => _volumeLimited = v ?? false),
                      ),
                      CheckboxListTile(
                        value: _selfService,
                        title: Text(t('self_service_label')),
                        onChanged: (v) => setState(() => _selfService = v ?? true),
                      ),
                      const SizedBox(height: 16),
                      Text('${t('seating_ratio_label')}: ${_seatingRatioPct.round()}%'),
                      Slider(
                        value: _seatingRatioPct,
                        min: 0,
                        max: 100,
                        divisions: 20,
                        label: '${_seatingRatioPct.round()}%',
                        onChanged: (v) => setState(() => _seatingRatioPct = v),
                      ),
                      const SizedBox(height: 16),
                      DropdownButtonFormField<String>(
                        initialValue: _weatherCondition,
                        decoration: InputDecoration(
                          labelText: t('weather_condition_label'),
                          border: const OutlineInputBorder(),
                        ),
                        items: [
                          for (final key in _weatherConditionOptions)
                            DropdownMenuItem(value: key, child: Text(t(_weatherConditionLabelKeys[key]!))),
                        ],
                        onChanged: (value) => setState(() => _weatherCondition = value ?? ''),
                      ),
                      const SizedBox(height: 16),
                      TextFormField(
                        initialValue: _expectedTemperatureC.toStringAsFixed(0),
                        keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                        decoration: InputDecoration(
                          labelText: t('expected_temperature_label'),
                          border: const OutlineInputBorder(),
                        ),
                        onChanged: (value) {
                          final parsed = double.tryParse(value.replaceAll(',', '.'));
                          if (parsed != null) _expectedTemperatureC = parsed;
                        },
                      ),
                      const SizedBox(height: 20),
                      Align(
                        alignment: Alignment.centerRight,
                        child: ElevatedButton(
                          onPressed: _saving || _locationType == null ? null : () => _save(t),
                          child: _saving
                              ? const SizedBox(
                                  width: 20,
                                  height: 20,
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                )
                              : Text(t('btn_save_party_context')),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        );
      },
    );
  }

  Future<void> _save(String Function(String, [Map<String, Object?>]) t) async {
    final ctx = PartyContext(
      locationType: _locationType!,
      indoorOutdoor: _indoorOutdoor,
      countryCode: _countryCode,
      hasGrill: _hasGrill,
      hasKitchen: _hasKitchen,
      hasFridge: _hasFridge,
      hasFreezer: _hasFreezer,
      hasIceMachine: _hasIceMachine,
      hasBar: _hasBar,
      hasCoffeeMachine: _hasCoffeeMachine,
      hasPower: _hasPower,
      hasRunningWater: _hasRunningWater,
      dancingPossible: _dancingPossible,
      neighborsSensitive: _neighborsSensitive,
      musicVolumeLimit: _volumeLimited ? 'limited' : null,
      selfService: _selfService,
      seatingRatio: _seatingRatioPct / 100.0,
      weatherCondition: _weatherCondition.isEmpty ? null : _weatherCondition,
      expectedTemperatureC: _expectedTemperatureC,
    );

    setState(() => _saving = true);
    try {
      await ref.read(partyContextProvider.notifier).save(ctx);
      if (!mounted) return;
      setState(() => _saving = false);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(t('party_context_saved'))));
    } catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Speichern fehlgeschlagen: $e')));
    }
  }
}
