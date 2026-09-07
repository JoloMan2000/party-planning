import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../api/api_client.dart';
import '../models/app_notification.dart';
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
    } catch (e) {
      // Bewusst nicht nur `on ApiException` - ein nicht erreichbarer Server
      // (z.B. Backend nicht gestartet) wirft eine `SocketException`/
      // `ClientException`, keine `ApiException`. Ohne diesen breiteren Catch
      // bliebe der State für immer bei `AsyncLoading` hängen (Spinner dreht
      // endlos), statt dem Nutzer einen Fehler anzuzeigen.
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
    } catch (e) {
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
/// Token bereits garantiert. Öffentlich, damit `admin_providers.dart` (seit
/// Phase 4 party-gescoped, kein eigener Admin-Token mehr) denselben
/// Account-Token mitbenutzen kann.
final requiredAccessTokenProvider = Provider<String>((ref) {
  final pair = ref.watch(authProvider).value;
  if (pair == null) {
    throw StateError('Account-Home ohne gültiges Token gerendert.');
  }
  return pair.accessToken;
});

/// `onRefresh`-Callback für `ApiClient._authorizedRequest` - öffentlich, damit
/// `admin_providers.dart` denselben Account-Token-Refresh-Flow mitbenutzen
/// kann (kein separater Admin-Token-Refresh mehr seit Phase 4).
Future<String?> Function() onRefresh(Ref ref) => () => ref.read(authProvider.notifier).refreshAndPersist();

final currentUserProvider = FutureProvider<UserAccount>((ref) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getMe(token, onRefresh(ref));
});

final myPartiesProvider = FutureProvider<List<Party>>((ref) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getMyParties(token, onRefresh(ref));
});

final myInvitationsProvider = FutureProvider<List<Invitation>>((ref) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getMyInvitations(token, onRefresh(ref));
});

final partyDetailProvider = FutureProvider.family<Party, String>((ref, partyId) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getParty(token, onRefresh(ref), partyId);
});

/// 403 (Gast ohne Host-/Co-Host-Rolle) wird von `PartyDetailScreen` selbst
/// abgefangen, um zwischen Gast- und Host-Ansicht zu unterscheiden - siehe
/// dortiger `AsyncValue`-Handling-Code, nicht hier verschluckt.
final partyGuestsProvider = FutureProvider.family<PartyGuestsResponse, String>((ref, partyId) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getPartyGuests(token, onRefresh(ref), partyId);
});

