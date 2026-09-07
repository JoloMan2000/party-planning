import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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
    }
  }
}
