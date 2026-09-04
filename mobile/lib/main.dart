import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'screens/admin_dashboard_screen.dart';
import 'screens/admin_login_screen.dart';
import 'screens/create_party_screen.dart';
import 'screens/invitation_detail_screen.dart';
import 'screens/login_screen.dart';
import 'screens/party_detail_screen.dart';
import 'screens/party_list_screen.dart';
import 'screens/signup_screen.dart';
import 'state/admin_providers.dart';
import 'state/auth_providers.dart';
import 'theme/party_theme.dart';

void main() {
  runApp(const ProviderScope(child: PartyApp()));
}

/// Root-Widget: routet zwischen Login/Signup -> Party-Liste -> Detail-
/// Screens (Account-basierter Flow, Phase 3). Der alte anonyme Gast-Wizard
/// (`IntroScreen`/`LanguageScreen`/`WizardScreen`) bleibt im Code erhalten,
/// ist aber ab hier nicht mehr erreichbar (siehe Plan-Entscheidung #1+#3) -
/// `adminMode` bleibt als Zweig bestehen, da nichts diese Route mehr aktiv
/// erreicht, aber der Admin-Dashboard-Code unverändert bleiben soll.
class PartyApp extends ConsumerWidget {
  const PartyApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final adminMode = ref.watch(adminModeProvider);
    final adminAuth = ref.watch(adminAuthProvider);
    final colors = PartyColors.fromThemeJson(null);

    Widget home;
    if (adminMode) {
      final token = adminAuth.asData?.value;
      home = token == null ? const AdminLoginScreen() : const AdminDashboardScreen();
    } else {
      final tokens = ref.watch(authProvider).asData?.value;
      final showSignup = ref.watch(showSignupProvider);
      final selectedPartyId = ref.watch(selectedPartyIdProvider);
      final selectedInvitationId = ref.watch(selectedInvitationIdProvider);
      final creatingParty = ref.watch(creatingPartyProvider);

      if (tokens == null) {
        home = showSignup ? const SignupScreen() : const LoginScreen();
      } else if (selectedPartyId != null) {
        home = PartyDetailScreen(partyId: selectedPartyId);
      } else if (selectedInvitationId != null) {
        home = InvitationDetailScreen(invitationId: selectedInvitationId);
      } else if (creatingParty) {
        home = const CreatePartyScreen();
      } else {
        home = const PartyListScreen();
      }
    }

    return MaterialApp(
      title: 'Party Planning',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(colors),
      home: home,
    );
  }
}
