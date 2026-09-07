import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/auth_providers.dart';
import '../state/providers.dart';
import '../theme/party_theme.dart';
import '../widgets/admin/catalog_curation_section.dart';
import '../widgets/admin/party_context_dashboard_section.dart';
import '../widgets/admin/party_context_overrides_section.dart';
import '../widgets/admin/party_context_section.dart';
import '../widgets/admin/party_settings_section.dart';
import '../widgets/admin/music_playlist_section.dart';
import '../widgets/admin/recommendations_section.dart';
import '../widgets/admin/responses_section.dart';
import '../widgets/admin/shopping_list_section.dart';
import '../widgets/party_hero.dart';

/// Admin-Dashboard-Shell (mirroring `render_admin_view()`, Sektionsreihenfolge
/// aus `"Party Planning.py"`: Party-Settings -> Party-Context -> Overrides ->
/// Catalog-Curation -> Context-Dashboard -> Empfehlungen -> Musik-Playlist ->
/// Antworten/CSV -> Einkaufsliste). Spotify-Export ist bewusst nicht Teil
/// dieses Dashboards (deferred, siehe Phase-3-Plan). Seit Phase 4 party-
/// gescoped statt über einen globalen Admin-Passwort-Modus erreichbar - siehe
/// "Verwalten"-Button auf `PartyDetailScreen`.
class AdminDashboardScreen extends ConsumerWidget {
  final String partyId;

  const AdminDashboardScreen({super.key, required this.partyId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final partyInfoAsync = ref.watch(partyInfoProvider(partyId));
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
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: () => ref.read(selectedAdminPartyIdProvider.notifier).state = null,
                  icon: const Icon(Icons.arrow_back),
                  label: const Text('Zurück zur Party'),
                ),
              ),
              const SizedBox(height: 12),
              PartySettingsSection(partyId: partyId),
              const SizedBox(height: 16),
              PartyContextSection(partyId: partyId),
              const SizedBox(height: 16),
              PartyContextOverridesSection(partyId: partyId),
              const SizedBox(height: 16),
              CatalogCurationSection(partyId: partyId),
              const SizedBox(height: 16),
              PartyContextDashboardSection(partyId: partyId),
              const SizedBox(height: 16),
              RecommendationsSection(partyId: partyId),
              const SizedBox(height: 16),
              MusicPlaylistSection(partyId: partyId),
              const SizedBox(height: 16),
              ResponsesSection(partyId: partyId),
              const SizedBox(height: 16),
              ShoppingListSection(partyId: partyId),
            ],
          ),
        ),
      ),
    );
  }
}
