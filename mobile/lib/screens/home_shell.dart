import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../api/api_config.dart';
import '../models/invitation.dart';
import '../state/auth_providers.dart';
import '../state/geo_providers.dart';
import '../state/profile_providers.dart';
import '../widgets/image_source_picker.dart';
import 'discover_screen.dart';
import 'invitation_list_screen.dart';
import 'party_list_screen.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Gemeinsame Startseite mit 3-Tab Material-3 `NavigationBar` (Discover
/// Events / My Parties / My Invites) - ersetzt seit dem Discover-MVP-Plan
/// den alten `TabBar`-only `PartyListScreen`. Trägt die gemeinsame `AppBar`
/// (Profilbild/Notification-Glocke/Logout, verbatim aus dem alten
/// `PartyListScreen` übernommen) und ein `IndexedStack`, damit der Zustand
/// jedes Tabs (insbesondere der Swipe-Deck-Fortschritt im Discover-Tab)
/// beim Tab-Wechsel erhalten bleibt.
class HomeShell extends ConsumerWidget {
  const HomeShell({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final userAsync = ref.watch(currentUserProvider);
    final selectedTab = ref.watch(selectedHomeTabProvider);
    final pendingInvites = ref.watch(myInvitationsProvider).maybeWhen(
          data: (invitations) => invitations.where((i) => i.status == InvitationStatus.pending).length,
          orElse: () => 0,
        );

    return Scaffold(
      appBar: AppBar(
        title: Text(userAsync.maybeWhen(
          data: (user) => 'Hi, ${user.displayName}',
          orElse: () => 'Party App',
        )),
        actions: [
          if (selectedTab == 0)
            IconButton(
              icon: const Icon(Icons.tune),
              tooltip: 'Discovery preferences',
              onPressed: () => ref.read(showDiscoveryPreferencesProvider.notifier).state = true,
            ),
          IconButton(
            icon: const Icon(Icons.person_outline),
            tooltip: 'Profile',
            onPressed: () => ref.read(showProfileProvider.notifier).state = true,
          ),
          const _ProfileAvatarButton(),
          const _NotificationBellButton(),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Log out',
            onPressed: () => ref.read(authProvider.notifier).logout(),
          ),
        ],
      ),
      body: Column(
        children: [
          if (userAsync.value?.emailVerified == false) const _EmailVerificationBanner(),
          Expanded(
            child: IndexedStack(
              index: selectedTab,
              children: const [DiscoverScreen(), PartyListScreen(), InvitationListScreen()],
            ),
          ),
        ],
      ),
      floatingActionButton: selectedTab == 1
          ? FloatingActionButton.extended(
              onPressed: () => ref.read(creatingPartyProvider.notifier).state = true,
              icon: const Icon(Icons.add),
              label: const Text('Create Party'),
            )
          : null,
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedTab,
        onDestinationSelected: (index) => ref.read(selectedHomeTabProvider.notifier).state = index,
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.explore_outlined),
            selectedIcon: Icon(Icons.explore),
            label: 'Discover',
          ),
          const NavigationDestination(
            icon: Icon(Icons.celebration_outlined),
            selectedIcon: Icon(Icons.celebration),
            label: 'My Parties',
          ),
          NavigationDestination(
            icon: pendingInvites > 0 ? Badge(label: Text('$pendingInvites'), child: const Icon(Icons.mail_outline)) : const Icon(Icons.mail_outline),
            selectedIcon: pendingInvites > 0 ? Badge(label: Text('$pendingInvites'), child: const Icon(Icons.mail)) : const Icon(Icons.mail),
            label: 'My Invites',
          ),
        ],
      ),
    );
  }
}

/// Glocken-Icon mit Ungelesen-Badge, öffnet `NotificationsScreen` via
/// `showNotificationsProvider`.
class _NotificationBellButton extends ConsumerWidget {
  const _NotificationBellButton();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notificationsAsync = ref.watch(notificationsProvider);
    final unreadCount = notificationsAsync.maybeWhen(
      data: (notifications) => notifications.where((n) => !n.read).length,
      orElse: () => 0,
    );

    return Stack(
      alignment: Alignment.center,
      children: [
        IconButton(
          icon: const Icon(Icons.notifications),
          tooltip: 'Notifications',
          onPressed: () => ref.read(showNotificationsProvider.notifier).state = true,
        ),
        if (unreadCount > 0)
          Positioned(
            right: 6,
            top: 6,
            child: Container(
              padding: const EdgeInsets.all(2),
              decoration: BoxDecoration(color: Colors.red, borderRadius: BorderRadius.circular(8)),
              constraints: const BoxConstraints(minWidth: 16, minHeight: 16),
              child: Text(
                '$unreadCount',
                style: const TextStyle(color: Colors.white, fontSize: 10),
                textAlign: TextAlign.center,
              ),
            ),
          ),
      ],
    );
  }
}

