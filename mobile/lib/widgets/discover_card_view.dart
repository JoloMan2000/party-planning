import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api/api_config.dart';
import '../models/discover_card.dart';
import '../state/auth_providers.dart';

// TODO(i18n): English-only strings for now, deliberately deferred per Phase-3
// scope decision (translations live in the backend-served `translations.py`
// catalog, out of scope for this Flutter-only phase).

/// Dating-Profil-artige Darstellung einer [DiscoverCard] - Cover-Bild
/// full-bleed mit Gradient-Scrim + Party-Name/Where-When-What, gestylt nach
/// dem bestehenden `party_theme.dart`-Farb-/Rundungssystem (siehe
/// Discover-MVP-Plan, Swipe-UI-Entscheidung).
class DiscoverCardView extends ConsumerWidget {
  final DiscoverCard card;
  const DiscoverCardView({super.key, required this.card});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final eventTypeLabel = ref.watch(eventInterestCatalogProvider).maybeWhen(
          data: (catalog) {
            final match = catalog.where((c) => c.id == card.eventType);
            return match.isEmpty ? card.eventType : match.first.label('en');
          },
          orElse: () => card.eventType,
        );

    return ClipRRect(
      borderRadius: BorderRadius.circular(24),
      child: SizedBox.expand(
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (card.coverImage.isNotEmpty)
              Image.network(
                '${ApiConfig.baseUrl}/media/${card.coverImage}',
                fit: BoxFit.cover,
                errorBuilder: (context, error, stackTrace) => _placeholder(),
              )
            else
              _placeholder(),
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Colors.transparent, Colors.black.withValues(alpha: 0.85)],
                  stops: const [0.4, 1.0],
                ),
              ),
            ),
            Positioned(
              left: 20,
              right: 20,
              bottom: 20,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    card.name,
                    style: GoogleFonts.fraunces(
                      fontSize: 26,
                      fontWeight: FontWeight.w800,
                      color: Colors.white,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 8),
                  if (card.location.isNotEmpty) _infoRow(Icons.location_on, card.location),
                  if (card.startsAt != null) _infoRow(Icons.event, card.startsAt.toString()),
                  if (eventTypeLabel.isNotEmpty) _infoRow(Icons.category, eventTypeLabel),
                  if (card.hostDisplayName.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Text(
                      'Hosted by ${card.hostDisplayName}',
                      style: const TextStyle(color: Colors.white70, fontSize: 13),
                    ),
                  ],
                  if (card.why.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    // Build-Schritt 7 (Explainability) - "Why this event?",
                    // keine versteckte Black Box (siehe accounts/discover_ranking.py::explain_candidate).
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.lightbulb_outline, size: 14, color: Colors.white),
                          const SizedBox(width: 6),
                          Flexible(
                            child: Text(
                              card.why,
                              style: const TextStyle(color: Colors.white, fontSize: 12),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _infoRow(IconData icon, String text) => Padding(
        padding: const EdgeInsets.only(top: 4),
        child: Row(
          children: [
            Icon(icon, size: 16, color: Colors.white70),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                text,
                style: const TextStyle(color: Colors.white, fontSize: 14),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      );

  Widget _placeholder() => Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF3F5B41), Color(0xFFC68642)],
          ),
        ),
        child: const Center(
          child: Icon(Icons.celebration, size: 72, color: Colors.white54),
        ),
      );
}
