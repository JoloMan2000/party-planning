import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../state/auth_providers.dart';
import '../theme/party_theme.dart';
import '../widgets/party_hero.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Zweiter Schritt des Forgot-Password-Flows - erreicht via
/// `partyplanning://reset/{token}`-Deep-Link (`main.dart::_handleDeepLink`).
/// Nimmt den rohen `token`-String (Format `{token_id}:{raw_token}`) entgegen
/// und reicht ihn unverändert an `POST /auth/reset-password` durch.
class ResetPasswordScreen extends ConsumerStatefulWidget {
  final String token;

  const ResetPasswordScreen({super.key, required this.token});

  @override
  ConsumerState<ResetPasswordScreen> createState() => _ResetPasswordScreenState();
}

class _ResetPasswordScreenState extends ConsumerState<ResetPasswordScreen> {
  final _newPasswordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  bool _obscure = true;
  bool _success = false;
  String? _mismatchError;

  @override
  void dispose() {
    _newPasswordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final resetState = ref.watch(resetPasswordProvider);
    final colors = PartyColors.fromThemeJson(null);
    final isLoading = resetState.isLoading;
    final error = resetState.hasError ? resetState.error : null;

    String? errorText;
    if (_mismatchError != null) {
      errorText = _mismatchError;
    } else if (error is ApiException && error.statusCode == 400) {
      errorText = error.detail is String ? error.detail as String : 'Invalid or expired reset link.';
    } else if (error != null) {
      errorText = 'Something went wrong. Please try again.';
    }

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
                    title: '🔑 Choose a new password',
                    subtitle: 'Enter and confirm your new password',
                    colors: colors,
                  ),
                  const SizedBox(height: 24),
                  if (_success) ...[
                    const Icon(Icons.check_circle_outline, size: 48),
                    const SizedBox(height: 12),
                    const Text(
                      'Your password has been reset. Please log in with your new password.',
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 20),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: () => ref.read(passwordResetTokenProvider.notifier).state = null,
                        child: const Text('Back to login'),
                      ),
                    ),
                  ] else ...[
                    TextField(
                      controller: _newPasswordController,
                      autofocus: true,
                      obscureText: _obscure,
                      decoration: InputDecoration(
                        labelText: 'New password',
                        border: const OutlineInputBorder(),
                        suffixIcon: IconButton(
                          icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                          onPressed: () => setState(() => _obscure = !_obscure),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _confirmPasswordController,
                      obscureText: _obscure,
                      decoration: const InputDecoration(
                        labelText: 'Confirm new password',
                        border: OutlineInputBorder(),
                      ),
                      onSubmitted: (_) => _submit(),
                    ),
                    if (errorText != null) ...[
                      const SizedBox(height: 12),
                      Text(
                        errorText,
                        style: TextStyle(color: Theme.of(context).colorScheme.error),
                        textAlign: TextAlign.center,
                      ),
                    ],
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
                            : const Text('Reset password'),
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  TextButton(
                    onPressed: () => ref.read(passwordResetTokenProvider.notifier).state = null,
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
    final newPassword = _newPasswordController.text;
    final confirmPassword = _confirmPasswordController.text;
    if (newPassword.isEmpty || confirmPassword.isEmpty) return;
    if (newPassword != confirmPassword) {
      setState(() => _mismatchError = 'Passwords do not match.');
      return;
    }
    setState(() => _mismatchError = null);
    await ref.read(resetPasswordProvider.notifier).reset(widget.token, newPassword);
    final state = ref.read(resetPasswordProvider);
    if (mounted && !state.hasError) {
      setState(() => _success = true);
    }
  }
}
