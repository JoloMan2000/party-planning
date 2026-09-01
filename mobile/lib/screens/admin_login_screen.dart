import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/admin_providers.dart';
import '../state/providers.dart';
import '../theme/party_theme.dart';
import '../widgets/party_hero.dart';

/// Admin-Login (ersetzt den `?admin=<ADMIN_TOKEN>`-Query-Param-Check aus
/// `"Party Planning.py"` durch ein Passwortformular gegen
/// `POST /api/v1/auth/admin/login`, siehe Plan Schritt 4).
class AdminLoginScreen extends ConsumerStatefulWidget {
  const AdminLoginScreen({super.key});

  @override
  ConsumerState<AdminLoginScreen> createState() => _AdminLoginScreenState();
}

class _AdminLoginScreenState extends ConsumerState<AdminLoginScreen> {
  final _passwordController = TextEditingController();
  bool _obscure = true;

  @override
  void dispose() {
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(adminAuthProvider);
    final partyInfoAsync = ref.watch(partyInfoProvider('de'));
    final colors = partyInfoAsync.maybeWhen(
      data: (info) => PartyColors.fromThemeJson(info.theme),
      orElse: () => PartyColors.fromThemeJson(null),
    );
    final isLoading = authState.isLoading;
    final error = authState.hasError ? authState.error : null;

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
                    title: '🔐 Admin',
                    subtitle: 'Zugang zum Party-Dashboard',
                    colors: colors,
                  ),
                  const SizedBox(height: 24),
                  TextField(
                    controller: _passwordController,
                    obscureText: _obscure,
                    autofocus: true,
                    decoration: InputDecoration(
                      labelText: 'Passwort',
                      border: const OutlineInputBorder(),
                      suffixIcon: IconButton(
                        icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                        onPressed: () => setState(() => _obscure = !_obscure),
                      ),
                    ),
                    onSubmitted: (_) => _submit(),
                  ),
                  if (error != null) ...[
                    const SizedBox(height: 12),
                    Text(
                      'Login fehlgeschlagen: Passwort prüfen.',
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
                          : const Text('Einloggen'),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextButton(
                    onPressed: () => ref.read(adminModeProvider.notifier).state = false,
                    child: const Text('Zurück'),
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
    final password = _passwordController.text;
    if (password.isEmpty) return;
    ref.read(adminAuthProvider.notifier).login(password);
  }
}
