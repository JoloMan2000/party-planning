import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/api_config.dart';
import '../state/auth_providers.dart';
import '../theme/party_theme.dart';
import '../widgets/party_hero.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Login-Screen - neuer App-Einstiegspunkt für den Account-basierten Flow
/// (ersetzt Intro/Language/Wizard, siehe `main.dart`-Routing).
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _obscure = true;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);
    final colors = PartyColors.fromThemeJson(null);
    final isLoading = authState.isLoading;
    final error = authState.hasError ? authState.error : null;
    final isInvalidCredentials = error is ApiException && error.statusCode == 401;

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
                    subtitle: 'Log in to see your parties',
                    colors: colors,
                  ),
                  const SizedBox(height: 24),
                  TextField(
                    controller: _emailController,
                    autofocus: true,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      labelText: 'Email',
                      border: OutlineInputBorder(),
                    ),
                  ),
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
                  if (isInvalidCredentials) ...[
                    const SizedBox(height: 12),
                    Text(
                      'Email or password incorrect.',
                      style: TextStyle(color: Theme.of(context).colorScheme.error),
                      textAlign: TextAlign.center,
                    ),
                  ] else if (error != null) ...[
                    const SizedBox(height: 12),
                    Text(
                      'Login failed. Please try again.',
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
                          : const Text('Log in'),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextButton(
                    onPressed: () => ref.read(showSignupProvider.notifier).state = true,
                    child: const Text("Don't have an account? Sign up"),
                  ),
                  const SizedBox(height: 4),
                  TextButton(
                    onPressed: () => _showServerOverrideDialog(context),
                    child: const Text('Server settings', style: TextStyle(fontSize: 12)),
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
    if (email.isEmpty || password.isEmpty) return;
    ref.read(authProvider.notifier).login(email: email, password: password);
  }

  Future<void> _showServerOverrideDialog(BuildContext context) async {
    final controller = TextEditingController(text: ApiConfig.baseUrl);
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Server URL'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(hintText: 'http://192.168.1.10:8000'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(controller.text.trim()),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (result != null && result.isNotEmpty) {
      ApiConfig.override(result);
    }
  }
}
