/// Mirrort `backend/app/schemas/profile.py::DiscoveryPreferencesPublic`
/// (`GET/PUT /api/v1/me/discovery-preferences`).
class DiscoveryPreferences {
  final double discoveryRadiusKm;
  final bool allowMajorEventsOutsideRadius;
  final String discoveryCity;
  final double? discoveryLat;
  final double? discoveryLon;
  final List<String> preferredDays;
  final List<String> preferredDayparts;
  final String pricePreference;
  final double mainstreamDiscovery;
  final bool personalizedRecommendationsEnabled;

  const DiscoveryPreferences({
    this.discoveryRadiusKm = 25.0,
    this.allowMajorEventsOutsideRadius = false,
    this.discoveryCity = '',
    this.discoveryLat,
    this.discoveryLon,
    this.preferredDays = const [],
    this.preferredDayparts = const [],
    this.pricePreference = '',
    this.mainstreamDiscovery = 0.5,
    this.personalizedRecommendationsEnabled = true,
  });

  factory DiscoveryPreferences.fromJson(Map<String, dynamic> json) => DiscoveryPreferences(
        discoveryRadiusKm: (json['discovery_radius_km'] as num).toDouble(),
        allowMajorEventsOutsideRadius: (json['allow_major_events_outside_radius'] as bool?) ?? false,
        discoveryCity: (json['discovery_city'] as String?) ?? '',
        discoveryLat: (json['discovery_lat'] as num?)?.toDouble(),
        discoveryLon: (json['discovery_lon'] as num?)?.toDouble(),
        preferredDays: (json['preferred_days'] as List?)?.cast<String>() ?? const [],
        preferredDayparts: (json['preferred_dayparts'] as List?)?.cast<String>() ?? const [],
        pricePreference: (json['price_preference'] as String?) ?? '',
        mainstreamDiscovery: (json['mainstream_discovery'] as num).toDouble(),
        personalizedRecommendationsEnabled: (json['personalized_recommendations_enabled'] as bool?) ?? true,
      );

  DiscoveryPreferences copyWith({
    double? discoveryRadiusKm,
    bool? allowMajorEventsOutsideRadius,
    String? discoveryCity,
    double? discoveryLat,
    double? discoveryLon,
    List<String>? preferredDays,
    List<String>? preferredDayparts,
    String? pricePreference,
    double? mainstreamDiscovery,
    bool? personalizedRecommendationsEnabled,
  }) =>
      DiscoveryPreferences(
        discoveryRadiusKm: discoveryRadiusKm ?? this.discoveryRadiusKm,
        allowMajorEventsOutsideRadius: allowMajorEventsOutsideRadius ?? this.allowMajorEventsOutsideRadius,
        discoveryCity: discoveryCity ?? this.discoveryCity,
        discoveryLat: discoveryLat ?? this.discoveryLat,
        discoveryLon: discoveryLon ?? this.discoveryLon,
        preferredDays: preferredDays ?? this.preferredDays,
        preferredDayparts: preferredDayparts ?? this.preferredDayparts,
        pricePreference: pricePreference ?? this.pricePreference,
        mainstreamDiscovery: mainstreamDiscovery ?? this.mainstreamDiscovery,
        personalizedRecommendationsEnabled: personalizedRecommendationsEnabled ?? this.personalizedRecommendationsEnabled,
      );

  Map<String, dynamic> toJson() => {
        'discovery_radius_km': discoveryRadiusKm,
        'allow_major_events_outside_radius': allowMajorEventsOutsideRadius,
        'discovery_city': discoveryCity,
        'discovery_lat': discoveryLat,
        'discovery_lon': discoveryLon,
        'preferred_days': preferredDays,
        'preferred_dayparts': preferredDayparts,
        'price_preference': pricePreference,
        'mainstream_discovery': mainstreamDiscovery,
        'personalized_recommendations_enabled': personalizedRecommendationsEnabled,
      };
}
