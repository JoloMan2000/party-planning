import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../i18n/translate.dart';
import '../../models/music_admin_settings.dart';
import '../../models/music_planning_result.dart';
import '../../state/admin_providers.dart';
import '../../state/providers.dart';

/// Admin-Sektion für die Music Recommendation & Party Playlist Engine
/// (mirroring `render_music_playlist_section` in `"Party Planning.py"`):
/// Steuerparameter (Sliders/Checkbox), Playlist-Generierung und Anzeige der
/// generierten, nach Party-Phase gruppierten Playlist inkl. Erklärbarkeit
/// und Review-Hinweisen. Spotify-Export ist bewusst nicht Teil dieser
/// Sektion (deferred, siehe Phase-3-Plan).
class MusicPlaylistSection extends ConsumerStatefulWidget {
  const MusicPlaylistSection({super.key});

  @override
  ConsumerState<MusicPlaylistSection> createState() => _MusicPlaylistSectionState();
}

class _MusicPlaylistSectionState extends ConsumerState<MusicPlaylistSection> {
  double? _partyIntensity;
  double? _mainstreamDiscovery;
  double? _guestRequestPriority;
  bool? _explicitAllowed;
  int? _maxTracksPerArtist;
  bool _savingSettings = false;
  bool _generating = false;

  void _initFrom(MusicAdminSettings settings) {
    _partyIntensity ??= settings.partyIntensity;
    _mainstreamDiscovery ??= settings.mainstreamDiscovery;
    _guestRequestPriority ??= settings.guestRequestPriority;
    _explicitAllowed ??= settings.explicitAllowed;
    _maxTracksPerArtist ??= settings.maxTracksPerArtist;
  }

