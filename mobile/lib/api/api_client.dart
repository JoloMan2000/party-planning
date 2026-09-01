import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/admin_login_response.dart';
import '../models/catalog_item.dart';
import '../models/language_option.dart';
import '../models/party_info.dart';
import '../models/guest_response_draft.dart';
import 'api_config.dart';

/// Wird geworfen, wenn der Backend-Request mit einem Fehlerstatus antwortet.
class ApiException implements Exception {
  final int statusCode;
  final String message;

  ApiException(this.statusCode, this.message);

  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// Dünner HTTP-Client für die anonymen Gäste-Endpunkte des Phase-1-FastAPI-
/// Backends (`backend/app/routers/{guest,catalog,translations}.py`). Reine
/// Datenbeschaffung - keine Fachlogik, die bleibt vollständig im Backend
/// (party_engine/music_engine/party_context), mirroring der im Phase-1-Plan
/// festgelegten "Flutter ist ein reiner API-Konsument"-Regel.
class ApiClient {
  final http.Client _http;
  final String baseUrl;

  ApiClient({http.Client? httpClient, String? baseUrl})
      : _http = httpClient ?? http.Client(),
        baseUrl = baseUrl ?? ApiConfig.baseUrl;

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$baseUrl$path').replace(queryParameters: query);

  Map<String, dynamic> _decodeObject(http.Response resp) {
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  List<dynamic> _decodeList(http.Response resp) {
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as List<dynamic>;
  }

  Future<PartyInfo> getPartyInfo({String lang = 'de'}) async {
    final resp = await _http.get(_uri('/api/v1/guest/party-info', {'lang': lang}));
    return PartyInfo.fromJson(_decodeObject(resp));
  }

  Future<List<CatalogItem>> getDrinks({String lang = 'de'}) async {
    final resp = await _http.get(_uri('/api/v1/catalog/drinks', {'lang': lang}));
    return _decodeList(resp)
        .map((e) => CatalogItem.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  Future<List<CatalogItem>> getFood({String lang = 'de'}) async {
    final resp = await _http.get(_uri('/api/v1/catalog/food', {'lang': lang}));
    return _decodeList(resp)
        .map((e) => CatalogItem.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  Future<LanguagesResponse> getLanguages() async {
    final resp = await _http.get(_uri('/api/v1/translations/languages'));
    return LanguagesResponse.fromJson(_decodeObject(resp));
  }

  /// Vollständige `ui`-Übersetzungstabelle für [lang] (ein einziger Request,
  /// lokal wie `translations.t()` per Key nachschlagbar - siehe Docstring von
  /// `backend/app/routers/translations.py::get_translations_for_language`).
  Future<Map<String, String>> getTranslations(String lang) async {
    final resp = await _http.get(_uri('/api/v1/translations/$lang'));
    return _decodeObject(resp).map((key, value) => MapEntry(key, value as String));
  }

  Future<void> submitResponse(GuestResponseDraft draft) async {
    final resp = await _http.post(
      _uri('/api/v1/guest/responses'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(draft.toJson()),
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  /// Score-sortierte Item-IDs für die "empfohlen"-Hervorhebung im laufenden
  /// Wizard (mirroring `_guest_recommended_ids`).
  Future<List<String>> getRecommendations({
    required String name,
    required List<String> drinks,
    required List<String> food,
    int topN = 16,
  }) async {
    final resp = await _http.post(
      _uri('/api/v1/guest/recommendations'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name, 'drinks': drinks, 'food': food, 'top_n': topN}),
    );
    return _decodeList(resp).cast<String>();
  }

  /// Rohe ICS-Bytes für den Kalender-Export (Download/Teilen via
  /// `share_plus`). `null`, wenn die Party kein festes Datum hat (Backend
  /// antwortet dann mit 404, mirroring `calendar_export.has_scheduled_date`).
  Future<List<int>?> getCalendarIcs() async {
    final resp = await _http.get(_uri('/api/v1/guest/calendar.ics'));
    if (resp.statusCode == 404) return null;
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return resp.bodyBytes;
  }

  /// Admin-Login (`backend/app/routers/auth.py::admin_login`). Liefert bei
  /// falschem Passwort eine [ApiException] mit statusCode 401.
  Future<AdminLoginResponse> adminLogin(String password) async {
    final resp = await _http.post(
      _uri('/api/v1/auth/admin/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'password': password}),
    );
    return AdminLoginResponse.fromJson(_decodeObject(resp));
  }

  void close() => _http.close();
}
