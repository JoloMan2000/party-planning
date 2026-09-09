import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/friend.dart';
import '../models/friend_request.dart';
import '../models/social_privacy.dart';
import '../models/social_profile.dart';
import '../models/user_search_result.dart';
import 'auth_providers.dart';
import 'providers.dart';

/// Social Graph Phase 1 (Friends-Fundament) - Friend Requests, Friendship,
/// Blocking, Friend Search (siehe `backend/app/routers/social.py`).

final friendsProvider = FutureProvider<List<Friend>>((ref) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getFriends(token, onRefresh(ref));
});

final friendRequestsProvider = FutureProvider<FriendRequestsInbox>((ref) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getFriendRequests(token, onRefresh(ref));
});

final socialProfileProvider = FutureProvider.family<SocialProfile, String>((ref, userId) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getSocialProfile(token, onRefresh(ref), userId);
});

/// User-Suche als Suche-während-Tippen (mirrort `LocationSearchNotifier` in
/// `state/geo_providers.dart` exakt) - Generation-Counter statt
/// `http`-Request-Cancellation, damit eine spät eintreffende veraltete
/// Antwort nicht eine frischere überschreibt.
class UserSearchNotifier extends Notifier<AsyncValue<List<UserSearchResult>>> {
  int _generation = 0;

  @override
  AsyncValue<List<UserSearchResult>> build() => const AsyncData([]);

  Future<void> search(String query) async {
    if (query.trim().length < 2) {
      state = const AsyncData([]);
      return;
    }
    final myGeneration = ++_generation;
    state = const AsyncLoading();
    final token = ref.read(requiredAccessTokenProvider);
    try {
      final results = await ref.read(apiClientProvider).searchUsers(token, onRefresh(ref), q: query);
      if (myGeneration != _generation) return;
      state = AsyncData(results);
    } catch (error, stackTrace) {
      if (myGeneration != _generation) return;
      state = AsyncError(error, stackTrace);
    }
  }

  void clear() {
    _generation++;
    state = const AsyncData([]);
  }
}

final userSearchProvider =
    NotifierProvider<UserSearchNotifier, AsyncValue<List<UserSearchResult>>>(UserSearchNotifier.new);

/// Freundschaftsanfrage senden - invalidiert das Zielprofil (Status wechselt
/// auf "request_sent") + die eigene Outbox.
class SendFriendRequestNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> send(String userId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).sendFriendRequest(token, onRefresh(ref), userId);
      state = const AsyncData(null);
      ref.invalidate(socialProfileProvider(userId));
      ref.invalidate(friendRequestsProvider);
      ref.invalidate(friendsProvider); // Cross-Merge kann sofort eine Friendship erzeugen.
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final sendFriendRequestProvider = AsyncNotifierProvider<SendFriendRequestNotifier, void>(SendFriendRequestNotifier.new);

/// Annehmen/Ablehnen einer eingehenden Anfrage.
class RespondFriendRequestNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> accept(String requestId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).acceptFriendRequest(token, onRefresh(ref), requestId);
      state = const AsyncData(null);
      ref.invalidate(friendRequestsProvider);
      ref.invalidate(friendsProvider);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }

  Future<void> decline(String requestId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).declineFriendRequest(token, onRefresh(ref), requestId);
      state = const AsyncData(null);
      ref.invalidate(friendRequestsProvider);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final respondFriendRequestProvider =
    AsyncNotifierProvider<RespondFriendRequestNotifier, void>(RespondFriendRequestNotifier.new);

/// Zurückziehen einer selbst gesendeten Anfrage.
class CancelFriendRequestNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> cancel(String requestId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).cancelFriendRequest(token, onRefresh(ref), requestId);
      state = const AsyncData(null);
      ref.invalidate(friendRequestsProvider);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final cancelFriendRequestProvider =
    AsyncNotifierProvider<CancelFriendRequestNotifier, void>(CancelFriendRequestNotifier.new);

/// Freund entfernen.
class RemoveFriendNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> remove(String userId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).removeFriend(token, onRefresh(ref), userId);
      state = const AsyncData(null);
      ref.invalidate(friendsProvider);
      ref.invalidate(socialProfileProvider(userId));
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final removeFriendProvider = AsyncNotifierProvider<RemoveFriendNotifier, void>(RemoveFriendNotifier.new);

/// User blockieren/entblocken.
class BlockUserNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> block(String userId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).blockUser(token, onRefresh(ref), userId);
      state = const AsyncData(null);
      ref.invalidate(socialProfileProvider(userId));
      ref.invalidate(friendsProvider);
      ref.invalidate(friendRequestsProvider);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final blockUserProvider = AsyncNotifierProvider<BlockUserNotifier, void>(BlockUserNotifier.new);

class UnblockUserNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> unblock(String userId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).unblockUser(token, onRefresh(ref), userId);
      state = const AsyncData(null);
      ref.invalidate(socialProfileProvider(userId));
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final unblockUserProvider = AsyncNotifierProvider<UnblockUserNotifier, void>(UnblockUserNotifier.new);

/// Navigations-`StateProvider`s (mirroring `showSpotifyConnectProvider` in
/// `state/spotify_providers.dart` / `selectedPartyIdProvider` in
/// `state/auth_providers.dart` - dieses Repo hat kein Navigator/go_router,
/// Screen-Wechsel läuft komplett über solche booleschen/nullable Flags in
/// `main.dart`).
final showFriendsProvider = StateProvider<bool>((ref) => false);
final selectedFriendProfileUserIdProvider = StateProvider<String?>((ref) => null);

/// Social Graph Phase 3 (Friend-list privacy & social settings polish) -
/// siehe `backend/app/routers/social.py::get_social_privacy`/`update_social_privacy`.

/// Mirrort `DiscoveryPreferencesNotifier` in `state/geo_providers.dart`
/// exakt - `build()` lädt, `save()` PUTet den vollständigen Datensatz.
class SocialPrivacyNotifier extends AsyncNotifier<SocialPrivacy> {
  @override
  Future<SocialPrivacy> build() async {
    final token = ref.watch(requiredAccessTokenProvider);
    return ref.watch(apiClientProvider).getSocialPrivacy(token, onRefresh(ref));
  }

  Future<void> save(SocialPrivacy privacy) async {
    final token = ref.read(requiredAccessTokenProvider);
    final client = ref.read(apiClientProvider);
    final saved = await client.updateSocialPrivacy(token, onRefresh(ref), privacy);
    state = AsyncData(saved);
  }
}

final socialPrivacyProvider = AsyncNotifierProvider<SocialPrivacyNotifier, SocialPrivacy>(SocialPrivacyNotifier.new);

/// Navigations-Flag (mirrort `showFriendsProvider`).
final showSocialPrivacyProvider = StateProvider<bool>((ref) => false);

/// Freundesliste eines ANDEREN Users (Social-Graph-Phase-3) - respektiert
/// dessen `friend_list_visibility` serverseitig (siehe
/// `backend/app/routers/social.py::get_user_friends`).
final userFriendsProvider = FutureProvider.family<List<Friend>, String>((ref, userId) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getUserFriends(token, onRefresh(ref), userId);
});

/// Navigations-Flag mit Payload (mirrort `selectedFriendProfileUserIdProvider`).
final viewingUserFriendsUserIdProvider = StateProvider<String?>((ref) => null);
