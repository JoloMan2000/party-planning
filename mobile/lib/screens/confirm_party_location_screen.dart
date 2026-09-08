import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:latlong2/latlong.dart';

import '../geo/debounce.dart';
import '../geo/geo_models.dart';
import '../state/auth_providers.dart';
import '../state/geo_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

const _fallbackCenter = LatLng(53.5511, 9.9937); // Hamburg - nur Default, falls kein Punkt aufgelöst wurde.

const _visibilityPolicies = <String, String>{
  'exact_after_accept': 'Exact address after RSVP accepted',
  'exact_after_accept_or_maybe': 'Exact address after accepted or maybe',
  'exact_immediately': 'Exact address immediately',
  'approximate_only': 'Approximate label only, never exact',
};

/// Zweiter Schritt nach der Party-Erstellung (Spec §20-25): Kartenvorschau
/// mit zentrierter Pin, optionale manuelle Anpassung ("Adjust Pin" pannt die
/// Karte + löst debounced `reverseGeocode` aus - vermeidet eine
/// Marker-Drag-Plugin-Abhängigkeit), Sichtbarkeitsrichtlinie,
/// Ankunftshinweise. Ein Fehlschlag hier blockiert nie die bereits
/// erfolgreiche Party-Erstellung - "Skip" verlässt den Screen ohne
/// strukturierte Location zu speichern.
class ConfirmPartyLocationScreen extends ConsumerStatefulWidget {
  final String partyId;
  final GeoPlace? initialPlace;

  const ConfirmPartyLocationScreen({super.key, required this.partyId, required this.initialPlace});

  @override
  ConsumerState<ConfirmPartyLocationScreen> createState() => _ConfirmPartyLocationScreenState();
}

class _ConfirmPartyLocationScreenState extends ConsumerState<ConfirmPartyLocationScreen> {
  final _mapController = MapController();
  final _arrivalController = TextEditingController();
  final _pinDebouncer = Debouncer();

  GeoPlace? _currentPlace;
  bool _manuallyAdjusted = false;
  bool _adjustPinEnabled = false;
  bool _resolvingPin = false;
  String _visibilityPolicy = 'exact_after_accept';
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _currentPlace = widget.initialPlace;
  }

  @override
  void dispose() {
    _arrivalController.dispose();
    _pinDebouncer.dispose();
    super.dispose();
  }

  LatLng get _center {
    final point = _currentPlace?.point;
    return point == null ? _fallbackCenter : LatLng(point.latitude, point.longitude);
  }

  void _onMapPositionChanged(MapCamera camera, bool hasGesture) {
    if (!_adjustPinEnabled || !hasGesture) return;
    final center = camera.center;
    _pinDebouncer.run(() => _resolvePin(center.latitude, center.longitude));
  }

  Future<void> _resolvePin(double latitude, double longitude) async {
    setState(() => _resolvingPin = true);
    try {
      final place = await ref.read(locationSearchProvider.notifier).reverseGeocode(latitude, longitude);
      if (!mounted) return;
      if (place != null) {
        setState(() {
          _currentPlace = place;
          _manuallyAdjusted = true;
        });
      }
    } finally {
      if (mounted) setState(() => _resolvingPin = false);
    }
  }

  Future<void> _confirm() async {
    setState(() => _saving = true);
    try {
      final place = _currentPlace;
      await ref.read(partyLocationProvider(widget.partyId).notifier).save(
            placeName: place?.name,
            address: place?.address,
            point: place?.point,
            precision: place?.precision ?? 'approximate',
            provider: place?.provider,
            providerPlaceId: place?.providerPlaceId,
            publicLocationLabel: place?.name ?? '',
            visibilityPolicy: _visibilityPolicy,
            arrivalInstructions: _arrivalController.text.trim().isEmpty ? null : _arrivalController.text.trim(),
            manuallyAdjusted: _manuallyAdjusted,
            source: _manuallyAdjusted ? 'manual_pin' : 'search_provider',
          );
      _finish();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Failed to save location. You can add it later from the party.')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _finish() {
    ref.read(confirmingPartyLocationProvider.notifier).state = null;
    ref.read(selectedPartyIdProvider.notifier).state = widget.partyId;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Confirm Location'),
        actions: [
          TextButton(onPressed: _saving ? null : _finish, child: const Text('Skip')),
        ],
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                _currentPlace?.address.formattedAddress ?? 'No address resolved yet.',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: 12),
              ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: SizedBox(
                  height: 260,
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      FlutterMap(
                        mapController: _mapController,
                        options: MapOptions(
                          initialCenter: _center,
                          initialZoom: 15,
                          onPositionChanged: _onMapPositionChanged,
                        ),
                        children: [
                          TileLayer(
                            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                            userAgentPackageName: 'com.partyplanning.mobile',
                          ),
                        ],
                      ),
                      const IgnorePointer(
                        child: Icon(Icons.location_pin, size: 40, color: Colors.red),
                      ),
                      if (_resolvingPin)
                        const Positioned(
                          top: 8,
                          right: 8,
                          child: SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Adjust Pin'),
                subtitle: const Text('Pan the map to fine-tune the exact spot.'),
                value: _adjustPinEnabled,
                onChanged: (value) => setState(() => _adjustPinEnabled = value),
              ),
              const SizedBox(height: 8),
              Text('Who can see the exact address?', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 8),
              DropdownButton<String>(
                isExpanded: true,
                value: _visibilityPolicy,
                items: _visibilityPolicies.entries
                    .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
                    .toList(),
                onChanged: (value) => setState(() => _visibilityPolicy = value ?? _visibilityPolicy),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _arrivalController,
                maxLines: 2,
                maxLength: 500,
                decoration: const InputDecoration(
                  labelText: 'Arrival instructions (optional)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: _saving ? null : _confirm,
                child: _saving
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Confirm Location'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
