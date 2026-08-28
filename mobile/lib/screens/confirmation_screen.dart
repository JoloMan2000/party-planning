import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../i18n/translate.dart';
import '../state/providers.dart';
import '../theme/party_theme.dart';

/// Erfolgs-/Bestätigungsseite nach dem Absenden (mirroring `st.success(...)`
/// + `render_calendar_export_section()`): Google-Kalender-Link + .ics-Teilen,
/// nur sichtbar, wenn der Admin bereits ein Party-Datum konfiguriert hat.
class ConfirmationScreen extends ConsumerWidget {
  final Map<String, String> translations;
  final PartyColors colors;

  const ConfirmationScreen({super.key, required this.translations, required this.colors});

  String _t(String key, [Map<String, Object?> params = const {}]) => tr(translations, key, params);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lang = ref.watch(languageProvider)!;
    final partyInfoAsync = ref.watch(partyInfoProvider(lang));

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFFE7EFE3),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: const Color(0xFF3F5B41).withValues(alpha: 0.3)),
            ),
            child: Row(
              children: [
                const Icon(Icons.check_circle, color: Color(0xFF3F5B41)),
                const SizedBox(width: 12),
                Expanded(child: Text(_t('submitted_msg'))),
              ],
            ),
          ),
          partyInfoAsync.when(
            data: (info) {
              if (!info.hasScheduledDate) return const SizedBox.shrink();
              return Padding(
                padding: const EdgeInsets.only(top: 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Divider(),
                    const SizedBox(height: 8),
                    Text(_t('calendar_section_header'),
                        style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 12),
                    if (info.googleCalendarUrl != null)
                      ElevatedButton.icon(
                        icon: const Icon(Icons.calendar_today, size: 18),
                        label: Text(_t('calendar_google_button')),
                        onPressed: () => launchUrl(
                          Uri.parse(info.googleCalendarUrl!),
                          mode: LaunchMode.externalApplication,
                        ),
                      ),
                    const SizedBox(height: 8),
                    OutlinedButton.icon(
                      icon: const Icon(Icons.download, size: 18),
                      label: Text(_t('calendar_ics_button')),
                      onPressed: () async {
                        final ics = await ref.read(apiClientProvider).getCalendarIcs();
                        if (ics == null) return;
                        await Share.shareXFiles(
                          [
                            XFile.fromData(
                              Uint8List.fromList(ics),
                              name: 'party.ics',
                              mimeType: 'text/calendar',
                            ),
                          ],
                        );
                      },
                    ),
                  ],
                ),
              );
            },
            loading: () => const Padding(
              padding: EdgeInsets.only(top: 24),
              child: Center(child: CircularProgressIndicator()),
            ),
            error: (err, stack) => const SizedBox.shrink(),
          ),
        ],
      ),
    );
  }
}
