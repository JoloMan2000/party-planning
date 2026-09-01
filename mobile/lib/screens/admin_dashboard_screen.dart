import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/admin_providers.dart';
import '../state/providers.dart';
import '../theme/party_theme.dart';
import '../widgets/admin/party_context_overrides_section.dart';
import '../widgets/admin/party_context_section.dart';
import '../widgets/admin/party_settings_section.dart';
import '../widgets/party_hero.dart';

/// Admin-Dashboard-Shell (mirroring `render_admin_view()`, Sektionsreihenfolge
/// aus `"Party Planning.py"`: Party-Settings -> Party-Context -> Overrides ->
/// Context-Dashboard -> Empfehlungen -> Musik-Playlist -> Antworten/CSV ->
/// Einkaufsliste). Sektionen werden schrittweise ergänzt; dies ist zunächst
/// nur das Gerüst mit Logout.
class AdminDashboardScreen extends ConsumerWidget {
  const AdminDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
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
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              PartyHero(
                title: '🛠️ Admin-Dashboard',
                subtitle: 'Party-Verwaltung',
                colors: colors,
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  TextButton.icon(
                    onPressed: () => ref.read(adminModeProvider.notifier).state = false,
                    icon: const Icon(Icons.arrow_back),
                    label: const Text('Zum Gast-Bereich'),
                  ),
                  TextButton.icon(
                    onPressed: () => ref.read(adminAuthProvider.notifier).logout(),
                    icon: const Icon(Icons.logout),
                    label: const Text('Ausloggen'),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              const PartySettingsSection(),
              const SizedBox(height: 16),
              const PartyContextSection(),
              const SizedBox(height: 16),
              const PartyContextOverridesSection(),
              const SizedBox(height: 16),
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(20),
                  child: Text(
                    'Weitere Sektionen (Context-Dashboard, Empfehlungen, '
                    'Musik-Playlist, Antworten, Einkaufsliste) folgen.',
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
