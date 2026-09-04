import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../api/api_client.dart';
import '../models/invitation.dart';
import '../models/party.dart';
import '../models/party_guests_response.dart';
import '../models/rsvp_response.dart';
import '../models/user_account.dart';
import 'providers.dart';

const _accessTokenKey = 'user_access_token';
const _refreshTokenKey = 'user_refresh_token';

/// Access-/Refresh-Token-Paar für den eingeloggten Nutzer (Phase 3, getrennt
/// vom Admin-Token in `admin_providers.dart` - eigene Storage-Keys, eigene
/// Provider-Instanz, kein gemeinsamer Zustand mit dem unangetasteten
/// Admin-Passwort-Flow).
class TokenPair {
  final String accessToken;
  final String refreshToken;

  const TokenPair(this.accessToken, this.refreshToken);
}

final _secureStorageProvider = Provider<FlutterSecureStorage>((ref) {
  return const FlutterSecureStorage();
});

/// Aktuelles User-Token-Paar (`null` = nicht eingeloggt). Wird beim App-
/// Start aus dem sicheren Speicher geladen, mirroring `AdminAuthNotifier`.
class AuthNotifier extends AsyncNotifier<TokenPair?> {
  @override
  Future<TokenPair?> build() async {
    final storage = ref.read(_secureStorageProvider);
    final access = await storage.read(key: _accessTokenKey);
    final refresh = await storage.read(key: _refreshTokenKey);
    if (access == null || refresh == null) return null;
    return TokenPair(access, refresh);
  }

  Future<void> _persist(TokenPair pair) async {
    final storage = ref.read(_secureStorageProvider);
    await storage.write(key: _accessTokenKey, value: pair.accessToken);
    await storage.write(key: _refreshTokenKey, value: pair.refreshToken);
  }

  Future<void> signup({required String email, required String password, required String displayName}) async {
    state = const AsyncLoading();
    try {
      final response = await ref
          .read(apiClientProvider)
          .signup(email: email, password: password, displayName: displayName);
      final pair = TokenPair(response.accessToken, response.refreshToken);
      await _persist(pair);
      state = AsyncData(pair);
    } on ApiException catch (e) {
      state = AsyncError(e, StackTrace.current);
    }
  }

  Future<void> login({required String email, required String password}) async {
    state = const AsyncLoading();
    try {
      final response = await ref.read(apiClientProvider).login(email: email, password: password);
      final pair = TokenPair(response.accessToken, response.refreshToken);
      await _persist(pair);
      state = AsyncData(pair);
    } on ApiException catch (e) {
      state = AsyncError(e, StackTrace.current);
    }
  }

  Future<void> logout() async {
    final pair = state.value;
    if (pair != null) {
      // Best-effort: Logout soll lokal immer gelingen, auch wenn der
      // Netzwerk-Call fehlschlägt (Ziel ist, den lokalen Zustand zu leeren).
      try {
        await ref.read(apiClientProvider).logout(pair.refreshToken);
      } catch (_) {
        // ignorieren - lokaler Logout läuft unabhängig davon weiter
      }
    }
    final storage = ref.read(_secureStorageProvider);
    await storage.delete(key: _accessTokenKey);
    await storage.delete(key: _refreshTokenKey);
    state = const AsyncData(null);
    ref.invalidate(currentUserProvider);
  }

  /// `onRefresh`-Callback für `ApiClient._authorizedRequest`. Liest das
  /// Refresh-Token aus dem aktuellen State (nicht direkt aus dem Storage, um
  /// ein Race gegen einen parallelen Rotations-Aufruf zu vermeiden), rotiert
  /// bei Erfolg das Token-Paar (persistiert + aktualisiert `state`), und
  /// erzwingt bei einem gescheiterten Refresh (401 - ungültig/widerrufen/
  /// wiederverwendet, siehe Backend-Reuse-Detection) einen lokalen Logout.
  Future<String?> refreshAndPersist() async {
    final current = state.value;
    if (current == null) return null;
    try {
      final response = await ref.read(apiClientProvider).refreshTokens(current.refreshToken);
      final pair = TokenPair(response.accessToken, response.refreshToken);
      await _persist(pair);
      state = AsyncData(pair);
      return pair.accessToken;
    } on ApiException {
      final storage = ref.read(_secureStorageProvider);
      await storage.delete(key: _accessTokenKey);
      await storage.delete(key: _refreshTokenKey);
      state = const AsyncData(null);
      return null;
    }
  }
}

final authProvider = AsyncNotifierProvider<AuthNotifier, TokenPair?>(AuthNotifier.new);

/// Aktuelles Access-Token als Nicht-Nullable-Wert - nur innerhalb des
/// eingeloggten Bereichs verwendet, wo `main.dart`'s Routing einen gültigen
/// Token bereits garantiert (mirroring `_requiredAdminTokenProvider`).
final _requiredAccessTokenProvider = Provider<String>((ref) {
  final pair = ref.watch(authProvider).value;
  if (pair == null) {
    throw StateError('Account-Home ohne gültiges Token gerendert.');
  }
  return pair.accessToken;
});

Future<String?> Function() _onRefresh(Ref ref) => () => ref.read(authProvider.notifier).refreshAndPersist();

