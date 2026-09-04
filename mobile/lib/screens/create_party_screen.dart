import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/auth_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Party-Erstellungsformular. Nach Erfolg landet der Nutzer direkt in
/// `PartyDetailScreen` (siehe `_submit`), nicht zurück in der Liste.
class CreatePartyScreen extends ConsumerStatefulWidget {
  const CreatePartyScreen({super.key});

  @override
  ConsumerState<CreatePartyScreen> createState() => _CreatePartyScreenState();
}

class _CreatePartyScreenState extends ConsumerState<CreatePartyScreen> {
  final _nameController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _locationController = TextEditingController();
  DateTime? _startsAt;
  String? _clientError;

  @override
  void dispose() {
    _nameController.dispose();
    _descriptionController.dispose();
    _locationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final createState = ref.watch(createPartyProvider);
    final isLoading = createState.isLoading;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Create Party'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => ref.read(creatingPartyProvider.notifier).state = false,
        ),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextField(
                controller: _nameController,
                autofocus: true,
                decoration: const InputDecoration(
                  labelText: 'Party name',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _descriptionController,
                maxLines: 3,
                decoration: const InputDecoration(
                  labelText: 'Description (optional)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _locationController,
                decoration: const InputDecoration(
                  labelText: 'Location (optional)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: _pickStartsAt,
                icon: const Icon(Icons.event),
                label: Text(
                  _startsAt == null ? 'Set date & time (optional)' : _startsAt.toString(),
                ),
              ),
              if (_clientError != null) ...[
                const SizedBox(height: 12),
                Text(
                  _clientError!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ] else if (createState.hasError) ...[
                const SizedBox(height: 12),
                Text(
                  'Failed to create party. Please try again.',
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 20),
              ElevatedButton(
                onPressed: isLoading ? null : _submit,
                child: isLoading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Create'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _pickStartsAt() async {
    final date = await showDatePicker(
      context: context,
      initialDate: DateTime.now(),
      firstDate: DateTime.now().subtract(const Duration(days: 1)),
      lastDate: DateTime.now().add(const Duration(days: 3650)),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(context: context, initialTime: TimeOfDay.now());
    if (time == null) return;
    setState(() {
      _startsAt = DateTime(date.year, date.month, date.day, time.hour, time.minute);
    });
  }

  Future<void> _submit() async {
    final name = _nameController.text.trim();
    setState(() {
      _clientError = name.isEmpty ? 'Please enter a party name.' : null;
    });
    if (_clientError != null) return;
    try {
      final party = await ref.read(createPartyProvider.notifier).create(
            name: name,
            description: _descriptionController.text.trim(),
            startsAt: _startsAt,
            location: _locationController.text.trim(),
          );
      ref.read(selectedPartyIdProvider.notifier).state = party.id;
      ref.read(creatingPartyProvider.notifier).state = false;
    } catch (_) {
      // error already reflected via createPartyProvider's AsyncError state
    }
  }
}
