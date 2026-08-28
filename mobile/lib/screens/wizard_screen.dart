import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../i18n/translate.dart';
import '../models/guest_response_draft.dart';
import '../models/song_request.dart';
import '../state/providers.dart';
import '../state/wizard_state.dart';
import '../theme/party_theme.dart';
import '../widgets/catalog_picker.dart';
import '../widgets/party_hero.dart';
import 'confirmation_screen.dart';

/// Der 4-Schritte-Gäste-Fragebogen (mirroring den `step`-Zweig von
/// `render_guest_form()`), gefolgt von der Bestätigungsseite.
class WizardScreen extends ConsumerWidget {
  const WizardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lang = ref.watch(languageProvider)!;
    final wizard = ref.watch(wizardProvider);
    final translationsAsync = ref.watch(translationsProvider(lang));
    final partyInfoAsync = ref.watch(partyInfoProvider(lang));

    return Scaffold(
      body: SafeArea(
        child: translationsAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (err, stack) => Center(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('Verbindung zum Server fehlgeschlagen.\n$err', textAlign: TextAlign.center),
                  const SizedBox(height: 12),
                  ElevatedButton(
                    onPressed: () => ref.invalidate(translationsProvider(lang)),
                    child: const Text('Erneut versuchen / Retry'),
                  ),
                ],
              ),
            ),
          ),
          data: (translations) {
            String t(String key, [Map<String, Object?> params = const {}]) =>
                tr(translations, key, params);

            final colors = partyInfoAsync.maybeWhen(
              data: (info) => PartyColors.fromThemeJson(info.theme),
              orElse: () => PartyColors.fromThemeJson(null),
            );
            final title = partyInfoAsync.maybeWhen(data: (info) => info.title, orElse: () => '');
            final meta =
                partyInfoAsync.maybeWhen(data: (info) => info.metaDatetime, orElse: () => null);

            if (wizard.submitted) {
              return ConfirmationScreen(translations: translations, colors: colors);
            }

            return SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Column(
                children: [
                  PartyHero(
                    title: title,
                    subtitle: t('hero_subtitle'),
                    meta: meta,
                    colors: colors,
                  ),
                  const SizedBox(height: 20),
                  LinearProgressIndicator(value: wizard.step / totalWizardSteps),
                  const SizedBox(height: 20),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: _StepContent(translations: translations, lang: lang),
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextButton(
                    onPressed: () {
                      ref.read(wizardProvider.notifier).reset();
                      ref.read(languageProvider.notifier).state = null;
                    },
                    child: Text(t('change_language')),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

class _StepContent extends ConsumerWidget {
  final Map<String, String> translations;
  final String lang;

  const _StepContent({required this.translations, required this.lang});

  String _t(String key, [Map<String, Object?> params = const {}]) => tr(translations, key, params);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final wizard = ref.watch(wizardProvider);
    switch (wizard.step) {
      case 1:
        return _Step1(t: _t);
      case 2:
        return _Step2(t: _t, lang: lang, translations: translations);
      case 3:
        return _Step3(t: _t, lang: lang, translations: translations);
      case 4:
      default:
        return _Step4(t: _t);
    }
  }
}

typedef _Translator = String Function(String key, [Map<String, Object?> params]);

class _Step1 extends ConsumerWidget {
  final _Translator t;

  const _Step1({required this.t});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final wizard = ref.watch(wizardProvider);
    final notifier = ref.read(wizardProvider.notifier);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(t('step1_header', {'n': totalWizardSteps}),
            style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 16),
        TextField(
          decoration: InputDecoration(labelText: t('name_label'), border: const OutlineInputBorder()),
          controller: TextEditingController(text: wizard.name)
            ..selection = TextSelection.collapsed(offset: wizard.name.length),
          onChanged: notifier.setName,
        ),
        const SizedBox(height: 16),
        InkWell(
          onTap: () async {
            final picked = await showTimePicker(context: context, initialTime: wizard.startTime);
            if (picked != null) notifier.setStartTime(picked);
          },
          child: InputDecorator(
            decoration: InputDecoration(labelText: t('time_label'), border: const OutlineInputBorder()),
            child: Text(wizard.startTimeFormatted),
          ),
        ),
        const SizedBox(height: 20),
        Align(
          alignment: Alignment.centerRight,
          child: ElevatedButton(
            onPressed: wizard.name.trim().isEmpty ? null : notifier.nextStep,
            child: Text(t('btn_next')),
          ),
        ),
      ],
    );
  }
}

