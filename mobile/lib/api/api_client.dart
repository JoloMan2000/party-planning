import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';

import '../models/admin_recommendation.dart';
import '../models/app_notification.dart';
import '../models/auth_token_response.dart';
import '../models/catalog_curation_settings.dart';
import '../models/catalog_item.dart';
import '../models/derived_party_context.dart';
import '../models/discover_action_result.dart';
import '../models/discover_card.dart';
import '../models/discovery_catalog_item.dart';
import '../models/discovery_preferences.dart';
import '../models/event_type.dart';
import '../models/guest_response.dart';
import '../models/invitation.dart';
import '../models/language_option.dart';
import '../models/music_admin_settings.dart';
import '../models/music_planning_result.dart';
import '../models/notification_settings.dart';
import '../models/party.dart';
import '../geo/geo_models.dart';
import '../models/party_context.dart';
import '../models/party_context_override.dart';
import '../models/party_demand_result.dart';
import '../models/party_guests_response.dart';
import '../models/party_info.dart';
import '../models/party_settings.dart';
import '../models/guest_response_draft.dart';
import '../models/profile.dart';
import '../models/rsvp_response.dart';
import '../models/spotify_status.dart';
import '../models/co_host_promote_result.dart';
import '../models/followed_event.dart';
import '../models/follow_status.dart';
import '../models/friend.dart';
import '../models/friend_invite_result.dart';
import '../models/friend_request.dart';
import '../models/organizer.dart';
import '../models/organizer_member.dart';
import '../models/search_results.dart';
import '../models/social_privacy.dart';
import '../models/social_profile.dart';
import '../models/user_search_result.dart';
import '../models/user_account.dart';
import 'api_config.dart';

/// Wird geworfen, wenn der Backend-Request mit einem Fehlerstatus antwortet.
class ApiException implements Exception {
  final int statusCode;
  final String message;

  ApiException(this.statusCode, this.message);

  /// Best-effort JSON-decodierter `detail`-Wert aus [message] (FastAPI packt
  /// `HTTPException(detail=...)` immer unter diesem Key, teils als String,
  /// teils als Objekt, z.B. `{"message": ..., "current_version": ...}` beim
  /// RSVP-409). `null`, wenn [message] kein valides JSON ist.
  dynamic get detail {
    try {
      final decoded = jsonDecode(message);
      if (decoded is Map<String, dynamic>) return decoded['detail'];
      return null;
    } catch (_) {
      return null;
    }
  }

  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// Erzwingt ein Timeout auf jedem Request (`http.Client()` hat sonst KEINEN
/// Default-Timeout - ein totes/hängendes Netzwerk würde Ladeindikatoren sonst
/// unbegrenzt weiterlaufen lassen). Wraps [inner] statt es zu ersetzen, damit
/// injizierte Test-`http.Client`s (z.B. `MockClient`) weiterhin funktionieren.
class _TimeoutClient extends http.BaseClient {
  final http.Client _inner;
  final Duration _timeout;

  _TimeoutClient(this._inner, this._timeout);

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    return _inner.send(request).timeout(_timeout);
  }

  @override
  void close() => _inner.close();
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
      : _http = _TimeoutClient(httpClient ?? http.Client(), const Duration(seconds: 20)),
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

  Future<PartyInfo> getPartyInfo(String partyId, {String lang = 'de'}) async {
    final resp = await _http.get(_uri('/api/v1/guest/$partyId/party-info', {'lang': lang}));
    return PartyInfo.fromJson(_decodeObject(resp));
  }

