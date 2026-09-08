import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/spotify_status.dart';
import 'auth_providers.dart';
import 'providers.dart';

/// Verbindungsstatus zum Spotify-Account (mirroring `DiscoveryPreferencesNotifier`'s
/// Fetch+Aktion-in-einem Pattern). `SpotifyConnectScreen` invalidiert diesen
/// Provider beim App-Resume (siehe dortiger `WidgetsBindingObserver`), da der
/// Backend-OAuth-Callback keinen Weg hat, die App direkt zu benachrichtigen
/// (`spotify_redirect_uri` ist eine feste HTTP-URL, kein `partyplanning://`
/// Deep Link) - der User kehrt manuell aus dem externen Browser zurück.
class SpotifyStatusNotifier extends AsyncNotifier<SpotifyStatus> {
  @override
  Future<SpotifyStatus> build() async {
    final token = ref.watch(requiredAccessTokenProvider);
    return ref.watch(apiClientProvider).getSpotifyStatus(token, onRefresh(ref));
  }

  Future<void> disconnect() async {
    final token = ref.read(requiredAccessTokenProvider);
    final client = ref.read(apiClientProvider);
    await client.disconnectSpotify(token, onRefresh(ref));
    state = AsyncData(await client.getSpotifyStatus(token, onRefresh(ref)));
  }
}

final spotifyStatusProvider = AsyncNotifierProvider<SpotifyStatusNotifier, SpotifyStatus>(SpotifyStatusNotifier.new);

/// Liefert die `authorize_url` als einmalige Aktion - der Screen selbst öffnet
/// sie via `url_launcher` im externen Browser.
class SpotifyConnectNotifier extends AsyncNotifier<String?> {
  @override
  Future<String?> build() async => null;

  Future<String> getAuthorizeUrl() async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      final url = await ref.read(apiClientProvider).getSpotifyConnectUrl(token, onRefresh(ref));
      state = AsyncData(url);
      return url;
    } catch (e, st) {
      state = AsyncError(e, st);
      rethrow;
    }
  }
}

final spotifyConnectProvider = AsyncNotifierProvider<SpotifyConnectNotifier, String?>(SpotifyConnectNotifier.new);

/// Zeigt `SpotifyConnectScreen` (Einstiegspunkt: Tile in `ProfileScreen`).
final showSpotifyConnectProvider = StateProvider<bool>((ref) => false);
