import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/auth_providers.dart';
import '../theme/party_theme.dart';
import '../widgets/party_hero.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Erreicht via `partyplanning://unlock/{token}`-Deep-Link
/// (`main.dart::_handleDeepLink`). Bestätigt den Token automatisch beim
/// Mounten, mirroring `VerifyEmailScreen`. Bei Erfolg ist der Account
/// sofort wieder normal einloggbar (Passwort/Refresh-Tokens bleiben
/// unangetastet - siehe `backend/app/routers/auth.py::unlock_account`).
class UnlockAccountScreen extends ConsumerStatefulWidget {
  final String token;

  const UnlockAccountScreen({super.key, required this.token});

  @override
  ConsumerState<UnlockAccountScreen> createState() => _UnlockAccountScreenState();
}

class _UnlockAccountScreenState extends ConsumerState<UnlockAccountScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref.read(unlockAccountProvider.notifier).confirm(widget.token));
  }

  @override
  Widget build(BuildContext context) {
    final unlockState = ref.watch(unlockAccountProvider);
    final colors = PartyColors.fromThemeJson(null);

    Widget content;
    if (unlockState.isLoading) {
      content = const CircularProgressIndicator();
    } else if (unlockState.hasError) {
      content = const Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.error_outline, size: 48),
          SizedBox(height: 12),
          Text(
            'This unlock link is invalid or expired.',
            textAlign: TextAlign.center,
          ),
        ],
      );
    } else {
      content = const Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.lock_open_outlined, size: 48),
          SizedBox(height: 12),
          Text(
            'Your account has been unlocked. You can log in now.',
            textAlign: TextAlign.center,
          ),
        ],
      );
    }

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  PartyHero(
                    title: '🔒 Unlock account',
                    subtitle: 'Confirming your unlock request',
                    colors: colors,
                  ),
                  const SizedBox(height: 24),
                  content,
                  const SizedBox(height: 20),
                  if (!unlockState.isLoading)
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: () => ref.read(accountUnlockTokenProvider.notifier).state = null,
                        child: const Text('Back to login'),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
