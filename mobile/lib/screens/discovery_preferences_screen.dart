import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../geo/debounce.dart';
import '../geo/geo_models.dart';
import '../models/discovery_preferences.dart';
import '../state/geo_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Discover-Radius-/Ort-Einstellungen (bisher nur backend-seitig vorhanden,
/// nie über Mobile erreichbar - siehe Geo-Platform-Plan). Erreichbar über ein
/// Zahnrad-Icon im Discover-Tab (`HomeShell`).
class DiscoveryPreferencesScreen extends ConsumerStatefulWidget {
  const DiscoveryPreferencesScreen({super.key});

  @override
  ConsumerState<DiscoveryPreferencesScreen> createState() => _DiscoveryPreferencesScreenState();
}

class _DiscoveryPreferencesScreenState extends ConsumerState<DiscoveryPreferencesScreen> {
  final _cityController = TextEditingController();
  final _cityDebouncer = Debouncer();
  bool _initialized = false;
  bool _saving = false;

  double _radiusKm = 25.0;
  bool _allowMajorEvents = false;
  String _city = '';
  double? _lat;
  double? _lon;

  @override
  void dispose() {
    _cityController.dispose();
    _cityDebouncer.dispose();
    super.dispose();
  }

  void _seedFrom(DiscoveryPreferences prefs) {
    if (_initialized) return;
    _initialized = true;
    _radiusKm = prefs.discoveryRadiusKm;
    _allowMajorEvents = prefs.allowMajorEventsOutsideRadius;
    _city = prefs.discoveryCity;
    _lat = prefs.discoveryLat;
    _lon = prefs.discoveryLon;
    _cityController.text = prefs.discoveryCity;
  }

  void _onCityChanged(String query) {
    _cityDebouncer.run(() => ref.read(locationSearchProvider.notifier).suggest(query));
  }

  Future<void> _selectCity(GeoSuggestion suggestion) async {
    final place = await ref.read(locationSearchProvider.notifier).retrieve(suggestion.providerPlaceId);
    if (!mounted || place == null) return;
    ref.read(locationSearchProvider.notifier).clear();
    setState(() {
      _city = place.address.city ?? place.name;
      _lat = place.point?.latitude;
      _lon = place.point?.longitude;
      _cityController.text = _city;
    });
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final current = ref.read(discoveryPreferencesProvider).valueOrNull ?? const DiscoveryPreferences();
      await ref.read(discoveryPreferencesProvider.notifier).save(
            current.copyWith(
              discoveryRadiusKm: _radiusKm,
              allowMajorEventsOutsideRadius: _allowMajorEvents,
              discoveryCity: _city,
              discoveryLat: _lat,
              discoveryLon: _lon,
            ),
          );
      if (mounted) messenger.showSnackBar(const SnackBar(content: Text('Discovery preferences saved.')));
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to save. Please try again.')));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final prefsAsync = ref.watch(discoveryPreferencesProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Discovery Preferences'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(showDiscoveryPreferencesProvider.notifier).state = false,
        ),
      ),
      body: prefsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(discoveryPreferencesProvider),
            child: const Text('Failed to load preferences. Retry'),
          ),
        ),
        data: (prefs) {
          _seedFrom(prefs);
          final suggestionsAsync = ref.watch(locationSearchProvider);
          final suggestions = suggestionsAsync.maybeWhen(data: (s) => s, orElse: () => const <GeoSuggestion>[]);

          return SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Your city', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 8),
                TextField(
                  controller: _cityController,
                  onChanged: _onCityChanged,
                  decoration: const InputDecoration(
                    labelText: 'City',
                    border: OutlineInputBorder(),
                  ),
                ),
                if (suggestions.isNotEmpty)
                  Card(
                    margin: const EdgeInsets.only(top: 4),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: suggestions
                          .map((s) => ListTile(
                                dense: true,
                                title: Text(s.primaryText),
                                subtitle: s.secondaryText.isNotEmpty ? Text(s.secondaryText) : null,
                                onTap: () => _selectCity(s),
                              ))
                          .toList(),
                    ),
                  ),
                const SizedBox(height: 24),
                Text('Discovery radius: ${_radiusKm.round()} km', style: Theme.of(context).textTheme.titleSmall),
                Slider(
                  value: _radiusKm,
                  min: 5,
                  max: 100,
                  divisions: 19,
                  label: '${_radiusKm.round()} km',
                  onChanged: (value) => setState(() => _radiusKm = value),
                ),
                const SizedBox(height: 12),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Show major festivals farther away'),
                  subtitle: const Text('Includes large events outside your normal radius.'),
                  value: _allowMajorEvents,
                  onChanged: (value) => setState(() => _allowMajorEvents = value),
                ),
                const SizedBox(height: 20),
                ElevatedButton(
                  onPressed: _saving ? null : _save,
                  child: _saving
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Save'),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
