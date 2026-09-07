import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/party.dart';
import '../state/auth_providers.dart';

// TODO(i18n): English-only strings for now, mirroring the deliberate Phase-3
// scope decision on the other screens.

/// Formular zum Bearbeiten der Party-Stammdaten (`PATCH /parties/{id}`,
/// bereits seit Phase 1 auf dem Backend vorhanden - dieser Screen ist reines
/// Flutter-Neuland, siehe Phase-5-Plan Part A).
class EditPartyScreen extends ConsumerStatefulWidget {
  final String partyId;
  const EditPartyScreen({super.key, required this.partyId});

  @override
  ConsumerState<EditPartyScreen> createState() => _EditPartyScreenState();
}

class _EditPartyScreenState extends ConsumerState<EditPartyScreen> {
  final _nameController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _locationController = TextEditingController();
  DateTime? _startsAt;
  bool _initialized = false;
  String? _error;

  @override
  void dispose() {
    _nameController.dispose();
    _descriptionController.dispose();
    _locationController.dispose();
    super.dispose();
  }

  void _initFromParty(Party party) {
    if (_initialized) return;
    _nameController.text = party.name;
    _descriptionController.text = party.description;
    _locationController.text = party.location;
    _startsAt = party.startsAt;
    _initialized = true;
  }

  @override
  Widget build(BuildContext context) {
    final partyAsync = ref.watch(partyDetailProvider(widget.partyId));
    final saveState = ref.watch(updatePartyProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Edit Party'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => ref.read(editingPartyIdProvider.notifier).state = null,
        ),
      ),
      body: partyAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(partyDetailProvider(widget.partyId)),
            child: const Text('Failed to load party. Retry'),
          ),
        ),
        data: (party) {
          _initFromParty(party);
          return SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextField(
                  controller: _nameController,
                  // Spiegelt das Backend-Limit (`_NAME_MAX_LENGTH` in
                  // `backend/app/schemas/accounts.py`), damit der Nutzer sofort
                  // sieht wann Schluss ist statt erst nach einem 422-Roundtrip.
                  maxLength: 200,
                  decoration: const InputDecoration(labelText: 'Name', border: OutlineInputBorder()),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _descriptionController,
                  decoration: const InputDecoration(labelText: 'Description', border: OutlineInputBorder()),
                  maxLines: 3,
                  maxLength: 5000,
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _locationController,
                  decoration: const InputDecoration(labelText: 'Location', border: OutlineInputBorder()),
                  maxLength: 300,
                ),
                const SizedBox(height: 12),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(_startsAt == null ? 'No date set' : 'When: $_startsAt'),
                  trailing: const Icon(Icons.calendar_today),
                  onTap: _pickDateTime,
                ),
                if (_error != null) ...[
                  const SizedBox(height: 8),
                  Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                ],
                const SizedBox(height: 16),
                ElevatedButton(
                  onPressed: saveState.isLoading ? null : _submit,
                  child: saveState.isLoading
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Save'),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Future<void> _pickDateTime() async {
    final now = DateTime.now();
    final date = await showDatePicker(
      context: context,
      initialDate: _startsAt ?? now,
      firstDate: now.subtract(const Duration(days: 365)),
      lastDate: now.add(const Duration(days: 365 * 3)),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(_startsAt ?? now),
    );
    if (time == null) return;
    setState(() {
      _startsAt = DateTime(date.year, date.month, date.day, time.hour, time.minute);
    });
  }

  Future<void> _submit() async {
    setState(() => _error = null);
    try {
      await ref.read(updatePartyProvider.notifier).save(
            widget.partyId,
            name: _nameController.text.trim(),
            description: _descriptionController.text.trim(),
            location: _locationController.text.trim(),
            startsAt: _startsAt,
          );
      if (!mounted) return;
      ref.read(editingPartyIdProvider.notifier).state = null;
    } catch (_) {
      setState(() => _error = 'Failed to save. Please try again.');
    }
  }
}
