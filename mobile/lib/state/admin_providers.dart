import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../api/api_client.dart';
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
