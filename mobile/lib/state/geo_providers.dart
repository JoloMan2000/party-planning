import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../geo/geo_models.dart';
import '../models/discovery_preferences.dart';
import 'auth_providers.dart';
import 'providers.dart';

/// Ortssuche fürs Create-Party-Formular und die Discovery-Preferences
/// (Suggest→Retrieve, Spec §7-13). Nutzt einen Generation-Counter statt
/// `http`-Request-Cancellation (die `http`-Package-Calls sind nicht nativ
/// abbrechbar) - eine spät eintreffende, veraltete Antwort wird anhand ihrer
/// Generation verworfen statt den `state` zu überschreiben.
class LocationSearchNotifier extends Notifier<AsyncValue<List<GeoSuggestion>>> {
  int _generation = 0;

  @override
  AsyncValue<List<GeoSuggestion>> build() => const AsyncData([]);

  Future<void> suggest(String query, {double? biasLat, double? biasLon}) async {
    if (query.trim().length < 2) {
      state = const AsyncData([]);
      return;
    }
    final myGeneration = ++_generation;
    state = const AsyncLoading();
    final token = ref.read(requiredAccessTokenProvider);
    try {
      final results = await ref.read(apiClientProvider).suggestPlaces(
            token,
            onRefresh(ref),
            query: query,
            biasLat: biasLat,
            biasLon: biasLon,
          );
      if (myGeneration != _generation) return;
      state = AsyncData(results);
    } catch (error, stackTrace) {
      if (myGeneration != _generation) return;
      state = AsyncError(error, stackTrace);
    }
  }

  void clear() {
    _generation++;
    state = const AsyncData([]);
  }

  Future<GeoPlace?> retrieve(String providerPlaceId) {
    final token = ref.read(requiredAccessTokenProvider);
    return ref.read(apiClientProvider).retrievePlace(token, onRefresh(ref), providerPlaceId: providerPlaceId);
  }

  Future<GeoPlace?> reverseGeocode(double latitude, double longitude) {
    final token = ref.read(requiredAccessTokenProvider);
    return ref.read(apiClientProvider).reverseGeocode(token, onRefresh(ref), latitude: latitude, longitude: longitude);
  }
}

final locationSearchProvider =
    NotifierProvider<LocationSearchNotifier, AsyncValue<List<GeoSuggestion>>>(LocationSearchNotifier.new);

/// Aktuelle Discover-Radius-/Ort-Einstellungen + Speichern-Aktion (mirroring
/// `PartySettingsNotifier`'s FutureBuilder+Save-Pattern).
class DiscoveryPreferencesNotifier extends AsyncNotifier<DiscoveryPreferences> {
  @override
  Future<DiscoveryPreferences> build() async {
    final token = ref.watch(requiredAccessTokenProvider);
    return ref.watch(apiClientProvider).getDiscoveryPreferences(token, onRefresh(ref));
  }

  Future<void> save(DiscoveryPreferences preferences) async {
    final token = ref.read(requiredAccessTokenProvider);
    final client = ref.read(apiClientProvider);
    final saved = await client.updateDiscoveryPreferences(token, onRefresh(ref), preferences);
    state = AsyncData(saved);
  }

  /// Build-Schritt 8: "Reset personalization" - löscht gelernte Affinitäten
  /// serverseitig, lädt die (unveränderten) expliziten Preferences danach
  /// neu, damit die UI konsistent bleibt.
  Future<void> resetLearning() async {
    final token = ref.read(requiredAccessTokenProvider);
    final client = ref.read(apiClientProvider);
    await client.resetLearning(token, onRefresh(ref));
    state = AsyncData(await client.getDiscoveryPreferences(token, onRefresh(ref)));
  }
}

final discoveryPreferencesProvider =
    AsyncNotifierProvider<DiscoveryPreferencesNotifier, DiscoveryPreferences>(DiscoveryPreferencesNotifier.new);

/// Strukturierte Location einer Party (`null` = noch keine gesetzt) + Setzen-
/// Aktion, party-gescoped wie `PartySettingsNotifier`.
class PartyLocationNotifier extends FamilyAsyncNotifier<PartyLocationView?, String> {
  @override
  Future<PartyLocationView?> build(String arg) async {
    final token = ref.watch(requiredAccessTokenProvider);
    return ref.watch(apiClientProvider).getPartyLocation(token, onRefresh(ref), arg);
  }

  Future<void> save({
    String? placeName,
    GeoAddress? address,
    GeoPoint? point,
    String precision = 'approximate',
    String? provider,
    String? providerPlaceId,
    String publicLocationLabel = '',
    String visibilityPolicy = 'exact_after_accept',
    String? arrivalInstructions,
    bool manuallyAdjusted = false,
    String source = 'organizer_entry',
  }) async {
    final token = ref.read(requiredAccessTokenProvider);
    final client = ref.read(apiClientProvider);
    await client.setPartyLocation(
      token,
      onRefresh(ref),
      arg,
      placeName: placeName,
      address: address,
      point: point,
      precision: precision,
      provider: provider,
      providerPlaceId: providerPlaceId,
      publicLocationLabel: publicLocationLabel,
      visibilityPolicy: visibilityPolicy,
      arrivalInstructions: arrivalInstructions,
      manuallyAdjusted: manuallyAdjusted,
      source: source,
    );
    state = AsyncData(await client.getPartyLocation(token, onRefresh(ref), arg));
  }
}

final partyLocationProvider =
    AsyncNotifierProvider.family<PartyLocationNotifier, PartyLocationView?, String>(PartyLocationNotifier.new);

/// Ad-hoc-Navigations-`StateProvider` (mirroring `selectedPartyIdProvider`
/// etc. in `state/auth_providers.dart`) - hält fest, für welche frisch
/// erstellte Party gerade der Location-Bestätigungs-Schritt aussteht, plus
/// den bereits aufgelösten `GeoPlace` (falls der Host beim Erstellen eine
/// Autocomplete-Suggestion ausgewählt oder "Use current location" genutzt
/// hat). `null` = kein ausstehender Bestätigungsschritt.
final confirmingPartyLocationProvider =
    StateProvider<({String partyId, GeoPlace? place})?>((ref) => null);

/// Zeigt `DiscoveryPreferencesScreen` (Einstiegspunkt: Icon im Discover-Tab).
final showDiscoveryPreferencesProvider = StateProvider<bool>((ref) => false);