class _Step2 extends ConsumerWidget {
  final _Translator t;
  final String lang;
  final Map<String, String> translations;

  const _Step2({required this.t, required this.lang, required this.translations});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final wizard = ref.watch(wizardProvider);
    final notifier = ref.read(wizardProvider.notifier);
    final drinksAsync = ref.watch(drinksProvider(lang));
    final recommendedAsync = ref.watch(recommendationsProvider(
      (name: wizard.name, drinks: wizard.drinks, food: wizard.food),
    ));
    final partyInfoAsync = ref.watch(partyInfoProvider(lang));
    final occasionLabel = partyInfoAsync.maybeWhen(
      data: (info) => info.partyName.isNotEmpty ? info.partyName : info.eventType,
      orElse: () => '',
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(t('step2_header', {'n': totalWizardSteps}),
            style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 4),
        Text(t('drinks_label')),
        const SizedBox(height: 16),
        drinksAsync.when(
          data: (items) => CatalogPicker(
            items: items,
            selectedIds: wizard.drinks,
            onChanged: notifier.setDrinks,
            translations: translations,
            recommendedIds: recommendedAsync.maybeWhen(data: (r) => r, orElse: () => const []),
            recommendedLabel: occasionLabel,
          ),
          loading: () => const Padding(
            padding: EdgeInsets.symmetric(vertical: 24),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (err, stack) => Text('Fehler beim Laden des Katalogs.\n$err'),
        ),
        const SizedBox(height: 12),
        TextField(
          decoration:
              InputDecoration(labelText: t('drinks_freetext_label'), border: const OutlineInputBorder()),
          controller: TextEditingController(text: wizard.drinksFreetext)
            ..selection = TextSelection.collapsed(offset: wizard.drinksFreetext.length),
          onChanged: notifier.setDrinksFreetext,
        ),
        const SizedBox(height: 20),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            OutlinedButton(onPressed: notifier.previousStep, child: Text(t('btn_back'))),
            ElevatedButton(onPressed: notifier.nextStep, child: Text(t('btn_next'))),
          ],
        ),
      ],
    );
  }
}

class _Step3 extends ConsumerWidget {
  final _Translator t;
  final String lang;
  final Map<String, String> translations;

  const _Step3({required this.t, required this.lang, required this.translations});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final wizard = ref.watch(wizardProvider);
    final notifier = ref.read(wizardProvider.notifier);
    final foodAsync = ref.watch(foodProvider(lang));
    final recommendedAsync = ref.watch(recommendationsProvider(
      (name: wizard.name, drinks: wizard.drinks, food: wizard.food),
    ));
    final partyInfoAsync = ref.watch(partyInfoProvider(lang));
    final occasionLabel = partyInfoAsync.maybeWhen(
      data: (info) => info.partyName.isNotEmpty ? info.partyName : info.eventType,
      orElse: () => '',
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(t('step3_header', {'n': totalWizardSteps}),
            style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 4),
        Text(t('food_label')),
        const SizedBox(height: 16),
        foodAsync.when(
          data: (items) => CatalogPicker(
            items: items,
            selectedIds: wizard.food,
            onChanged: notifier.setFood,
            translations: translations,
            recommendedIds: recommendedAsync.maybeWhen(data: (r) => r, orElse: () => const []),
            recommendedLabel: occasionLabel,
          ),
          loading: () => const Padding(
            padding: EdgeInsets.symmetric(vertical: 24),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (err, stack) => Text('Fehler beim Laden des Katalogs.\n$err'),
        ),
        const SizedBox(height: 12),
        TextField(
          decoration:
              InputDecoration(labelText: t('food_freetext_label'), border: const OutlineInputBorder()),
          controller: TextEditingController(text: wizard.foodFreetext)
            ..selection = TextSelection.collapsed(offset: wizard.foodFreetext.length),
          onChanged: notifier.setFoodFreetext,
        ),
        const SizedBox(height: 20),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            OutlinedButton(onPressed: notifier.previousStep, child: Text(t('btn_back'))),
            ElevatedButton(onPressed: notifier.nextStep, child: Text(t('btn_next'))),
          ],
        ),
      ],
    );
  }
}

