import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/providers.dart';
import '../theme/party_theme.dart';
import '../widgets/party_hero.dart';

/// Themen-Intro-Screen (mirroring `render_event_intro()`): Party-Name +
/// Event-Branding, bewusst noch zweisprachig (DE/EN), da die Sprache an
/// dieser Stelle noch nicht bekannt ist (Sprachauswahl folgt danach).
class IntroScreen extends ConsumerWidget {
  const IntroScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final partyInfoAsync = ref.watch(partyInfoProvider('de'));

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: partyInfoAsync.when(
              data: (info) {
                final colors = PartyColors.fromThemeJson(info.theme);
                final introSubtitle = (info.theme['intro_subtitle'] as String?) ?? '';
                return Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    PartyHero(
                      title: info.title,
                      subtitle: introSubtitle,
                      meta: info.metaDatetime,
                      colors: colors,
                    ),
                    const SizedBox(height: 24),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: () => ref.read(enteredIntroProvider.notifier).state = true,
                        child: const Text('Weiter / Continue ➡️'),
                      ),
                    ),
                  ],
                );
              },
              loading: () => const CircularProgressIndicator(),
              error: (err, stack) => _ErrorRetry(
                message: 'Verbindung zum Server fehlgeschlagen.\n$err',
                onRetry: () => ref.invalidate(partyInfoProvider('de')),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ErrorRetry extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const _ErrorRetry({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(message, textAlign: TextAlign.center),
        const SizedBox(height: 12),
        ElevatedButton(onPressed: onRetry, child: const Text('Erneut versuchen / Retry')),
      ],
    );
  }
}