/// Tippbarer Avatar in der AppBar - öffnet die Galerie via `image_picker`
/// und lädt das gewählte Foto als neues Profilbild hoch (lokales Disk-
/// Storage auf dem Server, siehe Phase-5-Plan Teil D). Zeigt das bestehende
/// Profilbild via `/media/...`-URL an, falls schon eines gesetzt ist.
class _ProfileAvatarButton extends ConsumerStatefulWidget {
  const _ProfileAvatarButton();

  @override
  ConsumerState<_ProfileAvatarButton> createState() => _ProfileAvatarButtonState();
}

class _ProfileAvatarButtonState extends ConsumerState<_ProfileAvatarButton> {
  bool _uploading = false;

  Future<void> _pickAndUpload() async {
    final source = await pickImageSource(context);
    if (source == null || !mounted) return;
    final picker = ImagePicker();
    XFile? picked;
    try {
      picked = await picker.pickImage(source: source, maxWidth: 1024, maxHeight: 1024);
    } catch (_) {
      // z.B. verweigerte Kamera-/Galerie-Berechtigung wirft eine
      // `PlatformException` - ohne diesen Guard würde das hier uncaught
      // durchschlagen statt eine Fehlermeldung zu zeigen.
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not open image picker. Check app permissions.')),
        );
      }
      return;
    }
    if (picked == null || !mounted) return;
    setState(() => _uploading = true);
    try {
      await ref.read(uploadProfileImageProvider.notifier).upload(File(picked.path));
      // Der Dateiname ist serverseitig fest ({user_id}.jpg, siehe
      // `me.py::upload_profile_image`) - ohne Cache-Eviction würde das alte
      // Bild aus dem Flutter-`imageCache` weiterhin unter derselben URL
      // angezeigt und ein erfolgreicher Upload sähe wie ein no-op aus.
      final updated = ref.read(uploadProfileImageProvider).value;
      if (updated != null && updated.profileImage.isNotEmpty) {
        imageCache.evict(NetworkImage('${ApiConfig.baseUrl}/media/${updated.profileImage}'));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Failed to upload profile picture.')),
        );
      }
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final userAsync = ref.watch(currentUserProvider);
    final profileImage = userAsync.maybeWhen(data: (user) => user.profileImage, orElse: () => '');

    return IconButton(
      tooltip: 'Change profile picture',
      onPressed: _uploading ? null : _pickAndUpload,
      icon: _uploading
          ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
          : CircleAvatar(
              radius: 14,
              backgroundImage:
                  profileImage.isNotEmpty ? NetworkImage('${ApiConfig.baseUrl}/media/$profileImage') : null,
              // Ohne diesen Handler wirft ein 404/kaputtes Profilbild einen
              // ungefangenen Bildfehler bei jedem Repaint statt sauber auf das
              // Personen-Icon zurückzufallen.
              onBackgroundImageError: profileImage.isNotEmpty ? (_, _) {} : null,
              child: profileImage.isEmpty ? const Icon(Icons.person, size: 16) : null,
            ),
    );
  }
}

/// Schlanker, nicht-blockierender Hinweis über dem `IndexedStack`, solange
/// `email_verified` false ist (soft/nicht-blockierendes Feature, siehe Plan).
/// Verschwindet von selbst, sobald `currentUserProvider` nach erfolgreichem
/// Verify/Resend neu geladen wird - kein manuelles Dismiss nötig.
class _EmailVerificationBanner extends ConsumerWidget {
  const _EmailVerificationBanner();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final resendState = ref.watch(resendVerificationEmailProvider);
    final isLoading = resendState.isLoading;

    ref.listen(resendVerificationEmailProvider, (previous, next) {
      if (next.hasError) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Failed to resend verification email.')),
        );
      } else if (previous?.isLoading == true && !next.isLoading && !next.hasError) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Verification email sent.')),
        );
      }
    });

    return Container(
      width: double.infinity,
      color: Theme.of(context).colorScheme.secondaryContainer,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          const Expanded(child: Text('Please verify your email.')),
          TextButton(
            onPressed: isLoading ? null : () => ref.read(resendVerificationEmailProvider.notifier).resend(),
            child: isLoading
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Resend'),
          ),
        ],
      ),
    );
  }
}
