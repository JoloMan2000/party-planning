import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../api/api_client.dart';
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
import 'providers.dart';

const _tokenStorageKey = 'admin_jwt';

/// Umschalter zwischen Gast-Flow und Admin-Flow (separater Einstiegspunkt,
/// von der Sprachauswahl-Seite aus erreichbar - mirroring, dass der
/// Admin-Zugang in `"Party Planning.py"` über einen eigenen Query-Param
/// (`?admin=...`) läuft statt über den Gast-Wizard).
final adminModeProvider = StateProvider<bool>((ref) => false);

final _secureStorageProvider = Provider<FlutterSecureStorage>((ref) {
  return const FlutterSecureStorage();
});

/// Aktuelles Admin-JWT (`null` = nicht eingeloggt). Wird beim App-Start aus
/// dem sicheren Speicher geladen (mirroring, dass die Streamlit-App den
/// `?admin=...`-Query-Param bei jedem Reload erneut prüft - hier bleibt die
/// Session stattdessen über Neustarts hinweg erhalten, bis das Token abläuft
/// oder der Admin sich explizit ausloggt).
class AdminAuthNotifier extends AsyncNotifier<String?> {
  @override
  Future<String?> build() async {
    return ref.read(_secureStorageProvider).read(key: _tokenStorageKey);
  }

  Future<void> login(String password) async {
    state = const AsyncLoading();
    final storage = ref.read(_secureStorageProvider);
    final client = ref.read(apiClientProvider);
    try {
      final response = await client.adminLogin(password);
      await storage.write(key: _tokenStorageKey, value: response.accessToken);
      state = AsyncData(response.accessToken);
    } on ApiException catch (e) {
      state = AsyncError(e, StackTrace.current);
    }
  }

  Future<void> logout() async {
    await ref.read(_secureStorageProvider).delete(key: _tokenStorageKey);
    state = const AsyncData(null);
  }
}

final adminAuthProvider = AsyncNotifierProvider<AdminAuthNotifier, String?>(
  AdminAuthNotifier.new,
);

/// Aktuelles Admin-JWT als Nicht-Nullable-Wert - nur innerhalb des
/// Admin-Dashboards verwendet, wo ein gültiger Token durch [main.dart]'s
/// Routing bereits garantiert ist (kein Rendern der Dashboard-Widgets ohne
/// Token).
final _requiredAdminTokenProvider = Provider<String>((ref) {
  final token = ref.watch(adminAuthProvider).value;
  if (token == null) {
    throw StateError('Admin-Dashboard ohne gültiges Token gerendert.');
  }
  return token;
});

/// Alle wählbaren Event-Typen fürs Party-Settings-Dropdown.
final eventTypesProvider = FutureProvider<List<EventType>>((ref) {
  final token = ref.watch(_requiredAdminTokenProvider);
  return ref.watch(apiClientProvider).getEventTypes(token);
});

/// Aktuelle Party-Settings + Speichern-Aktion (mirroring
/// `render_party_settings_section`'s Formular + Save-Button-Handler).
class PartySettingsNotifier extends AsyncNotifier<PartySettings> {
  @override
  Future<PartySettings> build() async {
    final token = ref.watch(_requiredAdminTokenProvider);
    return ref.watch(apiClientProvider).getPartySettings(token);
  }

  /// Speichert [settings], lädt danach die Settings neu (Server ist die
  /// Quelle der Wahrheit) und gibt zurück, ob der Party-Lifecycle-Reset
  /// ausgelöst wurde (`party_settings_reset_notice`).
  Future<bool> save(PartySettings settings) async {
    final token = ref.read(_requiredAdminTokenProvider);
    final resetHappened = await ref.read(apiClientProvider).savePartySettings(token, settings);
    state = AsyncData(await ref.read(apiClientProvider).getPartySettings(token));
    return resetHappened;
  }
}

final partySettingsProvider = AsyncNotifierProvider<PartySettingsNotifier, PartySettings>(
  PartySettingsNotifier.new,
);

/// Stammdaten fürs Party-Kontext-Formular (Location-Typen, Länderliste).
final partyContextMetadataProvider = FutureProvider<PartyContextMetadata>((ref) {
  final token = ref.watch(_requiredAdminTokenProvider);
  return ref.watch(apiClientProvider).getPartyContextMetadata(token);
});

/// Aktueller Party-Kontext + Speichern-Aktion (mirroring
/// `render_party_context_section`'s Formular + Save-Button-Handler).
class PartyContextNotifier extends AsyncNotifier<PartyContext> {
  @override
  Future<PartyContext> build() async {
    final token = ref.watch(_requiredAdminTokenProvider);
    return ref.watch(apiClientProvider).getPartyContext(token);
  }

  Future<void> save(PartyContext context) async {
    final token = ref.read(_requiredAdminTokenProvider);
    await ref.read(apiClientProvider).savePartyContext(token, context);
    state = AsyncData(await ref.read(apiClientProvider).getPartyContext(token));
    ref.invalidate(derivedPartyContextProvider);
  }
}

final partyContextProvider = AsyncNotifierProvider<PartyContextNotifier, PartyContext>(
  PartyContextNotifier.new,
);

/// Rein informative abgeleitete Party-Wahrheit fürs Context-Dashboard
/// (mirroring `render_party_context_dashboard`) - wird nach jeder Context-/
/// Override-Änderung neu geladen (siehe `invalidate`-Aufrufe unten).
final derivedPartyContextProvider = FutureProvider<DerivedPartyContext>((ref) {
  final token = ref.watch(_requiredAdminTokenProvider);
  return ref.watch(apiClientProvider).getDerivedPartyContext(token);
});

