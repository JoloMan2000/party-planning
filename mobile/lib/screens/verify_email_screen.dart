import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/auth_providers.dart';
import '../theme/party_theme.dart';
import '../widgets/party_hero.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Erreicht via `partyplanning://verify/{token}`-Deep-Link
/// (`main.dart::_handleDeepLink`). Bestätigt den Token automatisch beim
/// Mounten (kein Nutzer-Input nötig, anders als `ResetPasswordScreen`) und
/// zeigt danach einen Erfolgs- oder Fehler-Zustand. Ein fehlgeschlagenes
/// Verify ist nicht fatal - E-Mail-Verifikation ist ein "soft"/nicht-
/// blockierendes Feature, der Nutzer kann die App trotzdem normal nutzen.
class VerifyEmailScreen extends ConsumerStatefulWidget {
  final String token;

  const VerifyEmailScreen({super.key, required this.token});

  @override
  ConsumerState<VerifyEmailScreen> createState() => _VerifyEmailScreenState();
}

class _VerifyEmailScreenState extends ConsumerState<VerifyEmailScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref.read(verifyEmailProvider.notifier).confirm(widget.token));
  }

  @override
  Widget build(BuildContext context) {
    final verifyState = ref.watch(verifyEmailProvider);
    final colors = PartyColors.fromThemeJson(null);

    Widget content;
    if (verifyState.isLoading) {
      content = const CircularProgressIndicator();
    } else if (verifyState.hasError) {
      content = const Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.error_outline, size: 48),
          SizedBox(height: 12),
          Text(
            'This verification link is invalid or expired.',
            textAlign: TextAlign.center,
          ),
        ],
      );
    } else {
      content = const Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.check_circle_outline, size: 48),
          SizedBox(height: 12),
          Text(
            'Your email has been verified!',
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
                    title: '📧 Verify your email',
                    subtitle: 'Confirming your email address',
                    colors: colors,
                  ),
                  const SizedBox(height: 24),
                  content,
                  const SizedBox(height: 20),
                  if (!verifyState.isLoading)
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: () => ref.read(emailVerificationTokenProvider.notifier).state = null,
                        child: const Text('Continue'),
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