/// Ruft `GET /invitations/{id}` ab - markiert serverseitig `viewed_at` als
/// Nebeneffekt, wenn der Betrachter der eingeladene User ist (kein
/// zusätzlicher Client-Code nötig, siehe `invitations.py::get_invitation`).
final invitationDetailProvider = FutureProvider.family<Invitation, String>((ref, invitationId) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getInvitation(token, onRefresh(ref), invitationId);
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
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      final party = await ref.read(apiClientProvider).createParty(
            token,
            onRefresh(ref),
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
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      final invitation = await ref.read(apiClientProvider).inviteGuest(
            token,
            onRefresh(ref),
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
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      final result = await ref.read(apiClientProvider).rsvp(
            token,
            onRefresh(ref),
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

/// Party-Bearbeiten als einmalige Aktion (mirroring `CreatePartyNotifier`) -
/// speichert nur die geänderten Felder (`PartyUpdate.model_dump(exclude_unset)`
/// serverseitig), lädt danach `partyDetailProvider` neu.
class UpdatePartyNotifier extends AsyncNotifier<Party?> {
  @override
  Future<Party?> build() async => null;

  Future<Party> save(
    String partyId, {
    String? name,
    String? description,
    DateTime? startsAt,
    String? location,
  }) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      final party = await ref.read(apiClientProvider).updateParty(
            token,
            onRefresh(ref),
            partyId,
            name: name,
            description: description,
            startsAt: startsAt,
            location: location,
          );
      state = AsyncData(party);
      ref.invalidate(partyDetailProvider(partyId));
      return party;
    } on ApiException catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final updatePartyProvider = AsyncNotifierProvider<UpdatePartyNotifier, Party?>(UpdatePartyNotifier.new);

/// Profilbild-Upload als einmalige Aktion (lokales Disk-Storage auf dem
/// Server, siehe Phase-5-Plan Teil D) - lädt `currentUserProvider` danach neu,
/// damit der neue `profile_image`-Pfad überall sichtbar wird, wo er
/// dargestellt wird.
class UploadProfileImageNotifier extends AsyncNotifier<UserAccount?> {
  @override
  Future<UserAccount?> build() async => null;

  Future<void> upload(File imageFile) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      final user = await ref.read(apiClientProvider).uploadProfileImage(token, onRefresh(ref), imageFile);
      state = AsyncData(user);
      ref.invalidate(currentUserProvider);
    } on ApiException catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final uploadProfileImageProvider =
    AsyncNotifierProvider<UploadProfileImageNotifier, UserAccount?>(UploadProfileImageNotifier.new);

// ---------------------------------------------------------------------
// Navigations-Zustand - reine `StateProvider`s statt eines Routing-Pakets,
// mirroring den bestehenden `adminModeProvider`/`enteredIntroProvider`-Stil
// (kein `Navigator`/`go_router` irgendwo in dieser Codebase).
// ---------------------------------------------------------------------

final showSignupProvider = StateProvider<bool>((ref) => false);
final selectedPartyIdProvider = StateProvider<String?>((ref) => null);
final selectedInvitationIdProvider = StateProvider<String?>((ref) => null);
final creatingPartyProvider = StateProvider<bool>((ref) => false);

/// Party-ID, für die das Admin-Dashboard geöffnet wurde (`null` = geschlossen).
/// Ersetzt seit Phase 4 den alten `adminModeProvider` - "Verwalten" auf
/// `PartyDetailScreen` setzt diesen Provider, statt in einen globalen
/// Admin-Modus zu wechseln.
final selectedAdminPartyIdProvider = StateProvider<String?>((ref) => null);

/// Party-ID, die gerade im `EditPartyScreen` bearbeitet wird (`null` =
/// geschlossen), gesetzt via Edit-Button auf `PartyDetailScreen`.
final editingPartyIdProvider = StateProvider<String?>((ref) => null);

// ---------------------------------------------------------------------
// In-App-Notification-Inbox (Phase 5) - Poll-basiert statt echtem Push
// (FCM/APNs), mirroring das Backend-seitige TODO in
// `backend/app/routers/notifications.py`. Der periodische Poll-Timer selbst
// lebt in `main.dart`'s `PartyApp` (`ConsumerStatefulWidget`), nicht hier -
// dieser Provider liefert nur den aktuellen Snapshot je Aufruf/Invalidate.
// ---------------------------------------------------------------------

/// `true` = `NotificationsScreen` ist geöffnet (via Glocken-Icon auf
/// `PartyListScreen`), mirroring den übrigen `StateProvider`-Navigationsstil.
final showNotificationsProvider = StateProvider<bool>((ref) => false);

final notificationsProvider = FutureProvider<List<AppNotification>>((ref) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getNotifications(token, onRefresh(ref));
});

/// "Als gelesen markieren" als einmalige Aktion, lädt `notificationsProvider`
/// danach neu (mirroring `InviteGuestNotifier`).
class MarkNotificationReadNotifier extends AsyncNotifier<AppNotification?> {
  @override
  Future<AppNotification?> build() async => null;

  Future<void> markRead(String notificationId) async {
    final token = ref.read(requiredAccessTokenProvider);
    final notification = await ref.read(apiClientProvider).markNotificationRead(
          token,
          onRefresh(ref),
          notificationId,
        );
    state = AsyncData(notification);
    ref.invalidate(notificationsProvider);
  }
}

final markNotificationReadProvider =
    AsyncNotifierProvider<MarkNotificationReadNotifier, AppNotification?>(MarkNotificationReadNotifier.new);
