import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;

/// Backend-Basis-URL für die lokale FastAPI-Instanz (Phase 1,
/// `uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000`).
///
/// - Android-Emulator erreicht den Host-Rechner nicht über `localhost`,
///   sondern über den Alias `10.0.2.2` (offizielle Emulator-Konvention).
/// - iOS-Simulator und Web (Chrome) teilen sich den Netzwerk-Stack des
///   Host-Rechners, `localhost` funktioniert dort direkt.
/// - Ein echtes Gerät im selben WLAN braucht stattdessen die LAN-IP des
///   Rechners, der den Server laufen lässt (siehe Phase-1-Plan Schritt 5) -
///   dafür [override] verwenden statt diese Konstante zu ändern.
class ApiConfig {
  ApiConfig._();

  static String? _override;

  /// Erlaubt es, die Basis-URL zur Laufzeit zu setzen (z.B. aus einem
  /// Einstellungsbildschirm heraus, wenn ein echtes Gerät über die LAN-IP
  /// statt über den Emulator-Alias auf den Server zugreifen muss).
  static void override(String baseUrl) => _override = baseUrl;

  static String get baseUrl {
    if (_override != null) return _override!;
    if (kIsWeb) return 'http://localhost:8000';
    if (Platform.isAndroid) return 'http://10.0.2.2:8000';
    return 'http://localhost:8000';
  }
}
