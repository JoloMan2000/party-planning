import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'package:share_plus/share_plus.dart';

import '../api/api_client.dart';
import '../api/api_config.dart';
import '../models/party.dart';
import '../models/party_guests_response.dart';
import '../state/auth_providers.dart';
import '../widgets/image_source_picker.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Party-Detail: Host/Co-Host sehen Gästeliste + Invite-Formular, einfache
/// Gäste sehen nur die Party-Infos (Unterscheidung über 403 auf
/// `partyGuestsProvider`, siehe Plan - keine explizite Rollen-Prüfung
/// client-seitig, da `GET /parties/{id}` die eigene Rolle nicht mitliefert).
class PartyDetailScreen extends ConsumerWidget {
  final String partyId;
  const PartyDetailScreen({super.key, required this.partyId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final partyAsync = ref.watch(partyDetailProvider(partyId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Party'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(selectedPartyIdProvider.notifier).state = null,
        ),
      ),
      body: partyAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(partyDetailProvider(partyId)),
            child: const Text('Failed to load party. Retry'),
          ),
        ),
        data: (party) => SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _PartyHeader(party: party),
              const SizedBox(height: 20),
              _UndoDiscoverJoinSection(party: party),
              _PublishToDiscoverSection(party: party),
              const SizedBox(height: 20),
              _GuestsSection(partyId: partyId),
            ],
          ),
        ),
      ),
    );
  }
}

/// "Undo"-Button für einen früheren Discover-Swipe (`going`/`maybe`) -
/// bewusst KEIN Rückwärts-Swipe im Deck, sondern ein expliziter Button im
/// Party-Detail-Screen (siehe Plan). Erscheint nie für den Host/Co-Host
/// oder für persönlich eingeladene Gäste, da nur ein Discover-Join
/// `party.myDiscoverAction` setzt.
class _UndoDiscoverJoinSection extends ConsumerWidget {
  final Party party;
  const _UndoDiscoverJoinSection({required this.party});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (party.myDiscoverAction == null) return const SizedBox.shrink();
    final undoState = ref.watch(undoDiscoverActionProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Card(
          child: ListTile(
            leading: const Icon(Icons.undo),
            title: const Text('Joined via Discover'),
            subtitle: Text('You are ${party.myDiscoverAction} for this party.'),
            trailing: TextButton(
              onPressed: undoState.isLoading ? null : () => _confirmAndUndo(context, ref),
              child: const Text('Undo'),
            ),
          ),
        ),
        const SizedBox(height: 20),
      ],
    );
  }

  Future<void> _confirmAndUndo(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Leave this party?'),
        content: const Text('You joined this party via Discover. Undoing will remove you from it.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Leave')),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(undoDiscoverActionProvider.notifier).undo(party.id);
      ref.read(selectedPartyIdProvider.notifier).state = null; // zurück zur Liste - Membership ist weg
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Failed to undo - please try again.')));
    }
  }
}

class _PartyHeader extends ConsumerWidget {
  final Party party;
  const _PartyHeader({required this.party});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Text(party.name, style: Theme.of(context).textTheme.titleLarge),
                ),
                IconButton(
                  icon: const Icon(Icons.edit),
                  onPressed: () => ref.read(editingPartyIdProvider.notifier).state = party.id,
                ),
              ],
            ),
            if (party.description.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(party.description),
            ],
            if (party.startsAt != null) ...[
              const SizedBox(height: 8),
              Text('When: ${party.startsAt}'),
            ],
            if (party.location.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('Where: ${party.location}'),
            ],
          ],
        ),
      ),
    );
  }
}

/// Host-only "Publish to Discover"-Sektion (siehe Discover-MVP-Plan) - nur
/// für den echten Host sichtbar (nicht Co-Hosts), da die Backend-Endpunkte
/// `POST/DELETE /parties/{id}/publish` und `POST /parties/{id}/cover-image`
/// mit `require_party_role({HOST})` streng host-only sind (403 für
/// Co-Hosts). Zeigt beim Aktivieren ein Event-Typ-Dropdown + Interest-Tag-
/// `FilterChip`-Wrap (aus den unauthentifizierten Katalog-Endpunkten) und
/// einen tippbaren Cover-Bild-Bereich, der den `image_picker`-Flow von
/// `_ProfileAvatarButton` spiegelt.
class _PublishToDiscoverSection extends ConsumerStatefulWidget {
  final Party party;
  const _PublishToDiscoverSection({required this.party});

  @override
  ConsumerState<_PublishToDiscoverSection> createState() => _PublishToDiscoverSectionState();
}

class _PublishToDiscoverSectionState extends ConsumerState<_PublishToDiscoverSection> {
  String? _eventType;
  late Set<String> _interestTags;
  late TextEditingController _maxGuestsController;
  bool _uploadingCover = false;

  @override
  void initState() {
    super.initState();
    _eventType = widget.party.eventType.isNotEmpty ? widget.party.eventType : null;
    _interestTags = widget.party.interestTags.toSet();
    _maxGuestsController = TextEditingController(text: widget.party.maxGuests.toString());
  }

