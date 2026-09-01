import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../api/api_client.dart';
import '../models/event_type.dart';
import '../models/party_context.dart';
import '../models/party_context_override.dart';
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
  }
}

final partyContextProvider = AsyncNotifierProvider<PartyContextNotifier, PartyContext>(
  PartyContextNotifier.new,
);

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
  }

  Future<void> remove(String key) async {
    final token = ref.read(_requiredAdminTokenProvider);
    await ref.read(apiClientProvider).deletePartyContextOverride(token, key);
    state = AsyncData(await ref.read(apiClientProvider).getPartyContextOverrides(token));
  }
}

final partyContextOverridesProvider =
    AsyncNotifierProvider<PartyContextOverridesNotifier, List<PartyContextOverride>>(
  PartyContextOverridesNotifier.new,
);
