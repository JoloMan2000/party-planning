import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../api/api_client.dart';
import '../models/app_notification.dart';
import '../models/discover_action_result.dart';
import '../models/discover_card.dart';
import '../models/discovery_catalog_item.dart';
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
    try {
      final access = await storage.read(key: _accessTokenKey);
      final refresh = await storage.read(key: _refreshTokenKey);
      if (access == null || refresh == null) return null;
      return TokenPair(access, refresh);
    } catch (_) {
      // Ein beschädigter Keychain-/Keystore-Eintrag (z.B. nach einem
      // Geräte-Restore/Reinstall mit verwaisten Schlüsseln - ein bekanntes
      // `flutter_secure_storage`-Fehlerbild) würde hier sonst ungefangen
      // durchschlagen. Statt dessen die kaputten Einträge löschen und den
      // Nutzer wie "nicht eingeloggt" behandeln, damit er sich einfach neu
      // einloggen kann statt dauerhaft auf dem Login-Screen festzuhängen.
      await storage.delete(key: _accessTokenKey);
      await storage.delete(key: _refreshTokenKey);
      return null;
    }
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

  /// In-flight Refresh-Future, damit mehrere gleichzeitig ablaufende Requests
  /// (z.B. beim Home-Load: `getMe`+`getMyParties`+`getMyInvitations` fast
  /// zeitgleich) nicht jeweils ihren eigenen `/auth/refresh`-Call auslösen.
  /// Da Refresh-Tokens serverseitig rotiert/single-use sind, würde der
  /// zweite Aufruf mit dem bereits verbrauchten alten Token sonst 401
  /// zurückbekommen und fälschlich einen kompletten Logout auslösen, obwohl
  /// die Session eigentlich gültig war.
  Future<String?>? _refreshInFlight;

  /// `onRefresh`-Callback für `ApiClient._authorizedRequest`. Bündelt
  /// gleichzeitige Aufrufe auf ein einziges In-Flight-Future (s.o.), rotiert
  /// bei Erfolg das Token-Paar (persistiert + aktualisiert `state`), und
  /// erzwingt bei einem gescheiterten Refresh (401 - ungültig/widerrufen/
  /// wiederverwendet, siehe Backend-Reuse-Detection) einen lokalen Logout.
  Future<String?> refreshAndPersist() {
    return _refreshInFlight ??= _doRefresh().whenComplete(() => _refreshInFlight = null);
  }

  Future<String?> _doRefresh() async {
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
    } catch (e) {
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
    } catch (e) {
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
    } catch (e) {
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
    } catch (e) {
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
    } catch (e) {
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
final showForgotPasswordProvider = StateProvider<bool>((ref) => false);
/// Gesetzt vom `partyplanning://reset/{token}`-Deep-Link-Handler in
/// `main.dart` - `null` = kein Reset-Flow aktiv.
final passwordResetTokenProvider = StateProvider<String?>((ref) => null);
/// Gesetzt vom `partyplanning://verify/{token}`-Deep-Link-Handler in
/// `main.dart` - `null` = kein Verify-Flow aktiv.
final emailVerificationTokenProvider = StateProvider<String?>((ref) => null);
/// Gesetzt vom `partyplanning://unlock/{token}`-Deep-Link-Handler in
/// `main.dart` - `null` = kein Unlock-Flow aktiv.
final accountUnlockTokenProvider = StateProvider<String?>((ref) => null);
final showAccountUnlockRequestProvider = StateProvider<bool>((ref) => false);
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
    try {
      final notification = await ref.read(apiClientProvider).markNotificationRead(
            token,
            onRefresh(ref),
            notificationId,
          );
      state = AsyncData(notification);
      ref.invalidate(notificationsProvider);
    } catch (e) {
      // Bewusst kein `rethrow` - der einzige Aufrufer (`NotificationsScreen.
      // _handleTap`) navigiert danach unabhängig weiter und hat kein
      // Error-Handling; ein fehlgeschlagenes "als gelesen markieren" soll
      // diese Navigation nicht blockieren/abstürzen lassen.
      state = AsyncError(e, StackTrace.current);
    }
  }
}

final markNotificationReadProvider =
    AsyncNotifierProvider<MarkNotificationReadNotifier, AppNotification?>(MarkNotificationReadNotifier.new);

// ---------------------------------------------------------------------
// Discover-Events-MVP (dritter Bottom-Nav-Tab, siehe `discover_screen.dart`).
// ---------------------------------------------------------------------

