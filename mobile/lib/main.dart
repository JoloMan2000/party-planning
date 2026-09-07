import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'screens/admin_dashboard_screen.dart';
import 'screens/create_party_screen.dart';
import 'screens/edit_party_screen.dart';
import 'screens/forgot_password_screen.dart';
import 'screens/home_shell.dart';
import 'screens/invitation_detail_screen.dart';
import 'screens/login_screen.dart';
import 'screens/notifications_screen.dart';
import 'screens/party_detail_screen.dart';
import 'screens/reset_password_screen.dart';
import 'screens/signup_screen.dart';
import 'state/auth_providers.dart';
import 'theme/party_theme.dart';

void main() {
  runApp(const ProviderScope(child: PartyApp()));
}

/// Root-Widget: routet zwischen Login/Signup -> Party-Liste -> Detail-
/// Screens (Account-basierter Flow, Phase 3). Seit Phase 4 party-gescoptes
/// Admin-Dashboard über `selectedAdminPartyIdProvider` (gesetzt via
/// "Verwalten"-Button auf `PartyDetailScreen`) statt des alten globalen
/// Admin-Passwort-Modus. Seit Phase 5 `ConsumerStatefulWidget`, da hier zwei
/// Dinge mit eigenem Lifecycle verwaltet werden: der `app_links`-Stream für
/// Deep Links (`partyplanning://...`) und ein `Timer.periodic` zum Pollen der
/// In-App-Notifications (kein echter Push, siehe Backend-TODO in
/// `backend/app/routers/notifications.py`).
class PartyApp extends ConsumerStatefulWidget {
  const PartyApp({super.key});

  @override
  ConsumerState<PartyApp> createState() => _PartyAppState();
}

class _PartyAppState extends ConsumerState<PartyApp> {
  StreamSubscription<Uri>? _linkSubscription;
  Timer? _notificationPollTimer;

  @override
  void initState() {
    super.initState();
    _initDeepLinks();
    _notificationPollTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (ref.read(authProvider).asData?.value != null) {
        ref.invalidate(notificationsProvider);
      }
    });
  }

  Future<void> _initDeepLinks() async {
    final appLinks = AppLinks();
    try {
      final initialUri = await appLinks.getInitialLink();
      if (initialUri != null) _handleDeepLink(initialUri);
    } catch (_) {
      // Kein initialer Link oder Plattform-Fehler - ignorieren, App startet
      // normal ohne Deep-Link-Ziel.
    }
    _linkSubscription = appLinks.uriLinkStream.listen(_handleDeepLink);
  }

  /// Parst `partyplanning://invite/{invitationId}` und
  /// `partyplanning://party/{partyId}` in die bestehenden Navigations-
  /// `StateProvider`s - kein Routentabelle nötig, mirroring das übrige
  /// ad-hoc Navigationsmodell dieser App.
  void _handleDeepLink(Uri uri) {
    if (uri.scheme != 'partyplanning') return;
    final segments = uri.pathSegments.isNotEmpty
        ? uri.pathSegments
        : [uri.host, ...uri.pathSegments];
    if (segments.length < 2) return;
    final kind = segments[0];
    final id = segments[1];
    if (id.isEmpty) return;
    if (kind == 'invite') {
      ref.read(selectedInvitationIdProvider.notifier).state = id;
    } else if (kind == 'party') {
      ref.read(selectedPartyIdProvider.notifier).state = id;
    } else if (kind == 'reset') {
      ref.read(passwordResetTokenProvider.notifier).state = id;
    }
  }

  @override
  void dispose() {
    _linkSubscription?.cancel();
    _notificationPollTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final selectedAdminPartyId = ref.watch(selectedAdminPartyIdProvider);
    final colors = PartyColors.fromThemeJson(null);

    final editingPartyId = ref.watch(editingPartyIdProvider);

    Widget home;
    if (selectedAdminPartyId != null) {
      home = AdminDashboardScreen(partyId: selectedAdminPartyId);
    } else if (editingPartyId != null) {
      home = EditPartyScreen(partyId: editingPartyId);
    } else {
      final tokens = ref.watch(authProvider).asData?.value;
      final showSignup = ref.watch(showSignupProvider);
      final showForgotPassword = ref.watch(showForgotPasswordProvider);
      final resetToken = ref.watch(passwordResetTokenProvider);
      final showNotifications = ref.watch(showNotificationsProvider);
      final selectedPartyId = ref.watch(selectedPartyIdProvider);
      final selectedInvitationId = ref.watch(selectedInvitationIdProvider);
      final creatingParty = ref.watch(creatingPartyProvider);

      if (resetToken != null) {
        // Vor `tokens == null` geprüft - ein Reset-Link kann ankommen,
        // während auf diesem Gerät noch ein anderer User eingeloggt ist.
        home = ResetPasswordScreen(token: resetToken);
      } else if (tokens == null) {
        home = showForgotPassword
            ? const ForgotPasswordScreen()
            : (showSignup ? const SignupScreen() : const LoginScreen());
      } else if (showNotifications) {
        home = const NotificationsScreen();
      } else if (selectedPartyId != null) {
        home = PartyDetailScreen(partyId: selectedPartyId);
      } else if (selectedInvitationId != null) {
        home = InvitationDetailScreen(invitationId: selectedInvitationId);
      } else if (creatingParty) {
        home = const CreatePartyScreen();
      } else {
        home = const HomeShell();
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
