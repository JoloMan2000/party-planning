import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/admin_login_response.dart';
import '../models/admin_recommendation.dart';
import '../models/auth_token_response.dart';
import '../models/catalog_curation_settings.dart';
import '../models/catalog_item.dart';
import '../models/derived_party_context.dart';
import '../models/event_type.dart';
import '../models/guest_response.dart';
import '../models/invitation.dart';
import '../models/language_option.dart';
import '../models/music_admin_settings.dart';
import '../models/music_planning_result.dart';
import '../models/party.dart';
import '../models/party_context.dart';
import '../models/party_context_override.dart';
import '../models/party_demand_result.dart';
import '../models/party_guests_response.dart';
import '../models/party_info.dart';
import '../models/party_settings.dart';
import '../models/guest_response_draft.dart';
import '../models/rsvp_response.dart';
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

  Map<String, String> _authHeaders(String token) => {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      };

  /// Alle wählbaren Event-Typen fürs Party-Settings-Dropdown
  /// (`admin_party_settings.py::get_event_types`).
  Future<List<EventType>> getEventTypes(String token) async {
    final resp = await _http.get(
      _uri('/api/v1/admin/party-settings/event-types'),
      headers: _authHeaders(token),
    );
    return _decodeList(resp)
        .map((e) => EventType.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  Future<PartySettings> getPartySettings(String token) async {
    final resp = await _http.get(
      _uri('/api/v1/admin/party-settings'),
      headers: _authHeaders(token),
    );
    return PartySettings.fromJson(_decodeObject(resp));
  }

  /// Speichert die Party-Settings, liefert `reset_happened` zurück (mirroring
  /// des Lifecycle-Trigger-Hinweises in `render_party_settings_section`).
  Future<bool> savePartySettings(String token, PartySettings settings) async {
    final resp = await _http.post(
      _uri('/api/v1/admin/party-settings'),
      headers: _authHeaders(token),
      body: jsonEncode(settings.toJson()),
    );
    final body = _decodeObject(resp);
    return body['reset_happened'] as bool? ?? false;
  }

  /// Stammdaten fürs Party-Kontext-Formular (Location-Typen, Länderliste -
  /// `admin_party_context.py::get_party_context_metadata`).
  Future<PartyContextMetadata> getPartyContextMetadata(String token) async {
    final resp = await _http.get(
      _uri('/api/v1/admin/party-context/metadata'),
      headers: _authHeaders(token),
    );
    return PartyContextMetadata.fromJson(_decodeObject(resp));
  }

  Future<PartyContext> getPartyContext(String token) async {
    final resp = await _http.get(
      _uri('/api/v1/admin/party-context'),
      headers: _authHeaders(token),
    );
    return PartyContext.fromJson(_decodeObject(resp));
  }

  Future<void> savePartyContext(String token, PartyContext context) async {
    final resp = await _http.post(
      _uri('/api/v1/admin/party-context'),
      headers: _authHeaders(token),
      body: jsonEncode(context.toJson()),
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<MusicAdminSettings> getMusicSettings(String token) async {
    final resp = await _http.get(
      _uri('/api/v1/admin/music/settings'),
      headers: _authHeaders(token),
    );
    return MusicAdminSettings.fromJson(_decodeObject(resp));
  }

  Future<void> saveMusicSettings(String token, MusicAdminSettings settings) async {
    final resp = await _http.post(
      _uri('/api/v1/admin/music/settings'),
      headers: _authHeaders(token),
      body: jsonEncode(settings.toJson()),
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<MusicPlanningResult> generateMusicPlaylist(String token) async {
    final resp = await _http.post(
      _uri('/api/v1/admin/music/generate-playlist'),
      headers: _authHeaders(token),
    );
    return MusicPlanningResult.fromJson(_decodeObject(resp));
  }

  Future<CatalogCurationSettings> getCatalogCurationSettings(String token) async {
    final resp = await _http.get(
      _uri('/api/v1/admin/catalog-curation'),
      headers: _authHeaders(token),
    );
    return CatalogCurationSettings.fromJson(_decodeObject(resp));
  }

  Future<void> saveCatalogCurationSettings(String token, bool enabled, List<String> curatedItemIds) async {
    final resp = await _http.post(
      _uri('/api/v1/admin/catalog-curation'),
      headers: _authHeaders(token),
      body: jsonEncode({'enabled': enabled, 'curated_item_ids': curatedItemIds}),
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<CuratableCatalog> getCuratableCatalog(String token, {String lang = 'de'}) async {
    final resp = await _http.get(
      _uri('/api/v1/admin/catalog-curation/items', {'lang': lang}),
      headers: _authHeaders(token),
    );
    return CuratableCatalog.fromJson(_decodeObject(resp));
  }

  Future<AdminRecommendationsResponse> getAdminRecommendations(String token) async {
    final resp = await _http.get(
      _uri('/api/v1/admin/recommendations'),
      headers: _authHeaders(token),
    );
    return AdminRecommendationsResponse.fromJson(_decodeObject(resp));
  }

  Future<DerivedPartyContext> getDerivedPartyContext(String token) async {
    final resp = await _http.get(
      _uri('/api/v1/admin/party-context/derived'),
      headers: _authHeaders(token),
    );
    return DerivedPartyContext.fromJson(_decodeObject(resp));
  }

  Future<List<PartyContextOverride>> getPartyContextOverrides(String token) async {
    final resp = await _http.get(
      _uri('/api/v1/admin/party-context/overrides'),
      headers: _authHeaders(token),
    );
    return _decodeList(resp)
        .map((e) => PartyContextOverride.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  Future<void> addPartyContextOverride(String token, String key, String value, String? reason) async {
    final resp = await _http.post(
      _uri('/api/v1/admin/party-context/overrides'),
      headers: _authHeaders(token),
      body: jsonEncode({'key': key, 'value': value, 'reason': reason}),
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  Future<void> deletePartyContextOverride(String token, String key) async {
    final resp = await _http.delete(
      _uri('/api/v1/admin/party-context/overrides/$key'),
      headers: _authHeaders(token),
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  /// Gespeicherte Gäste-Antworten inkl. vorformatierter Anzeige-Felder
  /// (mirroring `raw_responses_expander`).
  Future<List<GuestResponse>> getResponses(String token, {String lang = 'de'}) async {
    final resp = await _http.get(
      _uri('/api/v1/admin/responses', {'lang': lang}),
      headers: _authHeaders(token),
    );
    return _decodeList(resp)
        .map((e) => GuestResponse.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  /// Rohe CSV-Bytes für den Antworten-Export (Download/Teilen via
  /// `share_plus`, mirroring `btn_csv`).
  Future<List<int>> getResponsesCsv(String token) async {
    final resp = await _http.get(
      _uri('/api/v1/admin/responses/csv'),
      headers: _authHeaders(token),
    );
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
    return resp.bodyBytes;
  }

  /// Einkaufsliste (Unified Demand Pipeline, mirroring `render_shopping_list`).
  Future<PartyDemandResult> computeShoppingList(String token) async {
    final resp = await _http.post(
      _uri('/api/v1/admin/shopping-list'),
      headers: _authHeaders(token),
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

  void close() => _http.close();
}