/// Index des aktuell gewählten Bottom-Nav-Tabs in `HomeShell`
/// (0 = Discover, 1 = My Parties, 2 = My Invites).
final selectedHomeTabProvider = StateProvider<int>((ref) => 0);

final discoverDeckProvider = FutureProvider<List<DiscoverCard>>((ref) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getDiscoverDeck(token, onRefresh(ref));
});

/// Öffentliche Kataloge (kein Auth nötig) - für Event-Typ-Dropdown +
/// Interest-Tag-Chips im "Publish to Discover"-Formular auf
/// `PartyDetailScreen`.
final eventInterestCatalogProvider = FutureProvider<List<DiscoveryCatalogItem>>((ref) {
  return ref.watch(apiClientProvider).getEventInterestCatalog();
});

final interestTagCatalogProvider = FutureProvider<List<DiscoveryCatalogItem>>((ref) {
  return ref.watch(apiClientProvider).getInterestTagCatalog();
});

/// Swipe-Ergebnis als einmalige Aktion. Invalidiert bewusst NUR
/// `myPartiesProvider` (nicht `discoverDeckProvider`) - der Deck-Re-Fetch
/// soll erst passieren, wenn der lokale Swipe-Stack leer ist (siehe
/// `DiscoverScreen.onDeckEmpty`), sonst würde die Karten-Stack-Animation
/// mitten in der Bewegung neu gemountet.
class DiscoverActionNotifier extends AsyncNotifier<DiscoverActionResult?> {
  @override
  Future<DiscoverActionResult?> build() async => null;

  Future<DiscoverActionResult> act(String partyId, {required String action, String? reason}) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      final result = await ref
          .read(apiClientProvider)
          .postDiscoverAction(token, onRefresh(ref), partyId, action: action, reason: reason);
      state = AsyncData(result);
      ref.invalidate(myPartiesProvider);
      return result;
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final discoverActionProvider =
    AsyncNotifierProvider<DiscoverActionNotifier, DiscoverActionResult?>(DiscoverActionNotifier.new);

/// Undo eines Discover-Swipes als einmalige Aktion - aufgerufen vom
/// "Undo"-Button auf `PartyDetailScreen` (kein Rückwärts-Swipe im Deck,
/// siehe Plan). Lädt `myPartiesProvider` neu, da die Mitgliedschaft danach
/// weg ist.
class UndoDiscoverActionNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> undo(String partyId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).undoDiscoverAction(token, onRefresh(ref), partyId);
      state = const AsyncData(null);
      ref.invalidate(myPartiesProvider);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final undoDiscoverActionProvider =
    AsyncNotifierProvider<UndoDiscoverActionNotifier, void>(UndoDiscoverActionNotifier.new);

/// Organizer blockieren/entblocken (Discover-Engine-Phase-1) - lädt
/// `partyDetailProvider` der aktuell offenen Party neu, da
/// `PartyDetailScreen` selbst keinen separaten "ist geblockt"-Provider
/// beobachtet, sondern rein über den Button-Zustand hier gesteuert wird.
class BlockOrganizerNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> block(String organizerId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).blockOrganizer(token, onRefresh(ref), organizerId);
      state = const AsyncData(null);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final blockOrganizerProvider = AsyncNotifierProvider<BlockOrganizerNotifier, void>(BlockOrganizerNotifier.new);

class UnblockOrganizerNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> unblock(String organizerId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).unblockOrganizer(token, onRefresh(ref), organizerId);
      state = const AsyncData(null);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final unblockOrganizerProvider = AsyncNotifierProvider<UnblockOrganizerNotifier, void>(UnblockOrganizerNotifier.new);

/// Publish/Unpublish als einmalige Aktion, lädt `partyDetailProvider` danach neu.
class PublishPartyNotifier extends AsyncNotifier<Party?> {
  @override
  Future<Party?> build() async => null;

  Future<Party> publish(
    String partyId, {
    required String eventType,
    List<String> interestTags = const [],
    int maxGuests = 0,
  }) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      final party = await ref.read(apiClientProvider).publishParty(
            token,
            onRefresh(ref),
            partyId,
            eventType: eventType,
            interestTags: interestTags,
            maxGuests: maxGuests,
          );
      state = AsyncData(party);
      ref.invalidate(partyDetailProvider(partyId));
      return party;
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }

  Future<void> unpublish(String partyId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).unpublishParty(token, onRefresh(ref), partyId);
      state = const AsyncData(null);
      ref.invalidate(partyDetailProvider(partyId));
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final publishPartyProvider = AsyncNotifierProvider<PublishPartyNotifier, Party?>(PublishPartyNotifier.new);

/// Party-Cover-Bild-Upload als einmalige Aktion (mirroring
/// `UploadProfileImageNotifier`), lädt `partyDetailProvider` danach neu.
class UploadPartyCoverImageNotifier extends AsyncNotifier<Party?> {
  @override
  Future<Party?> build() async => null;

