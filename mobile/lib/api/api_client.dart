import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../models/admin_recommendation.dart';
import '../models/app_notification.dart';
import '../models/auth_token_response.dart';
import '../models/catalog_curation_settings.dart';
import '../models/catalog_item.dart';
import '../models/derived_party_context.dart';
import '../models/discover_action_result.dart';
import '../models/discover_card.dart';
import '../models/discovery_catalog_item.dart';
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
  }) async {
    final resp = await _authorizedRequest(
      (token) => _http.post(
        _uri('/api/v1/discover/$partyId/action'),
        headers: _authHeaders(token),
        body: jsonEncode({'action': action}),
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

  void close() => _http.close();
}