  @override
  void didUpdateWidget(covariant _PublishToDiscoverSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.party.isPublished != widget.party.isPublished ||
        oldWidget.party.updatedAt != widget.party.updatedAt) {
      _eventType = widget.party.eventType.isNotEmpty ? widget.party.eventType : null;
      _interestTags = widget.party.interestTags.toSet();
      _maxGuestsController.text = widget.party.maxGuests.toString();
    }
  }

  @override
  void dispose() {
    _maxGuestsController.dispose();
    super.dispose();
  }

  int get _maxGuests => int.tryParse(_maxGuestsController.text) ?? 0;

  Future<void> _pickAndUploadCover() async {
    final source = await pickImageSource(context);
    if (source == null || !mounted) return;
    final picker = ImagePicker();
    final picked = await picker.pickImage(source: source, maxWidth: 1600, maxHeight: 1600);
    if (picked == null) return;
    setState(() => _uploadingCover = true);
    try {
      await ref.read(uploadPartyCoverImageProvider.notifier).upload(widget.party.id, File(picked.path));
      // Der Dateiname ist serverseitig fest ({party_id}.jpg, siehe
      // `parties.py::upload_party_cover_image`) - ohne Cache-Eviction würde
      // das alte Bild aus dem Flutter-`imageCache` weiterhin unter derselben
      // URL angezeigt und ein erfolgreicher Upload sähe wie ein no-op aus.
      final updated = ref.read(uploadPartyCoverImageProvider).value;
      if (updated != null && updated.coverImage.isNotEmpty) {
        imageCache.evict(NetworkImage('${ApiConfig.baseUrl}/media/${updated.coverImage}'));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Failed to upload cover image.')),
        );
      }
    } finally {
      if (mounted) setState(() => _uploadingCover = false);
    }
  }

  void _showPublishError(ScaffoldMessengerState messenger, Object e) {
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          e is ApiException && e.statusCode == 403
              ? 'Your account isn\'t verified yet - publishing is disabled until an admin verifies your account.'
              : 'Failed to update publish status.',
        ),
      ),
    );
  }

  Future<void> _togglePublished(bool value) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      if (value) {
        await ref.read(publishPartyProvider.notifier).publish(
              widget.party.id,
              eventType: _eventType ?? '',
              interestTags: _interestTags.toList(),
              maxGuests: _maxGuests,
            );
      } else {
        await ref.read(publishPartyProvider.notifier).unpublish(widget.party.id);
      }
    } catch (e) {
      _showPublishError(messenger, e);
    }
  }

  Future<void> _republish() async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(publishPartyProvider.notifier).publish(
            widget.party.id,
            eventType: _eventType ?? '',
            interestTags: _interestTags.toList(),
            maxGuests: _maxGuests,
          );
    } catch (e) {
      _showPublishError(messenger, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final currentUserAsync = ref.watch(currentUserProvider);
    final isHost = currentUserAsync.maybeWhen(
      data: (user) => user.id == widget.party.hostUserId,
      orElse: () => false,
    );
    if (!isHost) return const SizedBox.shrink();

    final eventCatalogAsync = ref.watch(eventInterestCatalogProvider);
    final tagCatalogAsync = ref.watch(interestTagCatalogProvider);
    final publishState = ref.watch(publishPartyProvider);
    final isPublished = widget.party.isPublished;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Publish to Discover'),
              subtitle: const Text('Let other users find and swipe on this party.'),
              value: isPublished,
              onChanged: (publishState.isLoading || !widget.party.hostIsVerified) ? null : _togglePublished,
            ),
            if (!widget.party.hostIsVerified) ...[
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(
                  'Your account isn\'t verified yet - publishing is disabled until an admin verifies your account.',
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            ],
            GestureDetector(
              onTap: _uploadingCover ? null : _pickAndUploadCover,
              child: Container(
                height: 120,
                width: double.infinity,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(12),
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  image: widget.party.coverImage.isNotEmpty
                      ? DecorationImage(
                          image: NetworkImage('${ApiConfig.baseUrl}/media/${widget.party.coverImage}'),
                          fit: BoxFit.cover,
                        )
                      : null,
                ),
                child: _uploadingCover
                    ? const Center(child: CircularProgressIndicator())
                    : widget.party.coverImage.isEmpty
                        ? const Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(Icons.add_photo_alternate_outlined, size: 32),
                                SizedBox(height: 4),
                                Text('Add cover image'),
                              ],
                            ),
                          )
                        : Align(
                            alignment: Alignment.bottomRight,
                            child: Padding(
                              padding: const EdgeInsets.all(8),
                              child: Icon(Icons.edit, color: Colors.white, shadows: [
                                Shadow(color: Colors.black.withValues(alpha: 0.6), blurRadius: 4),
                              ]),
                            ),
                          ),
              ),
            ),
            if (isPublished) ...[
              const SizedBox(height: 16),
              Text('Max guests (0 = unlimited)', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 8),
              TextFormField(
                controller: _maxGuestsController,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(border: OutlineInputBorder()),
                onFieldSubmitted: (_) => _republish(),
              ),
              const SizedBox(height: 16),
              Text('Event type', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 8),
              eventCatalogAsync.when(
                loading: () => const CircularProgressIndicator(),
                error: (err, st) => const Text('Failed to load event types.'),
                data: (catalog) => DropdownButton<String>(
                  isExpanded: true,
                  value: _eventType != null && catalog.any((c) => c.id == _eventType) ? _eventType : null,
                  hint: const Text('Select event type'),
                  items: catalog
                      .map((c) => DropdownMenuItem(value: c.id, child: Text(c.label('en'))))
                      .toList(),
                  onChanged: (value) {
                    setState(() => _eventType = value);
                    _republish();
                  },
                ),
              ),
              const SizedBox(height: 16),
              Text('Interest tags', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 8),
              tagCatalogAsync.when(
                loading: () => const CircularProgressIndicator(),
                error: (err, st) => const Text('Failed to load interest tags.'),
                data: (catalog) => Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: catalog
                      .map((tag) => FilterChip(
                            label: Text(tag.label('en')),
                            selected: _interestTags.contains(tag.id),
                            onSelected: (selected) {
                              setState(() {
                                if (selected) {
                                  _interestTags.add(tag.id);
                                } else {
                                  _interestTags.remove(tag.id);
                                }
                              });
                              _republish();
                            },
                          ))
                      .toList(),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _GuestsSection extends ConsumerWidget {
  final String partyId;
  const _GuestsSection({required this.partyId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final guestsAsync = ref.watch(partyGuestsProvider(partyId));

    return guestsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (err, st) {
        if (err is ApiException && err.statusCode == 403) {
          // Guest ohne Host-/Co-Host-Rolle: kein Fehler, nur eingeschränkte Sicht.
          return const SizedBox.shrink();
        }
        return Center(
          child: TextButton(
            onPressed: () => ref.invalidate(partyGuestsProvider(partyId)),
            child: const Text('Failed to load guest list. Retry'),
          ),
        );
      },
      data: (guests) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Align(
            alignment: Alignment.centerRight,
            child: ElevatedButton.icon(
              onPressed: () =>
                  ref.read(selectedAdminPartyIdProvider.notifier).state = partyId,
              icon: const Icon(Icons.settings),
              label: const Text('Verwalten'),
            ),
          ),
          const SizedBox(height: 16),
          _HostGuestsView(partyId: partyId, guests: guests),
        ],
      ),
    );
  }
}

