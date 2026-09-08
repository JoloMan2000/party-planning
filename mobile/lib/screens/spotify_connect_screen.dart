import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../state/spotify_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Spotify-OAuth/PKCE-Connect-Screen (Phase 7 des Account-basierten Pivots -
/// bisher nur backend-seitig vorhanden, nie über Mobile erreichbar).
/// Erreichbar über die "Music Provider"-Kachel auf `ProfileScreen`.
///
/// Das Backend leitet Spotifys OAuth-Callback auf eine feste HTTP-URL um
/// (`spotify_redirect_uri`, KEIN `partyplanning://` Deep Link) und zeigt dort
/// nur eine simple HTML-Bestätigungsseite - die App kann also nicht
/// automatisch benachrichtigt werden, wenn der Browser-Flow abschließt.
/// Stattdessen: `WidgetsBindingObserver` löst beim App-Resume (User kehrt
/// manuell aus dem Browser zurück) ein Neuladen von [spotifyStatusProvider]
/// aus, plus ein manueller Refresh-Button als Fallback.
class SpotifyConnectScreen extends ConsumerStatefulWidget {
  const SpotifyConnectScreen({super.key});

  @override
  ConsumerState<SpotifyConnectScreen> createState() => _SpotifyConnectScreenState();
}

class _SpotifyConnectScreenState extends ConsumerState<SpotifyConnectScreen> with WidgetsBindingObserver {
  bool _connecting = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      ref.invalidate(spotifyStatusProvider);
    }
  }

  Future<void> _connect() async {
    setState(() => _connecting = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final url = await ref.read(spotifyConnectProvider.notifier).getAuthorizeUrl();
      await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to open Spotify. Please try again.')));
    } finally {
      if (mounted) setState(() => _connecting = false);
    }
  }

  Future<void> _disconnect() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Disconnect Spotify?'),
        content: const Text('You can reconnect at any time.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Disconnect')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(spotifyStatusProvider.notifier).disconnect();
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to disconnect. Please try again.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final statusAsync = ref.watch(spotifyStatusProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Music Provider'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(showSpotifyConnectProvider.notifier).state = false,
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh status',
            onPressed: () => ref.invalidate(spotifyStatusProvider),
          ),
        ],
      ),
      body: statusAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(spotifyStatusProvider),
            child: const Text('Failed to load status. Retry'),
          ),
        ),
        data: (status) {
          return Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (status.connected) ...[
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.check_circle, color: Colors.green),
                      title: Text('Connected as ${status.spotifyUserId ?? "Spotify"}'),
                      subtitle: status.connectedAt != null ? Text('Since ${status.connectedAt}') : null,
                    ),
                  ),
                  const SizedBox(height: 20),
                  OutlinedButton(onPressed: _disconnect, child: const Text('Disconnect')),
                ] else ...[
                  const Text('Connect your Spotify account to personalize music recommendations.'),
                  const SizedBox(height: 20),
                  ElevatedButton(
                    onPressed: _connecting ? null : _connect,
                    child: _connecting
                        ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Text('Connect Spotify'),
                  ),
                ],
              ],
            ),
          );
        },
      ),
    );
  }
}