final currentUserProvider = FutureProvider<UserAccount>((ref) {
  final token = ref.watch(_requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getMe(token, _onRefresh(ref));
});

final myPartiesProvider = FutureProvider<List<Party>>((ref) {
  final token = ref.watch(_requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getMyParties(token, _onRefresh(ref));
});

final myInvitationsProvider = FutureProvider<List<Invitation>>((ref) {
  final token = ref.watch(_requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getMyInvitations(token, _onRefresh(ref));
});

final partyDetailProvider = FutureProvider.family<Party, String>((ref, partyId) {
  final token = ref.watch(_requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getParty(token, _onRefresh(ref), partyId);
});

/// 403 (Gast ohne Host-/Co-Host-Rolle) wird von `PartyDetailScreen` selbst
/// abgefangen, um zwischen Gast- und Host-Ansicht zu unterscheiden - siehe
/// dortiger `AsyncValue`-Handling-Code, nicht hier verschluckt.
final partyGuestsProvider = FutureProvider.family<PartyGuestsResponse, String>((ref, partyId) {
  final token = ref.watch(_requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getPartyGuests(token, _onRefresh(ref), partyId);
});

/// Ruft `GET /invitations/{id}` ab - markiert serverseitig `viewed_at` als
/// Nebeneffekt, wenn der Betrachter der eingeladene User ist (kein
/// zusätzlicher Client-Code nötig, siehe `invitations.py::get_invitation`).
final invitationDetailProvider = FutureProvider.family<Invitation, String>((ref, invitationId) {
  final token = ref.watch(_requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getInvitation(token, _onRefresh(ref), invitationId);
});

/// Party-Erstellung als einmalige Aktion (mirroring `MusicPlaylistNotifier`/
/// `ShoppingListNotifier`: `build()` liefert `null`, die Aktion setzt
/// `AsyncLoading` dann `AsyncData`/`AsyncError`).
class CreatePartyNotifier extends AsyncNotifier<Party?> {
  @override
  Future<Party?> build() async => null;

  Future<Party> create({
    required String name,
    String description = '',
    DateTime? startsAt,
    String location = '',
  }) async {
    final token = ref.read(_requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      final party = await ref.read(apiClientProvider).createParty(
            token,
            _onRefresh(ref),
            name: name,
            description: description,
            startsAt: startsAt,
            location: location,
          );
      state = AsyncData(party);
      ref.invalidate(myPartiesProvider);
      return party;
    } on ApiException catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final createPartyProvider = AsyncNotifierProvider<CreatePartyNotifier, Party?>(CreatePartyNotifier.new);

/// Gast-per-E-Mail-Einladen als einmalige Aktion.
class InviteGuestNotifier extends AsyncNotifier<Invitation?> {
  @override
  Future<Invitation?> build() async => null;

  Future<Invitation> invite(String partyId, {required String invitedUserEmail, String invitationMessage = ''}) async {
    final token = ref.read(_requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      final invitation = await ref.read(apiClientProvider).inviteGuest(
            token,
            _onRefresh(ref),
            partyId,
            invitedUserEmail: invitedUserEmail,
            invitationMessage: invitationMessage,
          );
      state = AsyncData(invitation);
      ref.invalidate(partyGuestsProvider(partyId));
      return invitation;
    } on ApiException catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final inviteGuestProvider = AsyncNotifierProvider<InviteGuestNotifier, Invitation?>(InviteGuestNotifier.new);

/// RSVP-Antwort als einmalige Aktion. Lädt nach Erfolg `invitationDetailProvider`
/// + `myInvitationsProvider` neu (Re-Fetch statt optimistisches UI, siehe
/// Phase-3-Plan: die servergeführte `version` muss für den nächsten Versuch
/// stimmen, ein lokal geratener Wert würde nur unnötige 409s produzieren).
class RsvpNotifier extends AsyncNotifier<RsvpResponse?> {
  @override
  Future<RsvpResponse?> build() async => null;

  Future<RsvpResponse> respond(
    String invitationId, {
    required String status,
    required int version,
    String? clientRequestId,
  }) async {
    final token = ref.read(_requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      final result = await ref.read(apiClientProvider).rsvp(
            token,
            _onRefresh(ref),
            invitationId,
            status: status,
            version: version,
            clientRequestId: clientRequestId,
          );
      state = AsyncData(result);
      ref.invalidate(invitationDetailProvider(invitationId));
      ref.invalidate(myInvitationsProvider);
      return result;
    } on ApiException catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final rsvpProvider = AsyncNotifierProvider<RsvpNotifier, RsvpResponse?>(RsvpNotifier.new);

// ---------------------------------------------------------------------
// Navigations-Zustand - reine `StateProvider`s statt eines Routing-Pakets,
// mirroring den bestehenden `adminModeProvider`/`enteredIntroProvider`-Stil
// (kein `Navigator`/`go_router` irgendwo in dieser Codebase).
// ---------------------------------------------------------------------

final showSignupProvider = StateProvider<bool>((ref) => false);
final selectedPartyIdProvider = StateProvider<String?>((ref) => null);
final selectedInvitationIdProvider = StateProvider<String?>((ref) => null);
final creatingPartyProvider = StateProvider<bool>((ref) => false);
