import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/admin_recommendation.dart';
import '../models/catalog_curation_settings.dart';
import '../models/event_type.dart';
import '../models/derived_party_context.dart';
import '../models/guest_response.dart';
import '../models/music_admin_settings.dart';
import '../models/music_planning_result.dart';
import '../models/party_context.dart';
import '../models/party_context_override.dart';
import '../models/party_demand_result.dart';
import '../models/party_settings.dart';
import 'auth_providers.dart';
import 'providers.dart';

/// Alle wählbaren Event-Typen fürs Party-Settings-Dropdown. Seit Phase 4
/// party-gescoped (`.family<_, String>` keyed by `partyId`) und geritten auf
/// dem Account-JWT statt eines separaten Admin-Tokens (kein eigener
/// Admin-Login mehr - HOST/CO_HOST-Rolle wird serverseitig via
/// `require_party_role` geprüft).
final eventTypesProvider = FutureProvider.family<List<EventType>, String>((ref, partyId) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getEventTypes(partyId, token, onRefresh(ref));
});

/// Aktuelle Party-Settings + Speichern-Aktion (mirroring
/// `render_party_settings_section`'s Formular + Save-Button-Handler).
class PartySettingsNotifier extends FamilyAsyncNotifier<PartySettings, String> {
  @override
  Future<PartySettings> build(String arg) async {
    final token = ref.watch(requiredAccessTokenProvider);
    return ref.watch(apiClientProvider).getPartySettings(arg, token, onRefresh(ref));
  }

  /// Speichert [settings], lädt danach die Settings neu (Server ist die
  /// Quelle der Wahrheit) und gibt zurück, ob der Party-Lifecycle-Reset
  /// ausgelöst wurde (`party_settings_reset_notice`).
  Future<bool> save(PartySettings settings) async {
    final token = ref.read(requiredAccessTokenProvider);
    final client = ref.read(apiClientProvider);
    final resetHappened = await client.savePartySettings(arg, token, onRefresh(ref), settings);
    state = AsyncData(await client.getPartySettings(arg, token, onRefresh(ref)));
    return resetHappened;
  }
}

final partySettingsProvider =
    AsyncNotifierProvider.family<PartySettingsNotifier, PartySettings, String>(PartySettingsNotifier.new);

/// Stammdaten fürs Party-Kontext-Formular (Location-Typen, Länderliste).
final partyContextMetadataProvider = FutureProvider.family<PartyContextMetadata, String>((ref, partyId) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getPartyContextMetadata(partyId, token, onRefresh(ref));
});

/// Aktueller Party-Kontext + Speichern-Aktion (mirroring
/// `render_party_context_section`'s Formular + Save-Button-Handler).
class PartyContextNotifier extends FamilyAsyncNotifier<PartyContext, String> {
  @override
  Future<PartyContext> build(String arg) async {
    final token = ref.watch(requiredAccessTokenProvider);
    return ref.watch(apiClientProvider).getPartyContext(arg, token, onRefresh(ref));
  }

  Future<void> save(PartyContext context) async {
    final token = ref.read(requiredAccessTokenProvider);
    final client = ref.read(apiClientProvider);
    await client.savePartyContext(arg, token, onRefresh(ref), context);
    state = AsyncData(await client.getPartyContext(arg, token, onRefresh(ref)));
    ref.invalidate(derivedPartyContextProvider(arg));
  }
}

final partyContextProvider =
    AsyncNotifierProvider.family<PartyContextNotifier, PartyContext, String>(PartyContextNotifier.new);

/// Rein informative abgeleitete Party-Wahrheit fürs Context-Dashboard
/// (mirroring `render_party_context_dashboard`) - wird nach jeder Context-/
/// Override-Änderung neu geladen (siehe `invalidate`-Aufrufe unten).
final derivedPartyContextProvider = FutureProvider.family<DerivedPartyContext, String>((ref, partyId) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getDerivedPartyContext(partyId, token, onRefresh(ref));
});

/// Bestehende Context-Overrides + Hinzufügen-/Entfernen-Aktionen (mirroring
/// `render_party_context_overrides_section`).
class PartyContextOverridesNotifier extends FamilyAsyncNotifier<List<PartyContextOverride>, String> {
  @override
  Future<List<PartyContextOverride>> build(String arg) async {
    final token = ref.watch(requiredAccessTokenProvider);
    return ref.watch(apiClientProvider).getPartyContextOverrides(arg, token, onRefresh(ref));
  }

  Future<void> add(String key, String value, String? reason) async {
    final token = ref.read(requiredAccessTokenProvider);
    final client = ref.read(apiClientProvider);
    await client.addPartyContextOverride(arg, token, onRefresh(ref), key, value, reason);
    state = AsyncData(await client.getPartyContextOverrides(arg, token, onRefresh(ref)));
    ref.invalidate(derivedPartyContextProvider(arg));
  }

  Future<void> remove(String key) async {
    final token = ref.read(requiredAccessTokenProvider);
    final client = ref.read(apiClientProvider);
    await client.deletePartyContextOverride(arg, token, onRefresh(ref), key);
    state = AsyncData(await client.getPartyContextOverrides(arg, token, onRefresh(ref)));
    ref.invalidate(derivedPartyContextProvider(arg));
  }
}