  @override
  Widget build(BuildContext context) {
    final translationsAsync = ref.watch(translationsProvider('de'));
    final settingsAsync = ref.watch(musicSettingsProvider);
    final playlistAsync = ref.watch(musicPlaylistProvider);

    return translationsAsync.when(
      loading: () => const Padding(
        padding: EdgeInsets.all(20),
        child: Center(child: CircularProgressIndicator()),
      ),
      error: (err, stack) => Padding(
        padding: const EdgeInsets.all(20),
        child: Text('Übersetzungen konnten nicht geladen werden.\n$err'),
      ),
      data: (translations) {
        String t(String key, [Map<String, Object?> params = const {}]) =>
            tr(translations, key, params);

        return settingsAsync.when(
          loading: () => const Padding(
            padding: EdgeInsets.all(20),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (err, stack) => Padding(
            padding: const EdgeInsets.all(20),
            child: Text('Musik-Settings konnten nicht geladen werden.\n$err'),
          ),
          data: (settings) {
            _initFrom(settings);

            return Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(t('music_settings_header'), style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 16),
                    Text('${t('music_party_intensity_label')}: ${_partyIntensity!.toStringAsFixed(2)}'),
                    Slider(
                      value: _partyIntensity!,
                      min: 0,
                      max: 1,
                      divisions: 20,
                      onChanged: (v) => setState(() => _partyIntensity = v),
                    ),
                    Text('${t('music_mainstream_discovery_label')}: ${_mainstreamDiscovery!.toStringAsFixed(2)}'),
                    Slider(
                      value: _mainstreamDiscovery!,
                      min: 0,
                      max: 1,
                      divisions: 20,
                      onChanged: (v) => setState(() => _mainstreamDiscovery = v),
                    ),
                    Text(
                      '${t('music_guest_request_priority_label')}: ${_guestRequestPriority!.toStringAsFixed(2)}',
                    ),
                    Slider(
                      value: _guestRequestPriority!,
                      min: 0,
                      max: 1,
                      divisions: 20,
                      onChanged: (v) => setState(() => _guestRequestPriority = v),
                    ),
                    CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      value: _explicitAllowed,
                      title: Text(t('music_explicit_allowed_label')),
                      onChanged: (v) => setState(() => _explicitAllowed = v ?? true),
                    ),
                    const SizedBox(height: 8),
                    TextFormField(
                      initialValue: _maxTracksPerArtist!.toString(),
                      keyboardType: TextInputType.number,
                      decoration: InputDecoration(
                        labelText: t('music_max_tracks_per_artist_label'),
                        border: const OutlineInputBorder(),
                      ),
                      onChanged: (value) {
                        final parsed = int.tryParse(value);
                        if (parsed != null && parsed >= 1 && parsed <= 10) {
                          _maxTracksPerArtist = parsed;
                        }
                      },
                    ),
                    const SizedBox(height: 16),
                    Align(
                      alignment: Alignment.centerRight,
                      child: ElevatedButton(
                        onPressed: _savingSettings ? null : () => _saveSettings(t),
                        child: _savingSettings
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : Text(t('btn_save_music_settings')),
                      ),
                    ),
                    const Divider(height: 32),
                    Text(t('music_playlist_header'), style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 12),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: ElevatedButton(
                        onPressed: _generating ? null : () => _generate(),
                        child: _generating
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : Text(t('btn_generate_playlist')),
                      ),
                    ),
                    const SizedBox(height: 16),
                    playlistAsync.when(
                      loading: () => const Center(child: CircularProgressIndicator()),
                      error: (err, stack) => Text('Playlist konnte nicht erzeugt werden.\n$err'),
                      data: (result) {
                        if (result == null) {
                          return Text(t('music_no_playlist_yet'),
                              style: Theme.of(context).textTheme.bodySmall);
                        }
                        return _PlaylistResultView(result: result, t: t);
                      },
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  Future<void> _saveSettings(String Function(String, [Map<String, Object?>]) t) async {
    final settings = MusicAdminSettings(
      partyIntensity: _partyIntensity!,
      mainstreamDiscovery: _mainstreamDiscovery!,
      guestRequestPriority: _guestRequestPriority!,
      explicitAllowed: _explicitAllowed!,
      maxTracksPerArtist: _maxTracksPerArtist!,
    );
    setState(() => _savingSettings = true);
    try {
      await ref.read(musicSettingsProvider.notifier).save(settings);
      if (!mounted) return;
      setState(() => _savingSettings = false);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(t('music_settings_saved'))));
    } catch (e) {
      if (!mounted) return;
      setState(() => _savingSettings = false);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Speichern fehlgeschlagen: $e')));
    }
  }

  Future<void> _generate() async {
    setState(() => _generating = true);
    try {
      await ref.read(musicPlaylistProvider.notifier).generate();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Playlist-Generierung fehlgeschlagen: $e')));
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }
}

class _PlaylistResultView extends StatelessWidget {
  final MusicPlanningResult result;
  final String Function(String, [Map<String, Object?>]) t;

  const _PlaylistResultView({required this.result, required this.t});

  @override
  Widget build(BuildContext context) {
    final phaseGroups = <String, List<PlaylistSlot>>{};
    for (final slot in result.playlist) {
      phaseGroups.putIfAbsent(slot.phaseId, () => []).add(slot);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 24,
          runSpacing: 12,
          children: [
            _Metric(label: t('music_metric_tracks'), value: '${result.totalTracks}'),
            _Metric(
              label: t('music_metric_duration'),
              value: '${(result.actualDurationMs / 60000).round()} min',
            ),
            _Metric(
              label: t('music_metric_guest_coverage'),
              value: '${(result.guestCoverage * 100).round()}%',
            ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          t('music_requested_coverage_caption', {
            'selected': result.requestedTracksSelected,
            'total': result.requestedTracksTotal,
          }),
          style: Theme.of(context).textTheme.bodySmall,
        ),
        if (result.reviewIssues.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text(t('music_review_issues_header'), style: const TextStyle(fontWeight: FontWeight.bold)),
          for (final issue in result.reviewIssues)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Text('⚠️ $issue'),
            ),
        ],
        const SizedBox(height: 16),
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          title: Text(t('music_explanations_header')),
          children: [
            for (final explanation in result.explanations)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Text('- $explanation'),
              ),
          ],
        ),
        const SizedBox(height: 8),
        for (final phase in result.phases)
          if (phaseGroups[phase.id] != null)
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: Text('${phase.label('de')} (${phaseGroups[phase.id]!.length})'),
              children: [
                for (final slot in phaseGroups[phase.id]!)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(
                      '${slot.position + 1}. ${slot.displayTitle}'
                      '${slot.supportingGuests.isNotEmpty ? ' (${slot.supportingGuests.join(', ')})' : ''}',
                    ),
                    subtitle: slot.reasons.isNotEmpty ? Text(slot.reasons.join(' · ')) : null,
                  ),
              ],
            ),
      ],
    );
  }
}

class _Metric extends StatelessWidget {
  final String label;
  final String value;

  const _Metric({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Theme.of(context).textTheme.bodySmall),
        Text(value, style: Theme.of(context).textTheme.titleMedium),
      ],
    );
  }
}
