import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../models/organizer.dart';
import '../models/organizer_member.dart';
import '../state/organizer_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Die fünf `OrganizerRole`-Werte des Backends - reine Client-Konvention
/// (kein Katalog-Endpoint), mirrort `social_privacy_screen.dart`'s
/// `_kFriendListVisibility`.
const _kOrganizerRoles = ['owner', 'admin', 'editor', 'viewer', 'member'];

/// Organizer-Detail (Social-Graph-Phase-4) - Kopf + Mitgliederliste. Der
/// `GET /organizers/{id}`-Endpoint ist member-gated: für einen gefolgten
/// Organizer, in dem der User NICHT Mitglied ist, kommt 403 - dann zeigt
/// dieser Screen einen erklärenden Leerzustand (mirrort
/// `UserFriendsScreen`'s 403-Behandlung). Mitglieder hinzufügen darf nur
/// der Owner (per roher User-ID - es gibt noch keine User-Suche innerhalb
/// eines Organizers).
class OrganizerDetailScreen extends ConsumerWidget {
  final String organizerId;
  const OrganizerDetailScreen({super.key, required this.organizerId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final organizerAsync = ref.watch(organizerDetailProvider(organizerId));

    return Scaffold(
      appBar: AppBar(
        title: Text(organizerAsync.valueOrNull?.displayName ?? 'Organizer'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(selectedOrganizerIdProvider.notifier).state = null,
        ),
      ),
      body: organizerAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) {
          if (err is ApiException && err.statusCode == 403) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: Text("You're not a member of this organizer."),
              ),
            );
          }
          return Center(
            child: TextButton(
              onPressed: () => ref.invalidate(organizerDetailProvider(organizerId)),
              child: const Text('Failed to load organizer. Retry'),
            ),
          );
        },
        data: (organizer) => SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _OrganizerHeader(organizer: organizer),
              const SizedBox(height: 20),
              _MembersSection(organizerId: organizerId, isOwner: organizer.myRole == 'owner'),
            ],
          ),
        ),
      ),
    );
  }
}

class _OrganizerHeader extends StatelessWidget {
  final Organizer organizer;
  const _OrganizerHeader({required this.organizer});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(organizer.displayName, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Row(
              children: [
                Icon(
                  organizer.isVerified ? Icons.verified : Icons.hourglass_empty,
                  size: 18,
                  color: organizer.isVerified ? Colors.green : Colors.grey,
                ),
                const SizedBox(width: 6),
                Text(organizer.verificationStatus),
              ],
            ),
            if (organizer.organizerType.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(organizer.organizerType, style: const TextStyle(color: Colors.grey)),
            ],
            if (organizer.description.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(organizer.description),
            ],
            if (organizer.websiteUrl.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(organizer.websiteUrl, style: const TextStyle(color: Colors.blue)),
            ],
          ],
        ),
      ),
    );
  }
}

class _MembersSection extends ConsumerWidget {
  final String organizerId;
  final bool isOwner;
  const _MembersSection({required this.organizerId, required this.isOwner});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final membersAsync = ref.watch(organizerMembersProvider(organizerId));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Members', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        membersAsync.when(
          loading: () => const Padding(
            padding: EdgeInsets.all(16),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (err, st) => TextButton(
            onPressed: () => ref.invalidate(organizerMembersProvider(organizerId)),
            child: const Text('Failed to load members. Retry'),
          ),
          data: (members) => Column(
            children: [
              for (final m in members) _MemberTile(member: m),
              if (members.isEmpty)
                const Padding(padding: EdgeInsets.symmetric(vertical: 12), child: Text('No members yet.')),
            ],
          ),
        ),
        if (isOwner) ...[
          const SizedBox(height: 12),
          _AddMemberForm(organizerId: organizerId),
        ],
      ],
    );
  }
}

class _MemberTile extends StatelessWidget {
  final OrganizerMember member;
  const _MemberTile({required this.member});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.person)),
        title: Text(member.userId, style: const TextStyle(fontFamily: 'monospace', fontSize: 12)),
        trailing: Text(member.role),
      ),
    );
  }
}

class _AddMemberForm extends ConsumerStatefulWidget {
  final String organizerId;
  const _AddMemberForm({required this.organizerId});

  @override
  ConsumerState<_AddMemberForm> createState() => _AddMemberFormState();
}

class _AddMemberFormState extends ConsumerState<_AddMemberForm> {
  final _userIdController = TextEditingController();
  String _role = 'editor';

  @override
  void dispose() {
    _userIdController.dispose();
    super.dispose();
  }

  Future<void> _add() async {
    final userId = _userIdController.text.trim();
    if (userId.isEmpty) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(addOrganizerMemberProvider.notifier).add(widget.organizerId, userId: userId, role: _role);
      _userIdController.clear();
      messenger.showSnackBar(const SnackBar(content: Text('Member added.')));
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to add member. Please try again.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final addState = ref.watch(addOrganizerMemberProvider);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Add member', style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 8),
            TextField(
              controller: _userIdController,
              decoration: const InputDecoration(
                labelText: 'User ID',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                const Text('Role: '),
                const SizedBox(width: 8),
                DropdownButton<String>(
                  value: _role,
                  items: _kOrganizerRoles
                      .map((r) => DropdownMenuItem(value: r, child: Text(r)))
                      .toList(),
                  onChanged: (value) => setState(() => _role = value ?? _role),
                ),
                const Spacer(),
                ElevatedButton(
                  onPressed: addState.isLoading ? null : _add,
                  child: addState.isLoading
                      ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('Add'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
