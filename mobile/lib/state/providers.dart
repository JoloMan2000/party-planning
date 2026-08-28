import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../models/catalog_item.dart';
import '../models/language_option.dart';
import '../models/party_info.dart';

/// Einziger [ApiClient] für die ganze App (mirroring, dass der Streamlit-
/// Code einen einzigen `requests`-ähnlichen Zugriffspfad je Modul hat).
final apiClientProvider = Provider<ApiClient>((ref) {
  final client = ApiClient();
  ref.onDispose(client.close);
  return client;
});

/// Aktuell gewählte Sprache. `null` = noch nicht ausgewählt (mirroring
/// `st.session_state.language is None` -> Sprach-Landing-Page).
final languageProvider = StateProvider<String?>((ref) => null);

/// Hat der Nutzer den Intro-Screen bereits verlassen? (mirroring
/// `st.session_state.entered_intro`).
final enteredIntroProvider = StateProvider<bool>((ref) => false);

/// Party-Titel/Theme/Kalender-Metadaten, sprachabhängig (für `hero_subtitle`).
final partyInfoProvider = FutureProvider.family<PartyInfo, String>((ref, lang) {
  return ref.watch(apiClientProvider).getPartyInfo(lang: lang);
});

/// Verfügbare Sprachen für die Sprachauswahl-Seite.
final languagesProvider = FutureProvider<LanguagesResponse>((ref) {
  return ref.watch(apiClientProvider).getLanguages();
});

/// Vollständige UI-Übersetzungstabelle für eine Sprache (ein Request, siehe
/// `ApiClient.getTranslations`).
final translationsProvider = FutureProvider.family<Map<String, String>, String>((ref, lang) {
  return ref.watch(apiClientProvider).getTranslations(lang);
});

/// Getränke-/Essens-Katalog, sprachabhängig (für `display_name`).
final drinksProvider = FutureProvider.family<List<CatalogItem>, String>((ref, lang) {
  return ref.watch(apiClientProvider).getDrinks(lang: lang);
});

final foodProvider = FutureProvider.family<List<CatalogItem>, String>((ref, lang) {
  return ref.watch(apiClientProvider).getFood(lang: lang);
});

/// Score-sortierte empfohlene Item-IDs für die aktuellen In-Wizard-
/// Selections (mirroring `_guest_recommended_ids`). [selectionKey] bündelt
/// Name+Drinks+Essen, damit der Provider nur bei tatsächlichen Änderungen neu
/// lädt statt bei jedem Tastendruck.
final recommendationsProvider =
    FutureProvider.family<List<String>, ({String name, List<String> drinks, List<String> food})>(
  (ref, selection) {
    return ref.watch(apiClientProvider).getRecommendations(
          name: selection.name,
          drinks: selection.drinks,
          food: selection.food,
        );
  },
);