final partyContextOverridesProvider = AsyncNotifierProvider.family<PartyContextOverridesNotifier,
    List<PartyContextOverride>, String>(PartyContextOverridesNotifier.new);

/// Der vollständige, ungefilterte Getränke-/Speisenkatalog fürs Kurations-
/// Formular (mirroring `_drink_items(catalog, apply_curation=False)`/
/// `_food_items(..., apply_curation=False)`).
final curatableCatalogProvider = FutureProvider.family<CuratableCatalog, String>((ref, partyId) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getCuratableCatalog(partyId, token, onRefresh(ref));
});

/// Aktuelle Catalog-Curation-Settings + Speichern-Aktion (mirroring
/// `render_catalog_curation_section`'s Formular + Save-Button-Handler).
class CatalogCurationNotifier extends FamilyAsyncNotifier<CatalogCurationSettings, String> {
  @override
  Future<CatalogCurationSettings> build(String arg) async {
    final token = ref.watch(requiredAccessTokenProvider);
    return ref.watch(apiClientProvider).getCatalogCurationSettings(arg, token, onRefresh(ref));
  }

  Future<void> save(bool enabled, List<String> curatedItemIds) async {
    final token = ref.read(requiredAccessTokenProvider);
    final client = ref.read(apiClientProvider);
    await client.saveCatalogCurationSettings(arg, token, onRefresh(ref), enabled, curatedItemIds);
    state = AsyncData(await client.getCatalogCurationSettings(arg, token, onRefresh(ref)));
  }
}

final catalogCurationProvider = AsyncNotifierProvider.family<CatalogCurationNotifier,
    CatalogCurationSettings, String>(CatalogCurationNotifier.new);

/// Admin-Sortiment-Empfehlungen (mirroring `render_recommendations_section`)
/// - rein informativ, erzeugt keine Demand/Preference.
final adminRecommendationsProvider = FutureProvider.family<AdminRecommendationsResponse, String>((ref, partyId) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getAdminRecommendations(partyId, token, onRefresh(ref));
});

/// Musik-Admin-Steuerparameter + Speichern-Aktion (mirroring
/// `render_music_playlist_section`'s Slider-/Checkbox-Formular).
class MusicSettingsNotifier extends FamilyAsyncNotifier<MusicAdminSettings, String> {
  @override
  Future<MusicAdminSettings> build(String arg) async {
    final token = ref.watch(requiredAccessTokenProvider);
    return ref.watch(apiClientProvider).getMusicSettings(arg, token, onRefresh(ref));
  }

  Future<void> save(MusicAdminSettings settings) async {
    final token = ref.read(requiredAccessTokenProvider);
    final client = ref.read(apiClientProvider);
    await client.saveMusicSettings(arg, token, onRefresh(ref), settings);
    state = AsyncData(await client.getMusicSettings(arg, token, onRefresh(ref)));
  }
}

final musicSettingsProvider =
    AsyncNotifierProvider.family<MusicSettingsNotifier, MusicAdminSettings, String>(MusicSettingsNotifier.new);

/// Zuletzt generierte Playlist (`null` = noch nicht generiert, mirroring
/// `st.session_state["music_planning_result"]`).
class MusicPlaylistNotifier extends FamilyAsyncNotifier<MusicPlanningResult?, String> {
  @override
  Future<MusicPlanningResult?> build(String arg) async => null;

  Future<void> generate() async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    state = AsyncData(await ref.read(apiClientProvider).generateMusicPlaylist(arg, token, onRefresh(ref)));
  }
}

final musicPlaylistProvider = AsyncNotifierProvider.family<MusicPlaylistNotifier, MusicPlanningResult?, String>(
    MusicPlaylistNotifier.new);

/// Gespeicherte Gäste-Antworten fürs Responses-Dashboard (mirroring
/// `load_responses()` + `raw_responses_expander`).
final adminResponsesProvider = FutureProvider.family<List<GuestResponse>, String>((ref, partyId) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getResponses(partyId, token, onRefresh(ref));
});

/// Rohe CSV-Bytes für den Antworten-Export (mirroring `btn_csv`) - eigene
/// Aktion statt Teil von [adminResponsesProvider], da sie Bytes statt
/// geparster Modelle liefert (Download/Teilen via `share_plus`).
Future<List<int>> downloadResponsesCsv(WidgetRef ref, String partyId) {
  final token = ref.read(requiredAccessTokenProvider);
  return ref.read(apiClientProvider).getResponsesCsv(
        partyId,
        token,
        () => ref.read(authProvider.notifier).refreshAndPersist(),
      );
}

/// Zuletzt berechnete Einkaufsliste (`null` = noch nicht berechnet, mirroring
/// des `btn_create_shopping_list`-Buttons in `render_admin_view`, der
/// `render_shopping_list` erst bei Klick aufruft statt bei jedem Rerun).
class ShoppingListNotifier extends FamilyAsyncNotifier<PartyDemandResult?, String> {
  @override
  Future<PartyDemandResult?> build(String arg) async => null;

  Future<void> compute() async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    state = AsyncData(await ref.read(apiClientProvider).computeShoppingList(arg, token, onRefresh(ref)));
  }
}

final shoppingListProvider =
    AsyncNotifierProvider.family<ShoppingListNotifier, PartyDemandResult?, String>(ShoppingListNotifier.new);