  Future<void> upload(String partyId, File imageFile) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      final party = await ref.read(apiClientProvider).uploadPartyCoverImage(token, onRefresh(ref), partyId, imageFile);
      state = AsyncData(party);
      ref.invalidate(partyDetailProvider(partyId));
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final uploadPartyCoverImageProvider =
    AsyncNotifierProvider<UploadPartyCoverImageNotifier, Party?>(UploadPartyCoverImageNotifier.new);

// ---------------------------------------------------------------------
// Forgot-Password-Flow - zwei einmalige Aktionen, mirroring `AuthNotifier.
// signup`'s breites `catch (e)` (nicht nur `on ApiException`), damit ein
// unerreichbarer Server den Spinner nicht endlos hängen lässt. Bewusst
// unauthentifiziert (kein `requiredAccessTokenProvider`) - beide Endpunkte
// sind vor dem Login erreichbar.
// ---------------------------------------------------------------------

class RequestPasswordResetNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> request(String email) async {
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).requestPasswordReset(email: email);
      state = const AsyncData(null);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
    }
  }
}

final requestPasswordResetProvider =
    AsyncNotifierProvider<RequestPasswordResetNotifier, void>(RequestPasswordResetNotifier.new);

class ResetPasswordNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  /// Löscht `passwordResetTokenProvider` bewusst NICHT automatisch bei
  /// Erfolg - `main.dart`'s Routing würde sonst sofort von
  /// `ResetPasswordScreen` weg zurück zum Login springen, bevor die
  /// Erfolgsmeldung überhaupt sichtbar wird. Der Screen selbst löscht den
  /// Token erst, wenn der Nutzer aktiv "Back to login" tippt.
  Future<void> reset(String token, String newPassword) async {
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).resetPassword(token: token, newPassword: newPassword);
      state = const AsyncData(null);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
    }
  }
}

final resetPasswordProvider = AsyncNotifierProvider<ResetPasswordNotifier, void>(ResetPasswordNotifier.new);

// ---------------------------------------------------------------------
// Email-Verification + Account-Unlock-Flow - mirroring den Forgot-Password-
// Block oben (gleiches breites `catch (e)`-Muster).
// ---------------------------------------------------------------------

/// Bestätigt einen `verify-email`-Token. Invalidiert `currentUserProvider`
/// bei Erfolg, damit die "E-Mail verifizieren"-Banner in `HomeShell` sofort
/// verschwindet, ohne dass der Nutzer manuell neu laden muss.
class VerifyEmailNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> confirm(String token) async {
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).verifyEmail(token: token);
      state = const AsyncData(null);
      ref.invalidate(currentUserProvider);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
    }
  }
}

final verifyEmailProvider = AsyncNotifierProvider<VerifyEmailNotifier, void>(VerifyEmailNotifier.new);

/// Verlangt einen bereits eingeloggten Nutzer (`requiredAccessTokenProvider`),
/// anders als die übrigen Notifiers in diesem Block - der "Resend"-Button
/// lebt im eingeloggten `HomeShell`-Banner.
class ResendVerificationEmailNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> resend() async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).resendVerificationEmail(token, onRefresh(ref));
      state = const AsyncData(null);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
    }
  }
}

final resendVerificationEmailProvider =
    AsyncNotifierProvider<ResendVerificationEmailNotifier, void>(ResendVerificationEmailNotifier.new);

class RequestAccountUnlockNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> request(String email) async {
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).requestAccountUnlock(email: email);
      state = const AsyncData(null);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
    }
  }
}

final requestAccountUnlockProvider =
    AsyncNotifierProvider<RequestAccountUnlockNotifier, void>(RequestAccountUnlockNotifier.new);

class UnlockAccountNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  /// Löscht `accountUnlockTokenProvider` bewusst NICHT automatisch bei
  /// Erfolg - mirroring `ResetPasswordNotifier.reset`, damit der Screen die
  /// Erfolgsmeldung zeigen kann, bevor der Nutzer aktiv weitergeht.
  Future<void> confirm(String token) async {
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).unlockAccount(token: token);
      state = const AsyncData(null);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
    }
  }
}

final unlockAccountProvider = AsyncNotifierProvider<UnlockAccountNotifier, void>(UnlockAccountNotifier.new);
