import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/search_results.dart';
import 'auth_providers.dart';
import 'providers.dart';

/// Social Graph Phase 6 (Unified Entity Search) - eine Suche über People +
/// Organizers + Events (`GET /api/v1/search`, siehe
/// `backend/app/routers/social.py::unified_search`).

const _emptyResults = SearchResults(users: [], organizers: [], events: []);

/// Suche-während-Tippen (verbatim-Klon von `UserSearchNotifier` in
/// `social_providers.dart`): Generation-Counter statt Request-Cancellation,
/// damit eine spät eintreffende veraltete Antwort keine frischere
/// überschreibt.
class UnifiedSearchNotifier extends Notifier<AsyncValue<SearchResults>> {
  int _generation = 0;

  @override
  AsyncValue<SearchResults> build() => const AsyncData(_emptyResults);

  Future<void> search(String query) async {
    if (query.trim().length < 2) {
      state = const AsyncData(_emptyResults);
      return;
    }
    final myGeneration = ++_generation;
    state = const AsyncLoading();
    final token = ref.read(requiredAccessTokenProvider);
    try {
      final results = await ref.read(apiClientProvider).unifiedSearch(token, onRefresh(ref), q: query);
      if (myGeneration != _generation) return;
      state = AsyncData(results);
    } catch (error, stackTrace) {
      if (myGeneration != _generation) return;
      state = AsyncError(error, stackTrace);
    }
  }

  void clear() {
    _generation++;
    state = const AsyncData(_emptyResults);
  }
}

final unifiedSearchProvider =
    NotifierProvider<UnifiedSearchNotifier, AsyncValue<SearchResults>>(UnifiedSearchNotifier.new);

/// Navigations-Flag (mirrort `showFriendsProvider`) - `SearchScreen` wird
/// über das Lupen-Icon in der `HomeShell`-AppBar geöffnet.
final showSearchProvider = StateProvider<bool>((ref) => false);
