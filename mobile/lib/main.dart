import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'screens/intro_screen.dart';
import 'screens/language_screen.dart';
import 'screens/wizard_screen.dart';
import 'state/providers.dart';
import 'theme/party_theme.dart';

void main() {
  runApp(const ProviderScope(child: PartyApp()));
}

/// Root-Widget: routet zwischen Intro -> Sprachauswahl -> Wizard
/// (mirroring den State-Machine-Zweig oben in `render_guest_form()`).
class PartyApp extends ConsumerWidget {
  const PartyApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final enteredIntro = ref.watch(enteredIntroProvider);
    final language = ref.watch(languageProvider);
    final partyInfoAsync = ref.watch(partyInfoProvider(language ?? 'de'));
    final colors = partyInfoAsync.maybeWhen(
      data: (info) => PartyColors.fromThemeJson(info.theme),
      orElse: () => PartyColors.fromThemeJson(null),
    );

    Widget home;
    if (!enteredIntro) {
      home = const IntroScreen();
    } else if (language == null) {
      home = const LanguageScreen();
    } else {
      home = const WizardScreen();
    }

    return MaterialApp(
      title: 'Party Planning',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(colors),
      home: home,
    );
  }
}
