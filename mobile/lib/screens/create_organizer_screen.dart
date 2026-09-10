import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/organizer_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Formular zum Anlegen eines Organizers (Social-Graph-Phase-4). Struktureller
/// Klon von `CreatePartyScreen`: Client-Validierung in `_clientError`,
/// `await notifier.create(...)` liefert die neue Entität, danach
/// `creatingOrganizerProvider = false` + Routing in den Detail-Screen über
/// `selectedOrganizerIdProvider`. Jeder eingeloggte User darf (self-serve);
/// der Ersteller wird automatisch `OWNER`.
class CreateOrganizerScreen extends ConsumerStatefulWidget {
  const CreateOrganizerScreen({super.key});

  @override
  ConsumerState<CreateOrganizerScreen> createState() => _CreateOrganizerScreenState();
}

class _CreateOrganizerScreenState extends ConsumerState<CreateOrganizerScreen> {
  final _displayNameController = TextEditingController();
  final _organizerTypeController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _websiteController = TextEditingController();
  String? _clientError;

  @override
  void dispose() {
    _displayNameController.dispose();
    _organizerTypeController.dispose();
    _descriptionController.dispose();
    _websiteController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final name = _displayNameController.text.trim();
    setState(() {
      _clientError = name.isEmpty ? 'Please enter an organizer name.' : null;
    });
    if (_clientError != null) return;
    try {
      final organizer = await ref.read(createOrganizerProvider.notifier).create(
            displayName: name,
            organizerType: _organizerTypeController.text.trim(),
            description: _descriptionController.text.trim(),
            websiteUrl: _websiteController.text.trim(),
          );
      ref.read(creatingOrganizerProvider.notifier).state = false;
      ref.read(selectedOrganizerIdProvider.notifier).state = organizer.id;
    } catch (_) {
      // Fehler wird über createOrganizerProvider's AsyncError-State angezeigt.
    }
  }

  @override
  Widget build(BuildContext context) {
    final createState = ref.watch(createOrganizerProvider);
    final isLoading = createState.isLoading;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Create Organizer'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => ref.read(creatingOrganizerProvider.notifier).state = false,
        ),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextField(
                controller: _displayNameController,
                autofocus: true,
                maxLength: 200,
                decoration: const InputDecoration(
                  labelText: 'Organizer name',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _organizerTypeController,
                decoration: const InputDecoration(
                  labelText: 'Type (optional)',
                  hintText: 'e.g. club, promoter, venue',
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
                controller: _websiteController,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  labelText: 'Website (optional)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              if (_clientError != null)
                Text(_clientError!, style: TextStyle(color: Theme.of(context).colorScheme.error))
              else if (createState.hasError)
                Text(
                  'Failed to create organizer. Please try again.',
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: isLoading ? null : _submit,
                child: isLoading
                    ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Create'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