class _Step4 extends ConsumerStatefulWidget {
  final _Translator t;

  const _Step4({required this.t});

  @override
  ConsumerState<_Step4> createState() => _Step4State();
}

class _Step4State extends ConsumerState<_Step4> {
  final _artistController = TextEditingController();
  final _titleController = TextEditingController();

  @override
  void dispose() {
    _artistController.dispose();
    _titleController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.t;
    final wizard = ref.watch(wizardProvider);
    final notifier = ref.read(wizardProvider.notifier);
    final canAdd = _artistController.text.trim().isNotEmpty && _titleController.text.trim().isNotEmpty;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(t('step4_header', {'n': totalWizardSteps}),
            style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 4),
        Text(t('step4_caption')),
        const SizedBox(height: 16),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _artistController,
                decoration:
                    InputDecoration(labelText: t('artist_label'), border: const OutlineInputBorder()),
                onChanged: (_) => setState(() {}),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                controller: _titleController,
                decoration:
                    InputDecoration(labelText: t('title_label'), border: const OutlineInputBorder()),
                onChanged: (_) => setState(() {}),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        ElevatedButton(
          onPressed: canAdd
              ? () {
                  notifier.addSong(SongRequest(
                    artist: _artistController.text.trim(),
                    title: _titleController.text.trim(),
                  ));
                  _artistController.clear();
                  _titleController.clear();
                  setState(() {});
                }
              : null,
          child: Text(t('btn_add_song')),
        ),
        if (wizard.songs.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text(t('your_songs_label')),
          for (var i = 0; i < wizard.songs.length; i++)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: Text('🎶 ${wizard.songs[i].artist} – ${wizard.songs[i].title}'),
              trailing: IconButton(
                icon: const Icon(Icons.close),
                onPressed: () => notifier.removeSongAt(i),
              ),
            ),
        ],
        const SizedBox(height: 20),
        if (wizard.submitError != null) ...[
          Text(wizard.submitError!, style: const TextStyle(color: Colors.red)),
          const SizedBox(height: 8),
        ],
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            OutlinedButton(
              onPressed: wizard.submitting ? null : notifier.previousStep,
              child: Text(t('btn_back')),
            ),
            ElevatedButton(
              onPressed: wizard.submitting ? null : () => _submit(context),
              child: wizard.submitting
                  ? const SizedBox(
                      width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : Text(t('btn_submit')),
            ),
          ],
        ),
      ],
    );
  }

  Future<void> _submit(BuildContext context) async {
    final wizard = ref.read(wizardProvider);
    final notifier = ref.read(wizardProvider.notifier);
    notifier.markSubmitting();
    try {
      await ref.read(apiClientProvider).submitResponse(GuestResponseDraft(
            name: wizard.name.trim(),
            startTime: wizard.startTimeFormatted,
            drinks: wizard.drinks,
            drinksFreetext: wizard.drinksFreetext,
            food: wizard.food,
            foodFreetext: wizard.foodFreetext,
            songs: wizard.songs,
          ));
      notifier.markSubmitted();
    } catch (err) {
      notifier.markSubmitError('$err');
    }
  }
}
