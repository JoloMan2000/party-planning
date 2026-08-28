import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Liest die Party-Theme-Farben aus dem `theme`-Feld von
/// `GET /api/v1/guest/party-info` (mirroring `event_theme.EVENT_TYPES[...]`,
/// siehe `event_theme.py`: `hero_gradient` = 3 Farben für den 135°-Hero-
/// Verlauf, `accent_gradient` = 2 Farben für Buttons). Fällt auf das
/// Default-Bauwagen-Theme zurück, falls das Feld fehlt/leer ist (z.B. bevor
/// die erste API-Antwort geladen ist).
class PartyColors {
  final List<Color> heroGradient;
  final List<Color> accentGradient;

  const PartyColors({required this.heroGradient, required this.accentGradient});

  static const _defaultHero = ['#3F2E22', '#4A342A', '#3F5B41'];
  static const _defaultAccent = ['#C68642', '#A8672F'];

  factory PartyColors.fromThemeJson(Map<String, dynamic>? theme) {
    final heroRaw = (theme?['hero_gradient'] as List?)?.cast<String>() ?? _defaultHero;
    final accentRaw = (theme?['accent_gradient'] as List?)?.cast<String>() ?? _defaultAccent;
    return PartyColors(
      heroGradient: heroRaw.map(_parseHex).toList(),
      accentGradient: accentRaw.map(_parseHex).toList(),
    );
  }

  static Color _parseHex(String hex) {
    final cleaned = hex.replaceFirst('#', '');
    return Color(int.parse('FF$cleaned', radix: 16));
  }

  LinearGradient get heroLinearGradient => LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: heroGradient,
      );

  LinearGradient get accentLinearGradient => LinearGradient(colors: accentGradient);
}

/// App-weites `ThemeData` mirroring `inject_theme()`'s CSS (Fraunces für
/// Überschriften, Inter für Fließtext, warmer Creme-Hintergrund, abgerundete
/// Pill-Buttons im Akzentverlauf).
ThemeData buildAppTheme(PartyColors colors) {
  final accent = colors.accentGradient.first;
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(seedColor: accent, brightness: Brightness.light),
    scaffoldBackgroundColor: const Color(0xFFF7F1E3),
    textTheme: GoogleFonts.interTextTheme(),
  );
  return base.copyWith(
    textTheme: base.textTheme.copyWith(
      headlineSmall: GoogleFonts.fraunces(
        fontWeight: FontWeight.w800,
        color: const Color(0xFF3F2E22),
      ),
      titleLarge: GoogleFonts.fraunces(
        fontWeight: FontWeight.w700,
        color: const Color(0xFF3F2E22),
      ),
      titleMedium: GoogleFonts.fraunces(
        fontWeight: FontWeight.w700,
        color: const Color(0xFF3F2E22),
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: accent,
        foregroundColor: const Color(0xFFFBF3E3),
        shape: const StadiumBorder(),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
        textStyle: GoogleFonts.inter(fontWeight: FontWeight.w600),
      ),
    ),
    cardTheme: CardThemeData(
      color: Colors.white.withValues(alpha: 0.55),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      elevation: 0,
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: Color(0xFF3F5B41)),
  );
}