  Future<List<CatalogItem>> getDrinks(String partyId, {String lang = 'de'}) async {
    final resp = await _http.get(_uri('/api/v1/guest/$partyId/catalog/drinks', {'lang': lang}));
    return _decodeList(resp)
        .map((e) => CatalogItem.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  Future<List<CatalogItem>> getFood(String partyId, {String lang = 'de'}) async {
    final resp = await _http.get(_uri('/api/v1/guest/$partyId/catalog/food', {'lang': lang}));
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

  Future<void> submitResponse(String partyId, GuestResponseDraft draft) async {
    final resp = await _http.post(
      _uri('/api/v1/guest/$partyId/responses'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(draft.toJson()),
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  /// Score-sortierte Item-IDs für die "empfohlen"-Hervorhebung im laufenden
  /// Wizard (mirroring `_guest_recommended_ids`).
  Future<List<String>> getRecommendations(
    String partyId, {
    required String name,
    required List<String> drinks,
    required List<String> food,
    int topN = 16,
  }) async {
    final resp = await _http.post(
      _uri('/api/v1/guest/$partyId/recommendations'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name, 'drinks': drinks, 'food': food, 'top_n': topN}),
    );
    return _decodeList(resp).cast<String>();
  }

  /// Rohe ICS-Bytes für den Kalender-Export (Download/Teilen via
  /// `share_plus`). `null`, wenn die Party kein festes Datum hat (Backend
  /// antwortet dann mit 404, mirroring `calendar_export.has_scheduled_date`).
  Future<List<int>?> getCalendarIcs(String partyId) async {
    final resp = await _http.get(_uri('/api/v1/guest/$partyId/calendar.ics'));
    if (resp.statusCode == 404) return null;
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return resp.bodyBytes;
  }

  Map<String, String> _authHeaders(String token) => {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      };

  /// Alle wählbaren Event-Typen fürs Party-Settings-Dropdown
  /// (`admin_party_settings.py::get_event_types`).
  Future<List<EventType>> getEventTypes(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(
        _uri('/api/v1/parties/$partyId/admin/party-settings/event-types'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return _decodeList(resp)
        .map((e) => EventType.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  Future<PartySettings> getPartySettings(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(
        _uri('/api/v1/parties/$partyId/admin/party-settings'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return PartySettings.fromJson(_decodeObject(resp));
  }

  /// Speichert die Party-Settings, liefert `reset_happened` zurück (mirroring
  /// des Lifecycle-Trigger-Hinweises in `render_party_settings_section`).
  Future<bool> savePartySettings(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
    PartySettings settings,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/parties/$partyId/admin/party-settings'),
        headers: _authHeaders(token),
        body: jsonEncode(settings.toJson()),
      ),
      accessToken,
      onRefresh,
    );
    final body = _decodeObject(resp);
    return body['reset_happened'] as bool? ?? false;
  }

  /// Stammdaten fürs Party-Kontext-Formular (Location-Typen, Länderliste -
  /// `admin_party_context.py::get_party_context_metadata`).
  Future<PartyContextMetadata> getPartyContextMetadata(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(
        _uri('/api/v1/parties/$partyId/admin/party-context/metadata'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return PartyContextMetadata.fromJson(_decodeObject(resp));
  }

  Future<PartyContext> getPartyContext(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(
        _uri('/api/v1/parties/$partyId/admin/party-context'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return PartyContext.fromJson(_decodeObject(resp));
  }

  Future<void> savePartyContext(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
    PartyContext context,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/parties/$partyId/admin/party-context'),
        headers: _authHeaders(token),
        body: jsonEncode(context.toJson()),
      ),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<MusicAdminSettings> getMusicSettings(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(
        _uri('/api/v1/parties/$partyId/admin/music/settings'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return MusicAdminSettings.fromJson(_decodeObject(resp));
  }

  Future<void> saveMusicSettings(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
    MusicAdminSettings settings,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/parties/$partyId/admin/music/settings'),
        headers: _authHeaders(token),
        body: jsonEncode(settings.toJson()),
      ),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<MusicPlanningResult> generateMusicPlaylist(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/parties/$partyId/admin/music/generate-playlist'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return MusicPlanningResult.fromJson(_decodeObject(resp));
  }

  Future<CatalogCurationSettings> getCatalogCurationSettings(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(
        _uri('/api/v1/parties/$partyId/admin/catalog-curation'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return CatalogCurationSettings.fromJson(_decodeObject(resp));
  }

  Future<void> saveCatalogCurationSettings(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
    bool enabled,
    List<String> curatedItemIds,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/parties/$partyId/admin/catalog-curation'),
        headers: _authHeaders(token),
        body: jsonEncode({'enabled': enabled, 'curated_item_ids': curatedItemIds}),
      ),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<CuratableCatalog> getCuratableCatalog(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh, {
    String lang = 'de',
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(
        _uri('/api/v1/parties/$partyId/admin/catalog-curation/items', {'lang': lang}),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return CuratableCatalog.fromJson(_decodeObject(resp));
  }

  Future<AdminRecommendationsResponse> getAdminRecommendations(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(
        _uri('/api/v1/parties/$partyId/admin/recommendations'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return AdminRecommendationsResponse.fromJson(_decodeObject(resp));
  }

  Future<DerivedPartyContext> getDerivedPartyContext(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(
        _uri('/api/v1/parties/$partyId/admin/party-context/derived'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return DerivedPartyContext.fromJson(_decodeObject(resp));
  }

  Future<List<PartyContextOverride>> getPartyContextOverrides(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(
        _uri('/api/v1/parties/$partyId/admin/party-context/overrides'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return _decodeList(resp)
        .map((e) => PartyContextOverride.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  Future<void> addPartyContextOverride(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
    String key,
    String value,
    String? reason,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/parties/$partyId/admin/party-context/overrides'),
        headers: _authHeaders(token),
        body: jsonEncode({'key': key, 'value': value, 'reason': reason}),
      ),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<void> deletePartyContextOverride(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
    String key,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.delete(
        _uri('/api/v1/parties/$partyId/admin/party-context/overrides/$key'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  /// Gespeicherte Gäste-Antworten inkl. vorformatierter Anzeige-Felder
  /// (mirroring `raw_responses_expander`).
  Future<List<GuestResponse>> getResponses(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh, {
    String lang = 'de',
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(
        _uri('/api/v1/parties/$partyId/admin/responses', {'lang': lang}),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return _decodeList(resp)
        .map((e) => GuestResponse.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  /// Rohe CSV-Bytes für den Antworten-Export (Download/Teilen via
  /// `share_plus`, mirroring `btn_csv`).
  Future<List<int>> getResponsesCsv(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(
        _uri('/api/v1/parties/$partyId/admin/responses/csv'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return resp.bodyBytes;
  }

  /// Einkaufsliste (Unified Demand Pipeline, mirroring `render_shopping_list`).
  Future<PartyDemandResult> computeShoppingList(
    String partyId,
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/parties/$partyId/admin/shopping-list'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return PartyDemandResult.fromJson(_decodeObject(resp));
  }

  // ---------------------------------------------------------------------
  // Account-basierter Auth-/Party-/Invitation-Flow (Phase 3). `ApiClient`
  // bleibt bewusst speicher-agnostisch (siehe Admin-Token-Handling oben) -
  // Tokens werden vom Aufrufer (`AuthNotifier`) übergeben, nie selbst aus
  // `flutter_secure_storage` gelesen.
  // ---------------------------------------------------------------------

  /// Führt [request] mit [accessToken] aus; bei 401 wird [onRefresh] genau
  /// einmal aufgerufen (liefert das neue Access-Token oder `null` bei
  /// gescheitertem Refresh), der Request dann genau einmal wiederholt.
  /// Liefert weiterhin die 401-Antwort, wenn [onRefresh] fehlschlägt - der
  /// Aufrufer (State-Layer) ist dafür verantwortlich, das als "muss neu
  /// einloggen" zu behandeln (siehe `AuthNotifier.refreshAndPersist`).
  Future<http.Response> _authorizedRequest(
    Future<http.Response> Function(String accessToken) request,
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    var resp = await request(accessToken);
    if (resp.statusCode == 401) {
      final newToken = await onRefresh();
      if (newToken != null) {
        resp = await request(newToken);
      }
    }
    return resp;
  }

  Future<AuthTokenResponse> signup({
    required String email,
    required String password,
    required String displayName,
  }) async {
    final resp = await _http.post(
      _uri('/api/v1/auth/signup'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password, 'display_name': displayName}),
    );
    return AuthTokenResponse.fromJson(_decodeObject(resp));
  }

  Future<AuthTokenResponse> login({required String email, required String password}) async {
    final resp = await _http.post(
      _uri('/api/v1/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );
    return AuthTokenResponse.fromJson(_decodeObject(resp));
  }

  /// Bewusst NICHT über [_authorizedRequest] geführt - der Refresh selbst
  /// ist das, was bei einem 401 passiert; ihn zu wrappen wäre zirkulär.
  Future<AuthTokenResponse> refreshTokens(String refreshToken) async {
    final resp = await _http.post(
      _uri('/api/v1/auth/refresh'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'refresh_token': refreshToken}),
    );
    return AuthTokenResponse.fromJson(_decodeObject(resp));
  }

  Future<void> logout(String refreshToken) async {
    await _http.post(
      _uri('/api/v1/auth/logout'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'refresh_token': refreshToken}),
    );
  }

  /// Löst immer denselben generischen Erfolg aus, egal ob die E-Mail
  /// existiert (siehe `backend/app/routers/auth.py::request_password_reset`)
  /// - der Response-Body wird bewusst verworfen, es gibt nichts Nutzbares
  /// darin außer der immer gleichen `message`.
  Future<void> requestPasswordReset({required String email}) async {
    final resp = await _http.post(
      _uri('/api/v1/auth/request-password-reset'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email}),
    );
    _decodeObject(resp);
  }

  Future<void> resetPassword({required String token, required String newPassword}) async {
    final resp = await _http.post(
      _uri('/api/v1/auth/reset-password'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'token': token, 'new_password': newPassword}),
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<void> verifyEmail({required String token}) async {
    final resp = await _http.post(
      _uri('/api/v1/auth/verify-email'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'token': token}),
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<void> resendVerificationEmail(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(_uri('/api/v1/auth/resend-verification-email'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  /// Löst immer denselben generischen Erfolg aus, egal ob die E-Mail
  /// existiert (siehe `backend/app/routers/auth.py::request_account_unlock`).
  Future<void> requestAccountUnlock({required String email}) async {
    final resp = await _http.post(
      _uri('/api/v1/auth/request-account-unlock'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email}),
    );
    _decodeObject(resp);
  }

  Future<void> unlockAccount({required String token}) async {
    final resp = await _http.post(
      _uri('/api/v1/auth/unlock-account'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'token': token}),
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<UserAccount> getMe(String accessToken, Future<String?> Function() onRefresh) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/me'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return UserAccount.fromJson(_decodeObject(resp));
  }

  Future<List<Party>> getMyParties(String accessToken, Future<String?> Function() onRefresh) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/me/parties'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return _decodeList(resp).map((e) => Party.fromJson((e as Map).cast<String, dynamic>())).toList();
  }

  Future<List<Invitation>> getMyInvitations(String accessToken, Future<String?> Function() onRefresh) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/me/invitations'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return _decodeList(resp).map((e) => Invitation.fromJson((e as Map).cast<String, dynamic>())).toList();
  }

  Future<Party> createParty(
    String accessToken,
    Future<String?> Function() onRefresh, {
    required String name,
    String description = '',
    DateTime? startsAt,
    String location = '',
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/parties'),
        headers: _authHeaders(token),
        body: jsonEncode({
          'name': name,
          'description': description,
          'starts_at': startsAt?.toIso8601String(),
          'location': location,
        }),
      ),
      accessToken,
      onRefresh,
    );
    return Party.fromJson(_decodeObject(resp));
  }

  Future<Party> getParty(String accessToken, Future<String?> Function() onRefresh, String partyId) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/parties/$partyId'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return Party.fromJson(_decodeObject(resp));
  }

  Future<Party> updateParty(
    String accessToken,
    Future<String?> Function() onRefresh,
    String partyId, {
    String? name,
    String? description,
    DateTime? startsAt,
    String? location,
  }) async {
    final body = <String, dynamic>{};
    if (name != null) body['name'] = name;
    if (description != null) body['description'] = description;
    if (startsAt != null) body['starts_at'] = startsAt.toIso8601String();
    if (location != null) body['location'] = location;
    final resp = await _authorizedRequest(
      (token) => _http.patch(
        _uri('/api/v1/parties/$partyId'),
        headers: _authHeaders(token),
        body: jsonEncode(body),
      ),
      accessToken,
      onRefresh,
    );
    return Party.fromJson(_decodeObject(resp));
  }

  Future<PartyGuestsResponse> getPartyGuests(
    String accessToken,
    Future<String?> Function() onRefresh,
    String partyId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/parties/$partyId/guests'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return PartyGuestsResponse.fromJson(_decodeObject(resp));
  }

  Future<Invitation> inviteGuest(
    String accessToken,
    Future<String?> Function() onRefresh,
    String partyId, {
    required String invitedUserEmail,
    String invitationMessage = '',
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/parties/$partyId/invitations'),
        headers: _authHeaders(token),
        body: jsonEncode({'invited_user_email': invitedUserEmail, 'invitation_message': invitationMessage}),
      ),
      accessToken,
      onRefresh,
    );
    return Invitation.fromJson(_decodeObject(resp));
  }

  /// Social-Graph-Phase-2: Batch-Einladung aus dem Freundeskreis - ein
  /// schlechter Eintrag bricht den Batch nicht ab, siehe
  /// `FriendInviteResponse`/`backend/app/routers/parties.py::invite_friends`.
  Future<FriendInviteResponse> inviteFriends(
    String accessToken,
    Future<String?> Function() onRefresh,
    String partyId, {
    required List<String> friendUserIds,
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/parties/$partyId/invitations/friends'),
        headers: _authHeaders(token),
        body: jsonEncode({'friend_user_ids': friendUserIds}),
      ),
      accessToken,
      onRefresh,
    );
    return FriendInviteResponse.fromJson(_decodeObject(resp));
  }

  /// Social-Graph-Phase-2: befördert einen bereits akzeptierten Gast zum
  /// Co-Host - host-exklusiv (siehe
  /// `backend/app/routers/parties.py::promote_co_host`).
  Future<CoHostPromoteResult> promoteCoHost(
    String accessToken,
    Future<String?> Function() onRefresh,
    String partyId, {
    required String userId,
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/parties/$partyId/co-hosts'),
        headers: _authHeaders(token),
        body: jsonEncode({'user_id': userId}),
      ),
      accessToken,
      onRefresh,
    );
    return CoHostPromoteResult.fromJson(_decodeObject(resp));
  }

  Future<Invitation> getInvitation(
    String accessToken,
    Future<String?> Function() onRefresh,
    String invitationId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/invitations/$invitationId'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return Invitation.fromJson(_decodeObject(resp));
  }

  Future<RsvpResponse> rsvp(
    String accessToken,
    Future<String?> Function() onRefresh,
    String invitationId, {
    required String status,
    required int version,
    String? clientRequestId,
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.put(
        _uri('/api/v1/invitations/$invitationId/rsvp'),
        headers: _authHeaders(token),
        body: jsonEncode({
          'status': status,
          'version': version,
          'client_request_id': ?clientRequestId,
        }),
      ),
      accessToken,
      onRefresh,
    );
    return RsvpResponse.fromJson(_decodeObject(resp));
  }

  Future<List<AppNotification>> getNotifications(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/me/notifications'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return _decodeList(resp)
        .map((e) => AppNotification.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  Future<AppNotification> markNotificationRead(
    String accessToken,
    Future<String?> Function() onRefresh,
    String notificationId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/me/notifications/$notificationId/read'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return AppNotification.fromJson(_decodeObject(resp));
  }

  /// Multipart-Upload fürs Profilbild (`POST /me/profile-image`) - fließt
  /// trotz abweichender Request-Bauart (`http.MultipartRequest` statt
  /// `_http.post`) durch denselben 401-Retry-Wrapper wie jeder andere
  /// authentifizierte Call, damit ein abgelaufenes Access-Token hier genauso
  /// automatisch erneuert wird.
  Future<UserAccount> uploadProfileImage(
    String accessToken,
    Future<String?> Function() onRefresh,
    File imageFile,
  ) async {
    Future<http.Response> sendWith(String token) async {
      final request = http.MultipartRequest('POST', _uri('/api/v1/me/profile-image'))
        ..headers['Authorization'] = 'Bearer $token'
        ..files.add(await http.MultipartFile.fromPath('file', imageFile.path));
      final streamedResponse = await _http.send(request);
      return http.Response.fromStream(streamedResponse);
    }

    final resp = await _authorizedRequest(sendWith, accessToken, onRefresh);
    return UserAccount.fromJson(_decodeObject(resp));
  }

  // ---------------------------------------------------------------------
  // Discover-Events-MVP (dritter Bottom-Nav-Tab) - Swipe-Deck über bereits
  // existierende, vom Host veröffentlichte Parties. Getrennt vom
  // Einladungs-/RSVP-Flow oben (siehe `backend/app/routers/discover.py`).
  // ---------------------------------------------------------------------

  Future<List<DiscoverCard>> getDiscoverDeck(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/discover/deck'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    final body = _decodeObject(resp);
    return (body['cards'] as List)
        .map((e) => DiscoverCard.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  Future<DiscoverActionResult> postDiscoverAction(
    String accessToken,
    Future<String?> Function() onRefresh,
    String partyId, {
    required String action,
    String? reason,
  }) async {
    final body = <String, dynamic>{'action': action};
    if (reason != null) body['reason'] = reason;
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/discover/$partyId/action'),
        headers: _authHeaders(token),
        body: jsonEncode(body),
      ),
      accessToken,
      onRefresh,
    );
    return DiscoverActionResult.fromJson(_decodeObject(resp));
  }

  /// Macht einen früheren `going`/`maybe`-Swipe rückgängig - bewusst kein
  /// Rückwärts-Swipe im Deck, sondern von einem "Undo"-Button im
  /// `PartyDetailScreen` aufgerufen (siehe Plan).
  Future<void> undoDiscoverAction(
    String accessToken,
    Future<String?> Function() onRefresh,
    String partyId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.delete(_uri('/api/v1/discover/$partyId/action'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  /// Discover-Engine-Phase-1: blockiert den Organizer (Host) einer Party
  /// hart - dessen künftige Parties verschwinden aus jedem folgenden
  /// Deck-Fetch (siehe `backend/app/routers/discover.py::block_organizer`).
  Future<void> blockOrganizer(
    String accessToken,
    Future<String?> Function() onRefresh,
    String organizerId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(_uri('/api/v1/discover/organizers/$organizerId/block'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<void> unblockOrganizer(
    String accessToken,
    Future<String?> Function() onRefresh,
    String organizerId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.delete(_uri('/api/v1/discover/organizers/$organizerId/block'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<Party> publishParty(
    String accessToken,
    Future<String?> Function() onRefresh,
    String partyId, {
    required String eventType,
    List<String> interestTags = const [],
    int maxGuests = 0,
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/parties/$partyId/publish'),
        headers: _authHeaders(token),
        body: jsonEncode({'event_type': eventType, 'interest_tags': interestTags, 'max_guests': maxGuests}),
      ),
      accessToken,
      onRefresh,
    );
    return Party.fromJson(_decodeObject(resp));
  }

  Future<void> unpublishParty(
    String accessToken,
    Future<String?> Function() onRefresh,
    String partyId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.delete(_uri('/api/v1/parties/$partyId/publish'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  /// Multipart-Upload fürs Party-Cover-Bild (mirroring `uploadProfileImage`).
  Future<Party> uploadPartyCoverImage(
    String accessToken,
    Future<String?> Function() onRefresh,
    String partyId,
    File imageFile,
  ) async {
    Future<http.Response> sendWith(String token) async {
      final request = http.MultipartRequest('POST', _uri('/api/v1/parties/$partyId/cover-image'))
        ..headers['Authorization'] = 'Bearer $token'
        ..files.add(await http.MultipartFile.fromPath('file', imageFile.path));
      final streamedResponse = await _http.send(request);
      return http.Response.fromStream(streamedResponse);
    }

    final resp = await _authorizedRequest(sendWith, accessToken, onRefresh);
    return Party.fromJson(_decodeObject(resp));
  }

  /// Öffentlicher Katalog, kein Auth nötig (`discovery_catalogs.py`).
  Future<List<DiscoveryCatalogItem>> getEventInterestCatalog() async {
    final resp = await _http.get(_uri('/api/v1/catalogs/event-interests'));
    return _decodeList(resp)
        .map((e) => DiscoveryCatalogItem.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  Future<List<DiscoveryCatalogItem>> getInterestTagCatalog() async {
    final resp = await _http.get(_uri('/api/v1/catalogs/interest-tags'));
    return _decodeList(resp)
        .map((e) => DiscoveryCatalogItem.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  // ---------------------------------------------------------------------
  // Geo Platform - Ortssuche (Suggest/Retrieve/Reverse), strukturierte
  // Party-Location (Privacy-Tiers) und Discovery-Radius-Einstellungen
  // (`geo/`, `backend/app/routers/geo.py`, `party_locations.py`,
  // `discovery_preferences.py`).
  // ---------------------------------------------------------------------

  Future<List<GeoSuggestion>> suggestPlaces(
    String accessToken,
    Future<String?> Function() onRefresh, {
    required String query,
    String? sessionId,
    double? biasLat,
    double? biasLon,
    String? biasCountry,
  }) async {
    final params = <String, String>{'query': query};
    if (sessionId != null) params['session_id'] = sessionId;
    if (biasLat != null) params['bias_lat'] = biasLat.toString();
    if (biasLon != null) params['bias_lon'] = biasLon.toString();
    if (biasCountry != null) params['bias_country'] = biasCountry;

    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/geo/suggest', params), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    final body = _decodeObject(resp);
    return (body['suggestions'] as List)
        .map((e) => GeoSuggestion.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  Future<GeoPlace?> retrievePlace(
    String accessToken,
    Future<String?> Function() onRefresh, {
    required String providerPlaceId,
    String? sessionId,
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/geo/retrieve'),
        headers: _authHeaders(token),
        body: jsonEncode({'provider_place_id': providerPlaceId, 'session_id': sessionId}),
      ),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) throw ApiException(resp.statusCode, resp.body);
    final decoded = jsonDecode(utf8.decode(resp.bodyBytes));
    return decoded == null ? null : GeoPlace.fromJson((decoded as Map).cast<String, dynamic>());
  }

  Future<GeoPlace?> reverseGeocode(
    String accessToken,
    Future<String?> Function() onRefresh, {
    required double latitude,
    required double longitude,
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/geo/reverse'),
        headers: _authHeaders(token),
        body: jsonEncode({'latitude': latitude, 'longitude': longitude}),
      ),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) throw ApiException(resp.statusCode, resp.body);
    final decoded = jsonDecode(utf8.decode(resp.bodyBytes));
    return decoded == null ? null : GeoPlace.fromJson((decoded as Map).cast<String, dynamic>());
  }

  /// Setzt/aktualisiert die strukturierte Location einer Party (nur HOST/
  /// CO_HOST). `address`/`point` bleiben `null`, wenn der Host nur Freitext
  /// eingegeben und nie einen Vorschlag ausgewählt hat.
  Future<PartyLocationView> setPartyLocation(
    String accessToken,
    Future<String?> Function() onRefresh,
    String partyId, {
    String? placeName,
    GeoAddress? address,
    GeoPoint? point,
    String precision = 'approximate',
    String? provider,
    String? providerPlaceId,
    String publicLocationLabel = '',
    String visibilityPolicy = 'exact_after_accept',
    String? arrivalInstructions,
    bool manuallyAdjusted = false,
    String source = 'organizer_entry',
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.put(
        _uri('/api/v1/parties/$partyId/location'),
        headers: _authHeaders(token),
        body: jsonEncode({
          'place_name': placeName,
          'address': address?.toJson(),
          'point': point?.toJson(),
          'precision': precision,
          'provider': provider,
          'provider_place_id': providerPlaceId,
          'public_location_label': publicLocationLabel,
          'visibility_policy': visibilityPolicy,
          'arrival_instructions': arrivalInstructions,
          'manually_adjusted': manuallyAdjusted,
          'source': source,
        }),
      ),
      accessToken,
      onRefresh,
    );
    return PartyLocationView.fromJson(_decodeObject(resp));
  }

  /// `null`, wenn für diese Party noch keine strukturierte Location gesetzt
  /// wurde (Backend liefert dafür 404 - kein Fehlerfall, der Client fällt auf
  /// das bestehende `Party.location`-Freitextfeld zurück).
  Future<PartyLocationView?> getPartyLocation(
    String accessToken,
    Future<String?> Function() onRefresh,
    String partyId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/parties/$partyId/location'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode == 404) return null;
    return PartyLocationView.fromJson(_decodeObject(resp));
  }

  Future<DiscoveryPreferences> getDiscoveryPreferences(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/me/discovery-preferences'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return DiscoveryPreferences.fromJson(_decodeObject(resp));
  }

  Future<DiscoveryPreferences> updateDiscoveryPreferences(
    String accessToken,
    Future<String?> Function() onRefresh,
    DiscoveryPreferences preferences,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.put(
        _uri('/api/v1/me/discovery-preferences'),
        headers: _authHeaders(token),
        body: jsonEncode(preferences.toJson()),
      ),
      accessToken,
      onRefresh,
    );
    return DiscoveryPreferences.fromJson(_decodeObject(resp));
  }

  /// Build-Schritt 8: löscht alle gelernten Affinitäten - Ranking fällt
  /// danach auf reine explizite Preferences zurück (siehe
  /// `backend/app/routers/discovery_preferences.py::reset_learning`).
  Future<void> resetLearning(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(_uri('/api/v1/me/discovery-profile/reset-learning'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  /// Wirft ein 404 als `ApiException` (anders als `getPartyLocation`) - der
  /// 404-Zustand IST hier das fachliche "Onboarding noch nicht abgeschlossen"-
  /// Signal, das `ProfileScreen` explizit auffängt, kein stiller Sonderfall.
  Future<Profile> getProfile(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/me/profile'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return Profile.fromJson(_decodeObject(resp));
  }

  /// Bewusst OHNE `birth_date`-Parameter (siehe `ProfileUpdateRequest` im
  /// Backend) - der einzige Schreibpfad dafür ist [correctBirthDate].
  Future<Profile> updateProfile(
    String accessToken,
    Future<String?> Function() onRefresh, {
    String? gender,
    String? bio,
    String? username,
  }) async {
    final body = <String, dynamic>{};
    if (gender != null) body['gender'] = gender;
    if (bio != null) body['bio'] = bio;
    if (username != null) body['username'] = username;
    final resp = await _authorizedRequest(
      (token) => _http.patch(
        _uri('/api/v1/me/profile'),
        headers: _authHeaders(token),
        body: jsonEncode(body),
      ),
      accessToken,
      onRefresh,
    );
    return Profile.fromJson(_decodeObject(resp));
  }

  /// Legt das Profil beim allerersten Aufruf an (Onboarding) oder korrigiert
  /// das Geburtsdatum später - einziger Endpoint, der `birth_date` je
  /// schreibt.
  Future<Profile> correctBirthDate(
    String accessToken,
    Future<String?> Function() onRefresh, {
    required DateTime birthDate,
    String reason = '',
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/me/profile/birth-date-correction'),
        headers: _authHeaders(token),
        body: jsonEncode({
          'birth_date': DateFormat('yyyy-MM-dd').format(birthDate),
          'reason': reason,
        }),
      ),
      accessToken,
      onRefresh,
    );
    return Profile.fromJson(_decodeObject(resp));
  }

  Future<String> getSpotifyConnectUrl(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(
        _uri('/api/v1/me/music-provider/spotify/connect'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return _decodeObject(resp)['authorize_url'] as String;
  }

  Future<SpotifyStatus> getSpotifyStatus(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(
        _uri('/api/v1/me/music-provider/spotify/status'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    return SpotifyStatus.fromJson(_decodeObject(resp));
  }

  Future<void> disconnectSpotify(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.delete(
        _uri('/api/v1/me/music-provider/spotify/disconnect'),
        headers: _authHeaders(token),
      ),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  // ---------------------------------------------------------------------
  // Social Graph Phase 1 (Friends-Fundament) - Friend Requests, Friendship,
  // Blocking, Friend Search (siehe `backend/app/routers/social.py`).
  // ---------------------------------------------------------------------

  Future<List<Friend>> getFriends(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/me/friends'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return _decodeList(resp).map((e) => Friend.fromJson((e as Map).cast<String, dynamic>())).toList();
  }

  Future<void> removeFriend(
    String accessToken,
    Future<String?> Function() onRefresh,
    String userId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.delete(_uri('/api/v1/friends/$userId'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<FriendRequestsInbox> getFriendRequests(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/me/friend-requests'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return FriendRequestsInbox.fromJson(_decodeObject(resp));
  }

  Future<List<UserSearchResult>> searchUsers(
    String accessToken,
    Future<String?> Function() onRefresh, {
    required String q,
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/users/search', {'q': q}), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    final body = _decodeObject(resp);
    return (body['results'] as List)
        .map((e) => UserSearchResult.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  Future<SocialProfile> getSocialProfile(
    String accessToken,
    Future<String?> Function() onRefresh,
    String userId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/users/$userId/social-profile'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return SocialProfile.fromJson(_decodeObject(resp));
  }

  Future<FriendRequest> sendFriendRequest(
    String accessToken,
    Future<String?> Function() onRefresh,
    String userId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(_uri('/api/v1/users/$userId/friend-request'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    final body = _decodeObject(resp);
    return FriendRequest.fromJson((body['request'] as Map).cast<String, dynamic>());
  }

  Future<FriendRequest> acceptFriendRequest(
    String accessToken,
    Future<String?> Function() onRefresh,
    String requestId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(_uri('/api/v1/friend-requests/$requestId/accept'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return FriendRequest.fromJson(_decodeObject(resp));
  }

  Future<void> declineFriendRequest(
    String accessToken,
    Future<String?> Function() onRefresh,
    String requestId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(_uri('/api/v1/friend-requests/$requestId/decline'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<void> cancelFriendRequest(
    String accessToken,
    Future<String?> Function() onRefresh,
    String requestId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(_uri('/api/v1/friend-requests/$requestId/cancel'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<void> blockUser(
    String accessToken,
    Future<String?> Function() onRefresh,
    String userId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(_uri('/api/v1/users/$userId/block'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<void> unblockUser(
    String accessToken,
    Future<String?> Function() onRefresh,
    String userId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.delete(_uri('/api/v1/users/$userId/block'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  // ---------------------------------------------------------------------
  // Social Graph Phase 3 (Friend-list privacy & social settings polish) -
  // siehe backend/app/routers/social.py::get_social_privacy/update_social_privacy/get_user_friends.
  // ---------------------------------------------------------------------

  Future<SocialPrivacy> getSocialPrivacy(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/me/social-privacy'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return SocialPrivacy.fromJson(_decodeObject(resp));
  }

  Future<SocialPrivacy> updateSocialPrivacy(
    String accessToken,
    Future<String?> Function() onRefresh,
    SocialPrivacy privacy,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.put(
        _uri('/api/v1/me/social-privacy'),
        headers: _authHeaders(token),
        body: jsonEncode(privacy.toJson()),
      ),
      accessToken,
      onRefresh,
    );
    return SocialPrivacy.fromJson(_decodeObject(resp));
  }

  Future<List<Friend>> getUserFriends(
    String accessToken,
    Future<String?> Function() onRefresh,
    String userId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/users/$userId/friends'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return _decodeList(resp).map((e) => Friend.fromJson((e as Map).cast<String, dynamic>())).toList();
  }

  // ---------------------------------------------------------------------
  // Social Graph Phase 4/5: Organizers + Following -
  // siehe backend/app/routers/organizers.py + backend/app/routers/follows.py.
  // ---------------------------------------------------------------------

  Future<Organizer> createOrganizer(
    String accessToken,
    Future<String?> Function() onRefresh, {
    required String displayName,
    String organizerType = '',
    String description = '',
    String websiteUrl = '',
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/organizers'),
        headers: _authHeaders(token),
        body: jsonEncode({
          'display_name': displayName,
          'organizer_type': organizerType,
          'description': description,
          'website_url': websiteUrl,
        }),
      ),
      accessToken,
      onRefresh,
    );
    return Organizer.fromJson(_decodeObject(resp));
  }

  Future<List<Organizer>> listMyOrganizers(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/organizers/mine'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return _decodeList(resp).map((e) => Organizer.fromJson((e as Map).cast<String, dynamic>())).toList();
  }

  Future<Organizer> getOrganizer(
    String accessToken,
    Future<String?> Function() onRefresh,
    String organizerId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/organizers/$organizerId'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return Organizer.fromJson(_decodeObject(resp));
  }

  Future<OrganizerMember> addOrganizerMember(
    String accessToken,
    Future<String?> Function() onRefresh,
    String organizerId, {
    required String userId,
    required String role,
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/organizers/$organizerId/members'),
        headers: _authHeaders(token),
        body: jsonEncode({'user_id': userId, 'role': role}),
      ),
      accessToken,
      onRefresh,
    );
    return OrganizerMember.fromJson(_decodeObject(resp));
  }

  Future<List<OrganizerMember>> listOrganizerMembers(
    String accessToken,
    Future<String?> Function() onRefresh,
    String organizerId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/organizers/$organizerId/members'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    final body = _decodeObject(resp);
    return (body['members'] as List)
        .map((e) => OrganizerMember.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  Future<OrganizerFollowStatus> followOrganizer(
    String accessToken,
    Future<String?> Function() onRefresh,
    String organizerId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(_uri('/api/v1/organizers/$organizerId/follow'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return OrganizerFollowStatus.fromJson(_decodeObject(resp));
  }

  Future<void> unfollowOrganizer(
    String accessToken,
    Future<String?> Function() onRefresh,
    String organizerId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.delete(_uri('/api/v1/organizers/$organizerId/follow'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<OrganizerFollowStatus> getOrganizerFollowStatus(
    String accessToken,
    Future<String?> Function() onRefresh,
    String organizerId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/organizers/$organizerId/followers'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return OrganizerFollowStatus.fromJson(_decodeObject(resp));
  }

  Future<EventFollowStatus> followEvent(
    String accessToken,
    Future<String?> Function() onRefresh,
    String partyId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(_uri('/api/v1/events/$partyId/follow'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return EventFollowStatus.fromJson(_decodeObject(resp));
  }

  Future<void> unfollowEvent(
    String accessToken,
    Future<String?> Function() onRefresh,
    String partyId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.delete(_uri('/api/v1/events/$partyId/follow'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<EventFollowStatus> getEventFollowStatus(
    String accessToken,
    Future<String?> Function() onRefresh,
    String partyId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/events/$partyId/followers'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return EventFollowStatus.fromJson(_decodeObject(resp));
  }

  Future<List<Organizer>> listFollowedOrganizers(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/me/following/organizers'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return _decodeList(resp).map((e) => Organizer.fromJson((e as Map).cast<String, dynamic>())).toList();
  }

  Future<List<FollowedEvent>> listFollowedEvents(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/me/following/events'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return _decodeList(resp).map((e) => FollowedEvent.fromJson((e as Map).cast<String, dynamic>())).toList();
  }

  // ---------------------------------------------------------------------
  // Social Graph Phase 6/7/8/10: unified search, another user's following
  // lists, notification-category settings, account deletion.
  // ---------------------------------------------------------------------

  Future<SearchResults> unifiedSearch(
    String accessToken,
    Future<String?> Function() onRefresh, {
    required String q,
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/search', {'q': q}), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return SearchResults.fromJson(_decodeObject(resp));
  }

  Future<List<Organizer>> getUserFollowedOrganizers(
    String accessToken,
    Future<String?> Function() onRefresh,
    String userId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/users/$userId/following/organizers'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return _decodeList(resp).map((e) => Organizer.fromJson((e as Map).cast<String, dynamic>())).toList();
  }

  Future<List<FollowedEvent>> getUserFollowedEvents(
    String accessToken,
    Future<String?> Function() onRefresh,
    String userId,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/users/$userId/following/events'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return _decodeList(resp).map((e) => FollowedEvent.fromJson((e as Map).cast<String, dynamic>())).toList();
  }

  Future<NotificationSettings> getNotificationSettings(
    String accessToken,
    Future<String?> Function() onRefresh,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.get(_uri('/api/v1/me/notification-settings'), headers: _authHeaders(token)),
      accessToken,
      onRefresh,
    );
    return NotificationSettings.fromJson(_decodeObject(resp));
  }

  Future<NotificationSettings> updateNotificationSettings(
    String accessToken,
    Future<String?> Function() onRefresh,
    NotificationSettings settings,
  ) async {
    final resp = await _authorizedRequest(
      (token) => _http.put(
        _uri('/api/v1/me/notification-settings'),
        headers: _authHeaders(token),
        body: jsonEncode(settings.toJson()),
      ),
      accessToken,
      onRefresh,
    );
    return NotificationSettings.fromJson(_decodeObject(resp));
  }

  Future<void> deleteAccount(
    String accessToken,
    Future<String?> Function() onRefresh, {
    required String password,
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.delete(
        _uri('/api/v1/me'),
        headers: _authHeaders(token),
        body: jsonEncode({'password': password}),
      ),
      accessToken,
      onRefresh,
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  void close() => _http.close();
}
