import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/party_theme.dart';

/// Der Hero-Header, mirroring `render_hero()`/`.party-hero` aus
/// `inject_theme()`: Titel (Fraunces, groß), Untertitel, optionale
/// sprachneutrale Meta-Zeile (Datum/Uhrzeit der Party).
class PartyHero extends StatelessWidget {
  final String title;
  final String subtitle;
  final String? meta;
  final PartyColors colors;

  const PartyHero({
    super.key,
    required this.title,
    required this.subtitle,
    required this.colors,
    this.meta,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(24, 38, 24, 34),
      decoration: BoxDecoration(
        gradient: colors.heroLinearGradient,
        borderRadius: BorderRadius.circular(22),
        boxShadow: const [
          BoxShadow(color: Color(0x593F2E22), blurRadius: 40, offset: Offset(0, 16)),
        ],
      ),
      child: Column(
        children: [
          Text(
            title,
            textAlign: TextAlign.center,
            style: GoogleFonts.fraunces(
              fontWeight: FontWeight.w800,
              fontSize: 28,
              color: const Color(0xFFFBF3E3),
            ),
          ),
          const SizedBox(height: 10),
          Text(
            subtitle,
            textAlign: TextAlign.center,
            style: GoogleFonts.inter(
              fontWeight: FontWeight.w500,
              fontSize: 16,
              color: const Color(0xFFE4DAC4),
            ),
          ),
          if (meta != null && meta!.isNotEmpty) ...[
            const SizedBox(height: 14),
            Text(
              meta!,
              textAlign: TextAlign.center,
              style: GoogleFonts.inter(
                fontWeight: FontWeight.w600,
                fontSize: 13,
                color: const Color(0xFFFBF3E3),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
