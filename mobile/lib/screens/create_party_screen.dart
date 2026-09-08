import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';

import '../geo/debounce.dart';
import '../geo/geo_models.dart';
import '../state/auth_providers.dart';
import '../state/geo_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Party-Erstellungsformular. Nach Erfolg landet der Nutzer direkt in
/// `PartyDetailScreen` (siehe `_submit`), nicht zurück in der Liste.
class CreatePartyScreen extends ConsumerStatefulWidget {
  const CreatePartyScreen({super.key});

  @override
  ConsumerState<CreatePartyScreen> createState() => _CreatePartyScreenState();
}

class _CreatePartyScreenState extends ConsumerState<CreatePartyScreen> {
  final _nameController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _locationController = TextEditingController();
  final _locationDebouncer = Debouncer();
  DateTime? _startsAt;
  String? _clientError;

  // Autocomplete/current-location Ergebnis - nur gesetzt, wenn der Host
  // tatsächlich eine Suggestion ausgewählt oder "Use current location"
  // genutzt hat. Bleibt `null` bei reiner Freitext-Eingabe (Spec §97: eine
  // down/leere Suche darf die Party-Erstellung nie blockieren - dann greift
  // exakt das alte Verhalten, ein reiner String im `location`-Feld).
  GeoPlace? _resolvedPlace;
  bool _requestingCurrentLocation = false;

  @override
  void dispose() {
    _nameController.dispose();
    _descriptionController.dispose();
    _locationController.dispose();
    _locationDebouncer.dispose();
    super.dispose();
  }

  void _onLocationChanged(String query) {
    if (_resolvedPlace != null) setState(() => _resolvedPlace = null);
    _locationDebouncer.run(() => ref.read(locationSearchProvider.notifier).suggest(query));
  }

  Future<void> _selectSuggestion(GeoSuggestion suggestion) async {
    final place = await ref.read(locationSearchProvider.notifier).retrieve(suggestion.providerPlaceId);
    if (!mounted) return;
    ref.read(locationSearchProvider.notifier).clear();
    setState(() {
      _resolvedPlace = place;
      _locationController.text = place?.name ?? suggestion.primaryText;
    });
  }

  Future<void> _useCurrentLocation() async {
    setState(() => _requestingCurrentLocation = true);
    try {
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Location permission denied.')),
          );
        }
        return;
      }
      final position = await Geolocator.getCurrentPosition();
      final place = await ref
          .read(locationSearchProvider.notifier)
          .reverseGeocode(position.latitude, position.longitude);
      if (!mounted) return;
      if (place == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not resolve an address for your location.')),
        );
        return;
      }
      setState(() {
        _resolvedPlace = place;
        _locationController.text = place.name;
      });
    } catch (_) {
      // Provider down/GPS aus/etc. - darf die Party-Erstellung nie blockieren.
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not determine current location.')),
        );
      }
    } finally {
      if (mounted) setState(() => _requestingCurrentLocation = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final createState = ref.watch(createPartyProvider);
    final isLoading = createState.isLoading;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Create Party'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => ref.read(creatingPartyProvider.notifier).state = false,
        ),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextField(
                controller: _nameController,
                autofocus: true,
                // Spiegelt das Backend-Limit (`_NAME_MAX_LENGTH` in
                // `backend/app/schemas/accounts.py`), damit der Nutzer sofort
                // sieht wann Schluss ist statt erst nach einem 422-Roundtrip.
                maxLength: 200,
                decoration: const InputDecoration(
                  labelText: 'Party name',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _descriptionController,
                maxLines: 3,
                maxLength: 5000,
                decoration: const InputDecoration(
                  labelText: 'Description (optional)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _locationController,
                maxLength: 300,
                onChanged: _onLocationChanged,
                decoration: InputDecoration(
                  labelText: 'Where is the party?',
                  border: const OutlineInputBorder(),
                  suffixIcon: _requestingCurrentLocation
                      ? const Padding(
                          padding: EdgeInsets.all(12),
                          child: SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                        )
                      : IconButton(
                          icon: const Icon(Icons.my_location),
                          tooltip: 'Use current location',
                          onPressed: _useCurrentLocation,
                        ),
                ),
              ),
              _LocationSuggestions(onSelect: _selectSuggestion),
              if (_resolvedPlace != null)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    _resolvedPlace!.address.formattedAddress,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: _pickStartsAt,
                icon: const Icon(Icons.event),
                label: Text(
                  _startsAt == null ? 'Set date & time (optional)' : _startsAt.toString(),
                ),
              ),
              if (_clientError != null) ...[
                const SizedBox(height: 12),
                Text(
                  _clientError!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ] else if (createState.hasError) ...[
                const SizedBox(height: 12),
                Text(
                  'Failed to create party. Please try again.',
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 20),
              ElevatedButton(
                onPressed: isLoading ? null : _submit,
                child: isLoading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Create'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _pickStartsAt() async {
    final date = await showDatePicker(
      context: context,
      initialDate: DateTime.now(),
      firstDate: DateTime.now().subtract(const Duration(days: 1)),
      lastDate: DateTime.now().add(const Duration(days: 3650)),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(context: context, initialTime: TimeOfDay.now());
    if (time == null) return;
    setState(() {
      _startsAt = DateTime(date.year, date.month, date.day, time.hour, time.minute);
    });
  }

  Future<void> _submit() async {
    final name = _nameController.text.trim();
    setState(() {
      _clientError = name.isEmpty ? 'Please enter a party name.' : null;
    });
    if (_clientError != null) return;
    try {
      final party = await ref.read(createPartyProvider.notifier).create(
            name: name,
            description: _descriptionController.text.trim(),
            startsAt: _startsAt,
            location: _locationController.text.trim(),
          );
      ref.read(creatingPartyProvider.notifier).state = false;
      if (_resolvedPlace != null) {
        // Ein zweiter Schritt (Kartenvorschau/Sichtbarkeit/Ankunftshinweise)
        // folgt noch - erst danach landet der Host in `PartyDetailScreen`
        // (siehe `ConfirmPartyLocationScreen`).
        ref.read(confirmingPartyLocationProvider.notifier).state = (partyId: party.id, place: _resolvedPlace);
      } else {
        // Reine Freitext-Eingabe (oder gar keine) - exakt das alte Verhalten.
        ref.read(selectedPartyIdProvider.notifier).state = party.id;
      }
    } catch (_) {
      // error already reflected via createPartyProvider's AsyncError state
    }
  }
}

/// Dropdown mit Autocomplete-Vorschlägen unterhalb des Location-Suchfelds
/// (Spec §10: primärer/sekundärer Text). Verschwindet automatisch, sobald
/// die Liste leer ist (kein Suchtext, zu kurz, oder Provider down).
class _LocationSuggestions extends ConsumerWidget {
  final void Function(GeoSuggestion) onSelect;
  const _LocationSuggestions({required this.onSelect});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final suggestionsAsync = ref.watch(locationSearchProvider);
    final suggestions = suggestionsAsync.maybeWhen(data: (s) => s, orElse: () => const <GeoSuggestion>[]);
    if (suggestions.isEmpty) return const SizedBox.shrink();

    return Card(
      margin: const EdgeInsets.only(top: 4),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: suggestions
            .map((s) => ListTile(
                  dense: true,
                  title: Text(s.primaryText),
                  subtitle: s.secondaryText.isNotEmpty ? Text(s.secondaryText) : null,
                  onTap: () => onSelect(s),
                ))
            .toList(),
      ),
    );
  }
}
