import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/social_privacy.dart';
import '../state/social_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

// Freiform-Strings serverseitig (validiert per Pydantic-field_validator in
// backend/app/schemas/social.py, kein Enum/Catalog-Endpoint) - diese
// Options-Listen sind eine reine Client-Konvention, mirrort
// discovery_preferences_screen.dart's _kPricePreferences-Muster.
const _kFriendListVisibility = ['nobody', 'friends', 'everyone'];
const _kFriendRequestPrivacy = ['nobody', 'everyone'];

/// Social-Graph-Phase-3: Privacy-Einstellungen für den Social Graph -
/// "Wer sieht meine Freundesliste?", "Wer darf mir eine Freundschaftsanfrage
/// senden?", "Bin ich per Username/Name auffindbar?". Erreichbar über eine
/// "Social Privacy"-Kachel auf `ProfileScreen`. Struktureller Klon von
/// `DiscoveryPreferencesScreen` (gleiches Save-Muster, gleiches
/// `ChoiceChip`/`SwitchListTile`-Vokabular - kein `Radio` existiert in
/// dieser Codebase).
class SocialPrivacyScreen extends ConsumerStatefulWidget {
  const SocialPrivacyScreen({super.key});

  @override
  ConsumerState<SocialPrivacyScreen> createState() => _SocialPrivacyScreenState();
}

class _SocialPrivacyScreenState extends ConsumerState<SocialPrivacyScreen> {
  bool _initialized = false;
  bool _saving = false;

  String _friendListVisibility = 'friends';
  String _friendRequestPrivacy = 'everyone';
  bool _discoverableByUsername = true;
  bool _discoverableByName = true;

  void _seedFrom(SocialPrivacy privacy) {
    if (_initialized) return;
    _initialized = true;
    _friendListVisibility = privacy.friendListVisibility;
    _friendRequestPrivacy = privacy.friendRequestPrivacy;
    _discoverableByUsername = privacy.discoverableByUsername;
    _discoverableByName = privacy.discoverableByName;
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final current = ref.read(socialPrivacyProvider).valueOrNull ??
          const SocialPrivacy(
            friendListVisibility: 'friends',
            friendRequestPrivacy: 'everyone',
            discoverableByUsername: true,
            discoverableByName: true,
          );
      await ref.read(socialPrivacyProvider.notifier).save(
            current.copyWith(
              friendListVisibility: _friendListVisibility,
              friendRequestPrivacy: _friendRequestPrivacy,
              discoverableByUsername: _discoverableByUsername,
              discoverableByName: _discoverableByName,
            ),
          );
      if (mounted) messenger.showSnackBar(const SnackBar(content: Text('Social privacy settings saved.')));
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to save. Please try again.')));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final privacyAsync = ref.watch(socialPrivacyProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Social Privacy'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(showSocialPrivacyProvider.notifier).state = false,
        ),
      ),
      body: privacyAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(socialPrivacyProvider),
            child: const Text('Failed to load privacy settings. Retry'),
          ),
        ),
        data: (privacy) {
          _seedFrom(privacy);
          return SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Who can see my friends?', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  children: _kFriendListVisibility
                      .map((value) => ChoiceChip(
                            label: Text(value[0].toUpperCase() + value.substring(1)),
                            selected: _friendListVisibility == value,
                            onSelected: (selected) =>
                                setState(() => _friendListVisibility = selected ? value : _friendListVisibility),
                          ))
                      .toList(),
                ),
                const SizedBox(height: 20),
                Text('Who can send me friend requests?', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  children: _kFriendRequestPrivacy
                      .map((value) => ChoiceChip(
                            label: Text(value[0].toUpperCase() + value.substring(1)),
                            selected: _friendRequestPrivacy == value,
                            onSelected: (selected) =>
                                setState(() => _friendRequestPrivacy = selected ? value : _friendRequestPrivacy),
                          ))
                      .toList(),
                ),
                const SizedBox(height: 20),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Allow people to find me by username'),
                  value: _discoverableByUsername,
                  onChanged: (value) => setState(() => _discoverableByUsername = value),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Allow people to find me by name'),
                  value: _discoverableByName,
                  onChanged: (value) => setState(() => _discoverableByName = value),
                ),
                const SizedBox(height: 20),
                ElevatedButton(
                  onPressed: _saving ? null : _save,
                  child: _saving
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Save'),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
