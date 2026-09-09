import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/profile.dart';
import 'auth_providers.dart';
import 'providers.dart';

/// Social-Profil des eingeloggten Users + Onboarding/Update-Aktionen
/// (mirroring `DiscoveryPreferencesNotifier`'s Fetch+Save-in-einem Pattern).
/// `build()` wirft ein 404 als `AsyncError`, solange noch nie
/// `birth-date-correction` aufgerufen wurde - `ProfileScreen` fängt genau
/// diesen Fall ab, um statt eines generischen Fehlerzustands das
/// Onboarding-Formular zu zeigen.
class ProfileNotifier extends AsyncNotifier<Profile> {
  @override
  Future<Profile> build() async {
    final token = ref.watch(requiredAccessTokenProvider);
    return ref.watch(apiClientProvider).getProfile(token, onRefresh(ref));
  }

  Future<void> save({String? gender, String? bio, String? username}) async {
    final token = ref.read(requiredAccessTokenProvider);
    final client = ref.read(apiClientProvider);
    final updated =
        await client.updateProfile(token, onRefresh(ref), gender: gender, bio: bio, username: username);
    state = AsyncData(updated);
  }

  /// Einziger Schreibpfad fürs Geburtsdatum - beim allerersten Aufruf legt
  /// das Backend das Profil überhaupt erst an (Onboarding), danach ist es
  /// eine reine Korrektur.
  Future<void> correctBirthDate({required DateTime birthDate, String reason = ''}) async {
    final token = ref.read(requiredAccessTokenProvider);
    final client = ref.read(apiClientProvider);
    final updated = await client.correctBirthDate(token, onRefresh(ref), birthDate: birthDate, reason: reason);
    state = AsyncData(updated);
  }
}

final profileProvider = AsyncNotifierProvider<ProfileNotifier, Profile>(ProfileNotifier.new);

/// Zeigt `ProfileScreen` (Einstiegspunkt: Icon in `HomeShell`'s AppBar).
final showProfileProvider = StateProvider<bool>((ref) => false);
