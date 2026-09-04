import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../state/auth_providers.dart';
import '../theme/party_theme.dart';
import '../widgets/party_hero.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Signup-Screen, mirroring `LoginScreen`'s Aufbau.
class SignupScreen extends ConsumerStatefulWidget {
  const SignupScreen({super.key});

  @override
  ConsumerState<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends ConsumerState<SignupScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _displayNameController = TextEditingController();
  bool _obscure = true;
  String? _clientError;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _displayNameController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);
    final colors = PartyColors.fromThemeJson(null);
    final isLoading = authState.isLoading;
    final error = authState.hasError ? authState.error : null;
    final isDuplicateEmail = error is ApiException && error.statusCode == 409;

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
                    title: '🎉 Party App',
                    subtitle: 'Create your account',
                    colors: colors,
                  ),
                  const SizedBox(height: 24),
                  TextField(
                    controller: _displayNameController,
                    autofocus: true,
                    decoration: const InputDecoration(
                      labelText: 'Display name',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      labelText: 'Email',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  if (isDuplicateEmail) ...[
                    const SizedBox(height: 8),
                    Text(
                      'An account with this email already exists.',
                      style: TextStyle(color: Theme.of(context).colorScheme.error),
                    ),
                  ],
                  const SizedBox(height: 12),
                  TextField(
                    controller: _passwordController,
                    obscureText: _obscure,
                    decoration: InputDecoration(
                      labelText: 'Password',
                      border: const OutlineInputBorder(),
                      suffixIcon: IconButton(
                        icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                        onPressed: () => setState(() => _obscure = !_obscure),
                      ),
                    ),
                    onSubmitted: (_) => _submit(),
                  ),
                  if (_clientError != null) ...[
                    const SizedBox(height: 12),
                    Text(
                      _clientError!,
                      style: TextStyle(color: Theme.of(context).colorScheme.error),
                      textAlign: TextAlign.center,
                    ),
                  ] else if (error != null && !isDuplicateEmail) ...[
                    const SizedBox(height: 12),
                    Text(
                      'Signup failed. Please try again.',
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
                          : const Text('Sign up'),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextButton(
                    onPressed: () => ref.read(showSignupProvider.notifier).state = false,
                    child: const Text('Already have an account? Log in'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _submit() {
    final email = _emailController.text.trim();
    final password = _passwordController.text;
    final displayName = _displayNameController.text.trim();
    setState(() {
      if (displayName.isEmpty) {
        _clientError = 'Please enter a display name.';
      } else if (email.isEmpty) {
        _clientError = 'Please enter an email address.';
      } else if (password.length < 8) {
        _clientError = 'Password must be at least 8 characters.';
      } else {
        _clientError = null;
      }
    });
    if (_clientError != null) return;
    ref.read(authProvider.notifier).signup(email: email, password: password, displayName: displayName);
  }
}
