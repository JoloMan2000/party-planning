import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/followed_event.dart';
import '../models/follow_status.dart';
import '../models/organizer.dart';
import '../models/organizer_member.dart';
import 'auth_providers.dart';
import 'providers.dart';

/// Social Graph Phase 4/5 (Organizer-Domain + Following) - Organizer-CRUD,
/// Mitgliedschaften und Follows auf Organizer/Events (siehe
/// `backend/app/routers/organizers.py` + `backend/app/routers/follows.py`).
/// Organizer und Following liegen bewusst in EINER Datei: Following folgt
/// primär Organizern, die beiden Domains teilen sich Screens
/// (`FollowingScreen`, `OrganizerDetailScreen`) und Invalidierungs-Ketten.

// --- Reads ----------------------------------------------------------

final myOrganizersProvider = FutureProvider<List<Organizer>>((ref) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).listMyOrganizers(token, onRefresh(ref));
});

final organizerDetailProvider = FutureProvider.family<Organizer, String>((ref, organizerId) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getOrganizer(token, onRefresh(ref), organizerId);
});

final organizerMembersProvider = FutureProvider.family<List<OrganizerMember>, String>((ref, organizerId) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).listOrganizerMembers(token, onRefresh(ref), organizerId);
});

final followedOrganizersProvider = FutureProvider<List<Organizer>>((ref) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).listFollowedOrganizers(token, onRefresh(ref));
});

final followedEventsProvider = FutureProvider<List<FollowedEvent>>((ref) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).listFollowedEvents(token, onRefresh(ref));
});

/// Follower-Zahl + eigener `following`-Status eines Organizers - `.family`
/// keyed by `organizerId`, damit ein Follow-Toggle auf `PartyDetailScreen`
/// bzw. im `FollowingScreen` gezielt genau diese Zeile neu lädt.
final organizerFollowStatusProvider = FutureProvider.family<OrganizerFollowStatus, String>((ref, organizerId) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getOrganizerFollowStatus(token, onRefresh(ref), organizerId);
});

final eventFollowStatusProvider = FutureProvider.family<EventFollowStatus, String>((ref, partyId) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getEventFollowStatus(token, onRefresh(ref), partyId);
});

// --- Actions ------------------------------------------------------

/// Organizer anlegen - mirrort `CreatePartyNotifier` in `auth_providers.dart`
/// (liefert die neue Entität zurück, damit der Aufrufer direkt in den
/// Detail-Screen routen kann).
class CreateOrganizerNotifier extends AsyncNotifier<Organizer?> {
  @override
  Future<Organizer?> build() async => null;

  Future<Organizer> create({
    required String displayName,
    String organizerType = '',
    String description = '',
    String websiteUrl = '',
  }) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      final organizer = await ref.read(apiClientProvider).createOrganizer(
            token,
            onRefresh(ref),
            displayName: displayName,
            organizerType: organizerType,
            description: description,
            websiteUrl: websiteUrl,
          );
      state = AsyncData(organizer);
      ref.invalidate(myOrganizersProvider);
      return organizer;
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final createOrganizerProvider =
    AsyncNotifierProvider<CreateOrganizerNotifier, Organizer?>(CreateOrganizerNotifier.new);

/// Mitglied hinzufügen/umstufen (nur der Owner darf) - akzeptiert alle fünf
/// `OrganizerRole`-Werte.
class AddOrganizerMemberNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> add(String organizerId, {required String userId, required String role}) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).addOrganizerMember(token, onRefresh(ref), organizerId, userId: userId, role: role);
      state = const AsyncData(null);
      ref.invalidate(organizerMembersProvider(organizerId));
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final addOrganizerMemberProvider =
    AsyncNotifierProvider<AddOrganizerMemberNotifier, void>(AddOrganizerMemberNotifier.new);

/// Organizer folgen/entfolgen. Invalidiert die Status-Zeile + die eigene
/// Following-Liste (mirrort `SendFriendRequestNotifier`).
class ToggleOrganizerFollowNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> follow(String organizerId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).followOrganizer(token, onRefresh(ref), organizerId);
      state = const AsyncData(null);
      ref.invalidate(organizerFollowStatusProvider(organizerId));
      ref.invalidate(followedOrganizersProvider);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }

  Future<void> unfollow(String organizerId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).unfollowOrganizer(token, onRefresh(ref), organizerId);
      state = const AsyncData(null);
      ref.invalidate(organizerFollowStatusProvider(organizerId));
      ref.invalidate(followedOrganizersProvider);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final toggleOrganizerFollowProvider =
    AsyncNotifierProvider<ToggleOrganizerFollowNotifier, void>(ToggleOrganizerFollowNotifier.new);

/// Event folgen/entfolgen. `Follow Event` ist getrennt von `Going`/`Maybe`.
class ToggleEventFollowNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> follow(String partyId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).followEvent(token, onRefresh(ref), partyId);
      state = const AsyncData(null);
      ref.invalidate(eventFollowStatusProvider(partyId));
      ref.invalidate(followedEventsProvider);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }

  Future<void> unfollow(String partyId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).unfollowEvent(token, onRefresh(ref), partyId);
      state = const AsyncData(null);
      ref.invalidate(eventFollowStatusProvider(partyId));
      ref.invalidate(followedEventsProvider);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final toggleEventFollowProvider =
    AsyncNotifierProvider<ToggleEventFollowNotifier, void>(ToggleEventFollowNotifier.new);

// --- Navigation flags -------------------------------------------------
// Reine `StateProvider`s (mirrort `showFriendsProvider` /
// `selectedFriendProfileUserIdProvider` in `social_providers.dart` - diese
// App hat kein Navigator/go_router, Screen-Wechsel läuft über solche Flags
// in `main.dart`).

final showMyOrganizersProvider = StateProvider<bool>((ref) => false);
final creatingOrganizerProvider = StateProvider<bool>((ref) => false);
final selectedOrganizerIdProvider = StateProvider<String?>((ref) => null);
final showFollowingProvider = StateProvider<bool>((ref) => false);