class _HostGuestsView extends ConsumerStatefulWidget {
  final String partyId;
  final PartyGuestsResponse guests;
  const _HostGuestsView({required this.partyId, required this.guests});

  @override
  ConsumerState<_HostGuestsView> createState() => _HostGuestsViewState();
}

class _HostGuestsViewState extends ConsumerState<_HostGuestsView> {
  final _emailController = TextEditingController();
  String? _inviteError;

  @override
  void dispose() {
    _emailController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final inviteState = ref.watch(inviteGuestProvider);
    final isLoading = inviteState.isLoading;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Guests', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: widget.guests.counts.entries
              .map((e) => Chip(label: Text('${e.key}: ${e.value}')))
              .toList(),
        ),
        const SizedBox(height: 8),
        ...widget.guests.guests.map(
          (g) => ListTile(
            title: Text(g.displayName),
            subtitle: Text('${g.email} · ${g.role}'),
            trailing: Text(g.rsvpStatus),
          ),
        ),
        const SizedBox(height: 16),
        Text('Invite a guest', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        TextField(
          controller: _emailController,
          keyboardType: TextInputType.emailAddress,
          decoration: const InputDecoration(
            labelText: 'Guest email',
            border: OutlineInputBorder(),
          ),
        ),
        if (_inviteError != null) ...[
          const SizedBox(height: 8),
          Text(
            _inviteError!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ],
        const SizedBox(height: 8),
        ElevatedButton(
          onPressed: isLoading ? null : _submitInvite,
          child: isLoading
              ? const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Invite'),
        ),
      ],
    );
  }

  Future<void> _submitInvite() async {
    final email = _emailController.text.trim();
    if (email.isEmpty) {
      setState(() => _inviteError = 'Please enter an email address.');
      return;
    }
    setState(() => _inviteError = null);
    try {
      final invitation =
          await ref.read(inviteGuestProvider.notifier).invite(widget.partyId, invitedUserEmail: email);
      _emailController.clear();
      ref.invalidate(partyGuestsProvider(widget.partyId));
      await Share.share('You\'re invited! Open it here: partyplanning://invite/${invitation.id}');
    } catch (e) {
      setState(() {
        if (e is ApiException && e.statusCode == 404) {
          _inviteError = 'No account found for this email.';
        } else if (e is ApiException && e.statusCode == 409) {
          _inviteError = 'This person is already invited.';
        } else {
          _inviteError = 'Failed to invite. Please try again.';
        }
      });
    }
  }
}
