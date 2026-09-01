import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/language_option.dart';
import '../state/admin_providers.dart';
import '../state/providers.dart';
import '../theme/party_theme.dart';
import '../widgets/party_hero.dart';

/// Icon-basierte Sprachauswahl (mirroring `render_language_landing()`):
/// primäre Sprachen als Grid-Buttons, weitere Sprachen über ein "Mehr"-Menü.
class LanguageScreen extends ConsumerWidget {
  const LanguageScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final languagesAsync = ref.watch(languagesProvider);
    final partyInfoAsync = ref.watch(partyInfoProvider('de'));
    final colors = partyInfoAsync.maybeWhen(
      data: (info) => PartyColors.fromThemeJson(info.theme),
      orElse: () => PartyColors.fromThemeJson(null),
    );

    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            children: [
              PartyHero(
                title: '🌿🪵✨',
                subtitle: 'Choose your language / Wähle deine Sprache',
                colors: colors,
              ),
              const SizedBox(height: 24),
              languagesAsync.when(
                data: (languages) => _LanguageGrid(languages: languages),
                loading: () => const CircularProgressIndicator(),
                error: (err, stack) => Column(
                  children: [
                    Text('Verbindung zum Server fehlgeschlagen.\n$err', textAlign: TextAlign.center),
                    const SizedBox(height: 12),
                    ElevatedButton(
                      onPressed: () => ref.invalidate(languagesProvider),
                      child: const Text('Erneut versuchen / Retry'),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              TextButton(
                onPressed: () => ref.read(adminModeProvider.notifier).state = true,
                child: const Text('Admin'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LanguageGrid extends ConsumerWidget {
  final LanguagesResponse languages;

  const _LanguageGrid({required this.languages});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    void select(String code) => ref.read(languageProvider.notifier).state = code;

    return Wrap(
      spacing: 12,
      runSpacing: 12,
      alignment: WrapAlignment.center,
      children: [
        for (final lang in languages.primaryLanguages)
          _LanguageButton(language: lang, onTap: () => select(lang.code)),
        _MoreLanguagesButton(languages: languages.extraLanguages, onSelected: select),
      ],
    );
  }
}

class _LanguageButton extends StatelessWidget {
  final LanguageOption language;
  final VoidCallback onTap;

  const _LanguageButton({required this.language, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 100,
      height: 84,
      child: ElevatedButton(
        onPressed: onTap,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(language.emoji, style: const TextStyle(fontSize: 22)),
            const SizedBox(height: 4),
            Text(language.name, textAlign: TextAlign.center, style: const TextStyle(fontSize: 12)),
          ],
        ),
      ),
    );
  }
}

class _MoreLanguagesButton extends StatelessWidget {
  final List<LanguageOption> languages;
  final ValueChanged<String> onSelected;

  const _MoreLanguagesButton({required this.languages, required this.onSelected});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 100,
      height: 84,
      child: ElevatedButton(
        onPressed: () => _showLanguageSheet(context),
        child: const Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text('🌐', style: TextStyle(fontSize: 22)),
            SizedBox(height: 4),
            Text('More', style: TextStyle(fontSize: 12)),
          ],
        ),
      ),
    );
  }

  void _showLanguageSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            for (final lang in languages)
              ListTile(
                leading: Text(lang.emoji, style: const TextStyle(fontSize: 20)),
                title: Text(lang.name),
                onTap: () {
                  Navigator.of(context).pop();
                  onSelected(lang.code);
                },
              ),
          ],
        ),
      ),
    );
  }
}
