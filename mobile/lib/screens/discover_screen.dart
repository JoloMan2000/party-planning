import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/discover_action_result.dart';
import '../models/discover_card.dart';
import '../state/auth_providers.dart';
import '../widgets/discover_card_view.dart';
import '../widgets/swipe_card_stack.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// "Discover Events"-Tab: Tinder-artiger Swipe-Stack über
/// `discoverDeckProvider`, plus Tap-Buttons für Barrierefreiheit (treiben
/// denselben `SwipeCardStackController`-Pfad wie eine echte Drag-Geste an -
/// siehe Discover-MVP-Plan). Bares Body-Widget, gehostet von `HomeShell`.
class DiscoverScreen extends ConsumerStatefulWidget {
  const DiscoverScreen({super.key});

  @override
  ConsumerState<DiscoverScreen> createState() => _DiscoverScreenState();
}

class _DiscoverScreenState extends ConsumerState<DiscoverScreen> {
  final _controller = SwipeCardStackController();

  @override
  Widget build(BuildContext context) {
    final deckAsync = ref.watch(discoverDeckProvider);

    return deckAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (err, st) => Center(
        child: TextButton(
          onPressed: () => ref.invalidate(discoverDeckProvider),
          child: const Text('Failed to load discover deck. Retry'),
        ),
      ),
      data: (cards) {
        if (cards.isEmpty) {
          return Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.explore_off, size: 48, color: Colors.grey),
                const SizedBox(height: 12),
                const Text('No new events to discover right now.'),
                const SizedBox(height: 12),
                TextButton(
                  onPressed: () => ref.invalidate(discoverDeckProvider),
                  child: const Text('Refresh'),
                ),
              ],
            ),
          );
        }
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Column(
            children: [
              Expanded(
                child: SwipeCardStack<DiscoverCard>(
                  items: cards,
                  controller: _controller,
                  cardBuilder: (context, card) => DiscoverCardView(card: card),
                  onSwiped: _onSwiped,
                  onDeckEmpty: () => ref.invalidate(discoverDeckProvider),
                ),
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  _actionButton(Icons.close, Colors.red, 'Not interested', _controller.swipeLeft),
                  _actionButton(Icons.question_mark, Colors.blue, 'Maybe', _controller.swipeUp),
                  _actionButton(Icons.favorite, Colors.green, 'Interested', _controller.swipeRight),
                ],
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _actionButton(IconData icon, Color color, String tooltip, VoidCallback onPressed) {
    return IconButton.filled(
      onPressed: onPressed,
      tooltip: tooltip,
      icon: Icon(icon),
      style: IconButton.styleFrom(
        backgroundColor: color.withValues(alpha: 0.15),
        foregroundColor: color,
        padding: const EdgeInsets.all(16),
      ),
    );
  }

  Future<void> _onSwiped(DiscoverCard card, SwipeDirection direction) async {
    final action = switch (direction) {
      SwipeDirection.right => 'going',
      SwipeDirection.up => 'maybe',
      SwipeDirection.left => 'not_interested',
    };
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(discoverActionProvider.notifier).act(card.partyId, action: action);
    } catch (_) {
      messenger.showSnackBar(
        const SnackBar(content: Text('Failed to record your swipe. Please try again.')),
      );
      return;
    }
    // Zero-Friction (Build-Schritt 3, siehe accounts/domain.py::DiscoverNotInterestedReason-
    // Docstring): der Swipe ist bereits gespeichert, der Reason-Picker ist rein
    // optionales Nachreichen - ein Dismiss ändert nichts am bereits erfolgten Swipe.
    if (direction == SwipeDirection.left && mounted) {
      await _promptForReason(card.partyId);
    }
  }

  Future<void> _promptForReason(String partyId) async {
    final reason = await showModalBottomSheet<DiscoverNotInterestedReason>(
      context: context,
      builder: (context) => _NotInterestedReasonSheet(),
    );
    if (reason == null || !mounted) return;
    try {
      await ref
          .read(discoverActionProvider.notifier)
          .act(partyId, action: 'not_interested', reason: reason.wireValue);
    } catch (_) {
      // Der Swipe selbst wurde bereits erfolgreich gespeichert - ein
      // fehlgeschlagener Reason-Nachtrag ist nicht kritisch genug für eine
      // SnackBar-Fehlermeldung, der User hat den Screen ohnehin schon verlassen.
    }
  }
}

class _NotInterestedReasonSheet extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Why not interested?',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 4),
            const Text('Optional - helps us show you better events.', textAlign: TextAlign.center),
            const SizedBox(height: 16),
            for (final reason in DiscoverNotInterestedReason.values)
              ListTile(
                title: Text(reason.label),
                onTap: () => Navigator.pop(context, reason),
              ),
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('Skip')),
          ],
        ),
      ),
    );
  }
}
