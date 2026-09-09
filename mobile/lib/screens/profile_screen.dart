import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../models/profile.dart';
import '../state/profile_providers.dart';
import '../state/social_providers.dart';
import '../state/spotify_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Social-Profil-Einstellungen (bisher nur backend-seitig vorhanden, nie über
/// Mobile erreichbar - Phase 6/7 des Account-basierten Pivots). Erreichbar
/// über ein Personen-Icon in der `HomeShell`-AppBar. Solange das Backend
/// `GET /me/profile` noch nie erfolgreich war (404, kein Geburtsdatum je
/// gesetzt), zeigt dieser Screen statt des normalen Formulars ein
/// Onboarding-Formular zur Geburtsdatum-Eingabe an - das ist der einzige
/// Weg, wie ein Profil überhaupt erst angelegt wird.
class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  final _genderController = TextEditingController();
  final _bioController = TextEditingController();
  final _usernameController = TextEditingController();
  bool _initialized = false;
  bool _saving = false;

  @override
  void dispose() {
    _genderController.dispose();
    _bioController.dispose();
    _usernameController.dispose();
    super.dispose();
  }

  void _seedFrom(Profile profile) {
    if (_initialized) return;
    _initialized = true;
    _genderController.text = profile.gender;
    _bioController.text = profile.bio;
    _usernameController.text = profile.username;
  }

  Future<DateTime?> _pickBirthDate() {
    final now = DateTime.now();
    return showDatePicker(
      context: context,
      initialDate: DateTime(now.year - 20, now.month, now.day),
      firstDate: DateTime(now.year - 120, now.month, now.day),
      lastDate: now.subtract(const Duration(days: 1)),
    );
  }

  Future<void> _correctBirthDate() async {
    final picked = await _pickBirthDate();
    if (picked == null || !mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(profileProvider.notifier).correctBirthDate(birthDate: picked);
    } catch (e) {
      final message = e is ApiException && e.detail is String
          ? e.detail as String
          : 'Failed to update birth date. Please try again.';
      messenger.showSnackBar(SnackBar(content: Text(message)));
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final trimmedUsername = _usernameController.text.trim();
      await ref.read(profileProvider.notifier).save(
            gender: _genderController.text.trim(),
            bio: _bioController.text.trim(),
            username: trimmedUsername.isEmpty ? null : trimmedUsername,
          );
      if (mounted) messenger.showSnackBar(const SnackBar(content: Text('Profile saved.')));
    } catch (e) {
      final message = e is ApiException && e.detail is String
          ? e.detail as String
          : 'Failed to save. Please try again.';
      messenger.showSnackBar(SnackBar(content: Text(message)));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final profileAsync = ref.watch(profileProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Profile'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(showProfileProvider.notifier).state = false,
        ),
      ),
      body: profileAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) {
          if (err is ApiException && err.statusCode == 404) {
            return _OnboardingBirthDateForm(onPick: _pickBirthDate);
          }
          return Center(
            child: TextButton(
              onPressed: () => ref.invalidate(profileProvider),
              child: const Text('Failed to load profile. Retry'),
            ),
          );
        },
        data: (profile) {
          _seedFrom(profile);
          return SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Age'),
                  subtitle: Text('${profile.age}'),
                ),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Birth date'),
                  subtitle: Text(
                    '${profile.birthDate.year}-${profile.birthDate.month.toString().padLeft(2, '0')}-${profile.birthDate.day.toString().padLeft(2, '0')}',
                  ),
                  trailing: TextButton(onPressed: _correctBirthDate, child: const Text('Correct')),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _usernameController,
                  decoration: const InputDecoration(
                    labelText: 'Username',
                    prefixText: '@',
                    border: OutlineInputBorder(),
                    helperText: '3-30 characters: letters, numbers, underscore, period.',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _genderController,
                  decoration: const InputDecoration(labelText: 'Gender', border: OutlineInputBorder()),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _bioController,
                  maxLines: 4,
                  decoration: const InputDecoration(labelText: 'Bio', border: OutlineInputBorder()),
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
                const SizedBox(height: 24),
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.music_note),
                    title: const Text('Music Provider'),
                    subtitle: Text(
                      ref.watch(spotifyStatusProvider).maybeWhen(
                            data: (status) => status.connected ? 'Spotify connected' : 'Not connected',
                            orElse: () => 'Checking status...',
                          ),
                    ),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => ref.read(showSpotifyConnectProvider.notifier).state = true,
                  ),
                ),
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.people),
                    title: const Text('Friends'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => ref.read(showFriendsProvider.notifier).state = true,
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

/// Erstanlage des Profils - der einzige Weg zu einem gültigen `data:`-Zustand
/// von `profileProvider`, solange `GET /me/profile` noch 404 liefert.
class _OnboardingBirthDateForm extends ConsumerStatefulWidget {
  final Future<DateTime?> Function() onPick;

  const _OnboardingBirthDateForm({required this.onPick});

  @override
  ConsumerState<_OnboardingBirthDateForm> createState() => _OnboardingBirthDateFormState();
}

class _OnboardingBirthDateFormState extends ConsumerState<_OnboardingBirthDateForm> {
  DateTime? _picked;
  String? _error;
  bool _submitting = false;

  Future<void> _pick() async {
    final picked = await widget.onPick();
    if (picked == null || !mounted) return;
    setState(() {
      _picked = picked;
      _error = null;
    });
  }

  Future<void> _continue() async {
    final picked = _picked;
    if (picked == null) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await ref.read(profileProvider.notifier).correctBirthDate(birthDate: picked);
    } catch (e) {
      setState(() {
        _error = e is ApiException && e.detail is String
            ? e.detail as String
            : 'Failed to save birth date. Please try again.';
      });
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final picked = _picked;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'Tell us your birth date to get started.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 16),
            ),
            const SizedBox(height: 20),
            OutlinedButton(
              onPressed: _submitting ? null : _pick,
              child: Text(
                picked == null
                    ? 'Pick birth date'
                    : '${picked.year}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}',
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: const TextStyle(color: Colors.red)),
            ],
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: (_submitting || picked == null) ? null : _continue,
              child: _submitting
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Continue'),
            ),
          ],
        ),
      ),
    );
  }
}
