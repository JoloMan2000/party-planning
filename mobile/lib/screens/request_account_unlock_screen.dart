import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/auth_providers.dart';
import '../theme/party_theme.dart';
import '../widgets/party_hero.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Mirrors `ForgotPasswordScreen` - E-Mail eingeben, Unlock-Link anfordern.
/// Zeigt IMMER dieselbe statische Erfolgsmeldung (mirroring die generische
/// Backend-Response in `auth.py::request_account_unlock` - Account-Existenz
/// darf niemals über UI-Unterschiede verraten werden).
class RequestAccountUnlockScreen extends ConsumerStatefulWidget {
  const RequestAccountUnlockScreen({super.key});

  @override
  ConsumerState<RequestAccountUnlockScreen> createState() => _RequestAccountUnlockScreenState();
}

class _RequestAccountUnlockScreenState extends ConsumerState<RequestAccountUnlockScreen> {
  final _emailController = TextEditingController();
  bool _submitted = false;

  @override
  void dispose() {
    _emailController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final requestState = ref.watch(requestAccountUnlockProvider);
    final colors = PartyColors.fromThemeJson(null);
    final isLoading = requestState.isLoading;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  PartyHero(
                    title: '🔒 Unlock your account',
                    subtitle: 'Enter your email and we will send you an unlock link',
                    colors: colors,
                  ),
                  const SizedBox(height: 24),
                  if (_submitted) ...[
                    const Icon(Icons.mark_email_read_outlined, size: 48),
                    const SizedBox(height: 12),
                    const Text(
                      "If that account exists, we've sent an unlock link to its email address. "
                      'Please check your inbox.',
                      textAlign: TextAlign.center,
                    ),
                  ] else ...[
                    TextField(
                      controller: _emailController,
                      autofocus: true,
                      keyboardType: TextInputType.emailAddress,
                      decoration: const InputDecoration(
                        labelText: 'Email',
                        border: OutlineInputBorder(),
                      ),
                      onSubmitted: (_) => _submit(),
                    ),
                    const SizedBox(height: 20),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: isLoading ? null : _submit,
                        child: isLoading
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Text('Send unlock link'),
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  TextButton(
                    onPressed: () => ref.read(showAccountUnlockRequestProvider.notifier).state = false,
                    child: const Text('Back to login'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _submit() async {
    final email = _emailController.text.trim();
    if (email.isEmpty) return;
    await ref.read(requestAccountUnlockProvider.notifier).request(email);
    if (mounted) setState(() => _submitted = true);
  }
}