/// Bestehende Context-Overrides + Hinzufügen-/Entfernen-Aktionen (mirroring
/// `render_party_context_overrides_section`).
class PartyContextOverridesNotifier extends AsyncNotifier<List<PartyContextOverride>> {
  @override
  Future<List<PartyContextOverride>> build() async {
    final token = ref.watch(_requiredAdminTokenProvider);
    return ref.watch(apiClientProvider).getPartyContextOverrides(token);
  }

  Future<void> add(String key, String value, String? reason) async {
    final token = ref.read(_requiredAdminTokenProvider);
    await ref.read(apiClientProvider).addPartyContextOverride(token, key, value, reason);
    state = AsyncData(await ref.read(apiClientProvider).getPartyContextOverrides(token));
    ref.invalidate(derivedPartyContextProvider);
  }

  Future<void> remove(String key) async {
    final token = ref.read(_requiredAdminTokenProvider);
    await ref.read(apiClientProvider).deletePartyContextOverride(token, key);
    state = AsyncData(await ref.read(apiClientProvider).getPartyContextOverrides(token));
    ref.invalidate(derivedPartyContextProvider);
  }
}

final partyContextOverridesProvider =
    AsyncNotifierProvider<PartyContextOverridesNotifier, List<PartyContextOverride>>(
  PartyContextOverridesNotifier.new,
);

/// Der vollständige, ungefilterte Getränke-/Speisenkatalog fürs Kurations-
/// Formular (mirroring `_drink_items(catalog, apply_curation=False)`/
/// `_food_items(..., apply_curation=False)`).
final curatableCatalogProvider = FutureProvider<CuratableCatalog>((ref) {
  final token = ref.watch(_requiredAdminTokenProvider);
  return ref.watch(apiClientProvider).getCuratableCatalog(token);
});

/// Aktuelle Catalog-Curation-Settings + Speichern-Aktion (mirroring
/// `render_catalog_curation_section`'s Formular + Save-Button-Handler).
class CatalogCurationNotifier extends AsyncNotifier<CatalogCurationSettings> {
  @override
  Future<CatalogCurationSettings> build() async {
    final token = ref.watch(_requiredAdminTokenProvider);
    return ref.watch(apiClientProvider).getCatalogCurationSettings(token);
  }

  Future<void> save(bool enabled, List<String> curatedItemIds) async {
    final token = ref.read(_requiredAdminTokenProvider);
    await ref.read(apiClientProvider).saveCatalogCurationSettings(token, enabled, curatedItemIds);
    state = AsyncData(await ref.read(apiClientProvider).getCatalogCurationSettings(token));
  }
}

final catalogCurationProvider = AsyncNotifierProvider<CatalogCurationNotifier, CatalogCurationSettings>(
  CatalogCurationNotifier.new,
);

/// Admin-Sortiment-Empfehlungen (mirroring `render_recommendations_section`)
/// - rein informativ, erzeugt keine Demand/Preference.
final adminRecommendationsProvider = FutureProvider<AdminRecommendationsResponse>((ref) {
  final token = ref.watch(_requiredAdminTokenProvider);
  return ref.watch(apiClientProvider).getAdminRecommendations(token);
});

/// Musik-Admin-Steuerparameter + Speichern-Aktion (mirroring
/// `render_music_playlist_section`'s Slider-/Checkbox-Formular).
class MusicSettingsNotifier extends AsyncNotifier<MusicAdminSettings> {
  @override
  Future<MusicAdminSettings> build() async {
    final token = ref.watch(_requiredAdminTokenProvider);
    return ref.watch(apiClientProvider).getMusicSettings(token);
  }

  Future<void> save(MusicAdminSettings settings) async {
    final token = ref.read(_requiredAdminTokenProvider);
    await ref.read(apiClientProvider).saveMusicSettings(token, settings);
    state = AsyncData(await ref.read(apiClientProvider).getMusicSettings(token));
  }
}

final musicSettingsProvider = AsyncNotifierProvider<MusicSettingsNotifier, MusicAdminSettings>(
  MusicSettingsNotifier.new,
);

/// Zuletzt generierte Playlist (`null` = noch nicht generiert, mirroring
/// `st.session_state["music_planning_result"]`).
class MusicPlaylistNotifier extends AsyncNotifier<MusicPlanningResult?> {
  @override
  Future<MusicPlanningResult?> build() async => null;

  Future<void> generate() async {
    final token = ref.read(_requiredAdminTokenProvider);
    state = const AsyncLoading();
    state = AsyncData(await ref.read(apiClientProvider).generateMusicPlaylist(token));
  }
}

final musicPlaylistProvider = AsyncNotifierProvider<MusicPlaylistNotifier, MusicPlanningResult?>(
  MusicPlaylistNotifier.new,
);

/// Gespeicherte Gäste-Antworten fürs Responses-Dashboard (mirroring
/// `load_responses()` + `raw_responses_expander`).
final adminResponsesProvider = FutureProvider<List<GuestResponse>>((ref) {
  final token = ref.watch(_requiredAdminTokenProvider);
  return ref.watch(apiClientProvider).getResponses(token);
});

/// Zuletzt berechnete Einkaufsliste (`null` = noch nicht berechnet, mirroring
/// des `btn_create_shopping_list`-Buttons in `render_admin_view`, der
/// `render_shopping_list` erst bei Klick aufruft statt bei jedem Rerun).
class ShoppingListNotifier extends AsyncNotifier<PartyDemandResult?> {
  @override
  Future<PartyDemandResult?> build() async => null;

  Future<void> compute() async {
    final token = ref.read(_requiredAdminTokenProvider);
    state = const AsyncLoading();
    state = AsyncData(await ref.read(apiClientProvider).computeShoppingList(token));
  }
}

final shoppingListProvider = AsyncNotifierProvider<ShoppingListNotifier, PartyDemandResult?>(
  ShoppingListNotifier.new,
);
