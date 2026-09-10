import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../state/auth_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Social-Graph-Phase-10: irreversibler Hard-Delete des eigenen Accounts
/// (`DELETE /api/v1/me`). Verlangt das aktuelle Passwort UND das getippte
/// Wort "DELETE" als Reibung. Bei Erfolg setzt der Notifier via
/// `AuthNotifier.logout()` `authProvider` auf `null` -> `main.dart` routet
/// automatisch auf den `LoginScreen` (dieser Screen wird dann verworfen).
class DeleteAccountScreen extends ConsumerStatefulWidget {
  const DeleteAccountScreen({super.key});

  @override
  ConsumerState<DeleteAccountScreen> createState() => _DeleteAccountScreenState();
}

class _DeleteAccountScreenState extends ConsumerState<DeleteAccountScreen> {
  final _passwordController = TextEditingController();
  final _confirmController = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _passwordController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  bool get _canSubmit =>
      _passwordController.text.isNotEmpty && _confirmController.text.trim() == 'DELETE';

  Future<void> _submit() async {
    setState(() => _error = null);
    try {
      await ref.read(deleteAccountProvider.notifier).delete(_passwordController.text);
      // Bei Erfolg ist der User bereits ausgeloggt -> main.dart zeigt den
      // LoginScreen; nichts weiter zu tun.
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e is ApiException && e.statusCode == 403
            ? 'Incorrect password.'
            : 'Failed to delete account. Please try again.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final deleteState = ref.watch(deleteAccountProvider);
    final isLoading = deleteState.isLoading;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Delete Account'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => ref.read(showDeleteAccountProvider.notifier).state = false,
        ),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'This permanently deletes your account. Parties and organizers you '
                'own are deleted too, along with your friends, follows and messages. '
                'This cannot be undone.',
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
              const SizedBox(height: 20),
              TextField(
                controller: _passwordController,
                obscureText: true,
                onChanged: (_) => setState(() {}),
                decoration: const InputDecoration(
                  labelText: 'Current password',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _confirmController,
                onChanged: (_) => setState(() {}),
                decoration: const InputDecoration(
                  labelText: 'Type DELETE to confirm',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              if (_error != null)
                Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              const SizedBox(height: 12),
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: Theme.of(context).colorScheme.error,
                  foregroundColor: Theme.of(context).colorScheme.onError,
                ),
                onPressed: (isLoading || !_canSubmit) ? null : _submit,
                child: isLoading
                    ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Delete my account'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
