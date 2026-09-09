import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../geo/debounce.dart';
import '../geo/geo_models.dart';
import '../models/discovery_preferences.dart';
import '../state/geo_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

// Freiform-Strings serverseitig (kein Enum/Catalog-Endpoint, siehe
// accounts/discovery_storage.py) - diese Options-Listen sind eine reine
// Client-Konvention. Wochentage/Dayparts spiegeln exakt die Werte, die
// accounts/discover_ranking.py::_timing_fit tatsächlich vergleicht
// (strftime("%A").lower() bzw. _DAYPART_HOURS-Keys + "late_night"-Fallback).
const _kWeekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const _kDayparts = ['morning', 'afternoon', 'evening', 'late_night'];
const _kPricePreferences = ['free', 'budget', 'moderate', 'premium'];

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
  Set<String> _preferredDays = {};
  Set<String> _preferredDayparts = {};
  String _pricePreference = '';
  double _mainstreamDiscovery = 0.5;
  bool _personalizedRecommendationsEnabled = true;
  bool _resettingLearning = false;

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
    _preferredDays = prefs.preferredDays.toSet();
    _preferredDayparts = prefs.preferredDayparts.toSet();
    _pricePreference = prefs.pricePreference;
    _mainstreamDiscovery = prefs.mainstreamDiscovery;
    _personalizedRecommendationsEnabled = prefs.personalizedRecommendationsEnabled;
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
              preferredDays: _preferredDays.toList(),
              preferredDayparts: _preferredDayparts.toList(),
              pricePreference: _pricePreference,
              mainstreamDiscovery: _mainstreamDiscovery,
              personalizedRecommendationsEnabled: _personalizedRecommendationsEnabled,
            ),
          );
      if (mounted) messenger.showSnackBar(const SnackBar(content: Text('Discovery preferences saved.')));
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to save. Please try again.')));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _confirmAndResetLearning() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Reset personalization?'),
        content: const Text(
          'This clears what Discover has learned from your swipes. Your explicit preferences '
          '(radius, city, days, etc.) and blocked organizers are not affected.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Reset')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _resettingLearning = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(discoveryPreferencesProvider.notifier).resetLearning();
      if (mounted) messenger.showSnackBar(const SnackBar(content: Text('Personalization reset.')));
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to reset. Please try again.')));
    } finally {
      if (mounted) setState(() => _resettingLearning = false);
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
                const SizedBox(height: 24),
                Text('Preferred days', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  children: _kWeekdays
                      .map((day) => FilterChip(
                            label: Text(day[0].toUpperCase() + day.substring(1)),
                            selected: _preferredDays.contains(day),
                            onSelected: (selected) => setState(() {
                              if (selected) {
                                _preferredDays.add(day);
                              } else {
                                _preferredDays.remove(day);
                              }
                            }),
                          ))
                      .toList(),
                ),
                const SizedBox(height: 20),
                Text('Preferred times of day', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  children: _kDayparts
                      .map((daypart) => FilterChip(
                            label: Text(daypart.replaceAll('_', ' ')),
                            selected: _preferredDayparts.contains(daypart),
                            onSelected: (selected) => setState(() {
                              if (selected) {
                                _preferredDayparts.add(daypart);
                              } else {
                                _preferredDayparts.remove(daypart);
                              }
                            }),
                          ))
                      .toList(),
                ),
                const SizedBox(height: 20),
                Text('Price preference', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  children: _kPricePreferences
                      .map((price) => ChoiceChip(
                            label: Text(price[0].toUpperCase() + price.substring(1)),
                            selected: _pricePreference == price,
                            onSelected: (selected) => setState(() => _pricePreference = selected ? price : ''),
                          ))
                      .toList(),
                ),
                const SizedBox(height: 20),
                Text(
                  'Mainstream vs. niche: ${(_mainstreamDiscovery * 100).round()}%',
                  style: Theme.of(context).textTheme.titleSmall,
                ),
                Slider(
                  value: _mainstreamDiscovery,
                  min: 0,
                  max: 1,
                  divisions: 20,
                  label: '${(_mainstreamDiscovery * 100).round()}%',
                  onChanged: (value) => setState(() => _mainstreamDiscovery = value),
                ),
                const SizedBox(height: 12),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Personalized recommendations'),
                  subtitle: const Text('Use your swipe history to improve your deck.'),
                  value: _personalizedRecommendationsEnabled,
                  onChanged: (value) => setState(() => _personalizedRecommendationsEnabled = value),
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
                const SizedBox(height: 12),
                OutlinedButton(
                  onPressed: _resettingLearning ? null : _confirmAndResetLearning,
                  child: _resettingLearning
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Reset personalization'),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
