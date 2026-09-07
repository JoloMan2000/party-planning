import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../models/party_info.dart';

/// Einziger [ApiClient] für die ganze App (mirroring, dass der Streamlit-
/// Code einen einzigen `requests`-ähnlichen Zugriffspfad je Modul hat).
final apiClientProvider = Provider<ApiClient>((ref) {
  final client = ApiClient();
  ref.onDispose(client.close);
  return client;
});

/// Party-Titel/Theme/Kalender-Metadaten für das Admin-Dashboard (mirroring
/// `hero_subtitle`) - seit Phase 4 party-gescoped (`.family<_, String>` keyed
/// by `partyId` statt Sprache, da der frühere anonyme Gast-Wizard, der diesen
/// Provider sprachabhängig nutzte, entfernt wurde).
final partyInfoProvider = FutureProvider.family<PartyInfo, String>((ref, partyId) {
  return ref.watch(apiClientProvider).getPartyInfo(partyId);
});

/// Vollständige UI-Übersetzungstabelle für eine Sprache (ein Request, siehe
/// `ApiClient.getTranslations`).
final translationsProvider = FutureProvider.family<Map<String, String>, String>((ref, lang) {
  return ref.watch(apiClientProvider).getTranslations(lang);
});
