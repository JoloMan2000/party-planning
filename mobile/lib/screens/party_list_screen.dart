import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../api/api_client.dart';
import '../api/api_config.dart';
import '../models/invitation.dart';
import '../models/party.dart';
import '../state/auth_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Authentifizierte Startseite: eigene Partys + eigene Einladungen in zwei
/// Tabs, mirroring den bestehenden Tab-losen Screens aber neu mit
/// `TabBar`/`TabBarView`, da hier erstmals zwei gleichrangige Listen
/// nebeneinander existieren.
class PartyListScreen extends ConsumerWidget {
  const PartyListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final userAsync = ref.watch(currentUserProvider);

    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: Text(userAsync.maybeWhen(
            data: (user) => 'Hi, ${user.displayName}',
            orElse: () => 'Party App',
          )),
          actions: [
            const _ProfileAvatarButton(),
            const _NotificationBellButton(),
            IconButton(
              icon: const Icon(Icons.logout),
              tooltip: 'Log out',
              onPressed: () => ref.read(authProvider.notifier).logout(),
            ),
          ],
          bottom: const TabBar(
            tabs: [
              Tab(text: 'My Parties'),
              Tab(text: 'My Invitations'),
            ],
          ),
        ),
        body: const TabBarView(
          children: [_MyPartiesTab(), _MyInvitationsTab()],
        ),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: () => ref.read(creatingPartyProvider.notifier).state = true,
          icon: const Icon(Icons.add),
          label: const Text('Create Party'),
        ),
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
    final picker = ImagePicker();
    final picked = await picker.pickImage(source: ImageSource.gallery, maxWidth: 1024, maxHeight: 1024);
    if (picked == null) return;
    setState(() => _uploading = true);
    try {
      await ref.read(uploadProfileImageProvider.notifier).upload(File(picked.path));
    } on ApiException catch (_) {
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
              child: profileImage.isEmpty ? const Icon(Icons.person, size: 16) : null,
            ),
    );
  }
}

class _MyPartiesTab extends ConsumerWidget {
  const _MyPartiesTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final partiesAsync = ref.watch(myPartiesProvider);
    return partiesAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (err, st) => Center(
        child: TextButton(
          onPressed: () => ref.invalidate(myPartiesProvider),
          child: const Text('Failed to load parties. Retry'),
        ),
      ),
      data: (parties) {
        if (parties.isEmpty) {
          return const Center(child: Text('No parties yet. Create one!'));
        }
        return ListView.builder(
          padding: const EdgeInsets.all(12),
          itemCount: parties.length,
          itemBuilder: (context, i) => _PartyTile(party: parties[i]),
        );
      },
    );
  }
}

class _PartyTile extends ConsumerWidget {
  final Party party;
  const _PartyTile({required this.party});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: ListTile(
        title: Text(party.name),
        subtitle: Text(
          party.startsAt != null ? party.startsAt.toString() : party.location,
        ),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => ref.read(selectedPartyIdProvider.notifier).state = party.id,
      ),
    );
  }
}

class _MyInvitationsTab extends ConsumerWidget {
  const _MyInvitationsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final invitationsAsync = ref.watch(myInvitationsProvider);
    return invitationsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (err, st) => Center(
        child: TextButton(
          onPressed: () => ref.invalidate(myInvitationsProvider),
          child: const Text('Failed to load invitations. Retry'),
        ),
      ),
      data: (invitations) {
        if (invitations.isEmpty) {
          return const Center(child: Text('No invitations yet.'));
        }
        return ListView.builder(
          padding: const EdgeInsets.all(12),
          itemCount: invitations.length,
          itemBuilder: (context, i) => _InvitationTile(invitation: invitations[i]),
        );
      },
    );
  }
}

class _InvitationTile extends ConsumerWidget {
  final Invitation invitation;
  const _InvitationTile({required this.invitation});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: ListTile(
        title: const Text('Invitation'),
        subtitle: Text('Status: ${invitation.status.name}'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => ref.read(selectedInvitationIdProvider.notifier).state = invitation.id,
      ),
    );
  }
}
