/// Admin-erfasste Location-/Infrastruktur-/Wetter-Basisdaten
/// (mirroring `party_context.domain.PartyContext`'s admin-editierbare Felder
/// bzw. `backend/app/schemas/admin.py::PartyContextUpdate`). Anlass/Datum/
/// Startzeit/Dauer/Gästezahl kommen aus [PartySettings] und werden hier
/// NICHT erneut geführt (EINE Quelle der Wahrheit).
class PartyContext {
  final String locationType;
  final String indoorOutdoor;
  final String countryCode;
  final bool hasGrill;
  final bool hasKitchen;
  final bool hasFridge;
  final bool hasFreezer;
  final bool hasIceMachine;
  final bool hasBar;
  final bool hasCoffeeMachine;
  final bool hasPower;
  final bool hasRunningWater;
  final bool dancingPossible;
  final bool neighborsSensitive;
  final String? musicVolumeLimit;
  final bool selfService;
  final double? seatingRatio;
  final String? weatherCondition;
  final double? expectedTemperatureC;

  const PartyContext({
    required this.locationType,
    required this.indoorOutdoor,
    required this.countryCode,
    required this.hasGrill,
    required this.hasKitchen,
    required this.hasFridge,
    required this.hasFreezer,
    required this.hasIceMachine,
    required this.hasBar,
    required this.hasCoffeeMachine,
    required this.hasPower,
    required this.hasRunningWater,
    required this.dancingPossible,
    required this.neighborsSensitive,
    required this.musicVolumeLimit,
    required this.selfService,
    required this.seatingRatio,
    required this.weatherCondition,
    required this.expectedTemperatureC,
  });

  factory PartyContext.fromJson(Map<String, dynamic> json) {
    return PartyContext(
      locationType: (json['location_type'] as String?) ?? 'other',
      indoorOutdoor: (json['indoor_outdoor'] as String?) ?? 'outdoor',
      countryCode: (json['country_code'] as String?) ?? '',
      hasGrill: (json['has_grill'] as bool?) ?? false,
      hasKitchen: (json['has_kitchen'] as bool?) ?? false,
      hasFridge: (json['has_fridge'] as bool?) ?? false,
      hasFreezer: (json['has_freezer'] as bool?) ?? false,
      hasIceMachine: (json['has_ice_machine'] as bool?) ?? false,
      hasBar: (json['has_bar'] as bool?) ?? false,
      hasCoffeeMachine: (json['has_coffee_machine'] as bool?) ?? false,
      hasPower: (json['has_power'] as bool?) ?? false,
      hasRunningWater: (json['has_running_water'] as bool?) ?? false,
      dancingPossible: (json['dancing_possible'] as bool?) ?? false,
      neighborsSensitive: (json['neighbors_sensitive'] as bool?) ?? false,
      musicVolumeLimit: json['music_volume_limit'] as String?,
      selfService: (json['self_service'] as bool?) ?? true,
      seatingRatio: (json['seating_ratio'] as num?)?.toDouble(),
      weatherCondition: json['weather_condition'] as String?,
      expectedTemperatureC: (json['expected_temperature_c'] as num?)?.toDouble(),
    );
  }

  Map<String, dynamic> toJson() => {
        'location_type': locationType,
        'indoor_outdoor': indoorOutdoor,
        'country_code': countryCode,
        'has_grill': hasGrill,
        'has_kitchen': hasKitchen,
        'has_fridge': hasFridge,
        'has_freezer': hasFreezer,
        'has_ice_machine': hasIceMachine,
        'has_bar': hasBar,
        'has_coffee_machine': hasCoffeeMachine,
        'has_power': hasPower,
        'has_running_water': hasRunningWater,
        'dancing_possible': dancingPossible,
        'neighbors_sensitive': neighborsSensitive,
        'music_volume_limit': musicVolumeLimit,
        'self_service': selfService,
        'seating_ratio': seatingRatio,
        'weather_condition': weatherCondition,
        'expected_temperature_c': expectedTemperatureC,
      };

  PartyContext copyWith({
    String? locationType,
    String? indoorOutdoor,
    String? countryCode,
    bool? hasGrill,
    bool? hasKitchen,
    bool? hasFridge,
    bool? hasFreezer,
    bool? hasIceMachine,
    bool? hasBar,
    bool? hasCoffeeMachine,
    bool? hasPower,
    bool? hasRunningWater,
    bool? dancingPossible,
    bool? neighborsSensitive,
    String? musicVolumeLimit,
    bool? selfService,
    double? seatingRatio,
    String? weatherCondition,
    double? expectedTemperatureC,
  }) {
    return PartyContext(
      locationType: locationType ?? this.locationType,
      indoorOutdoor: indoorOutdoor ?? this.indoorOutdoor,
      countryCode: countryCode ?? this.countryCode,
      hasGrill: hasGrill ?? this.hasGrill,
      hasKitchen: hasKitchen ?? this.hasKitchen,
      hasFridge: hasFridge ?? this.hasFridge,
      hasFreezer: hasFreezer ?? this.hasFreezer,
      hasIceMachine: hasIceMachine ?? this.hasIceMachine,
      hasBar: hasBar ?? this.hasBar,
      hasCoffeeMachine: hasCoffeeMachine ?? this.hasCoffeeMachine,
      hasPower: hasPower ?? this.hasPower,
      hasRunningWater: hasRunningWater ?? this.hasRunningWater,
      dancingPossible: dancingPossible ?? this.dancingPossible,
      neighborsSensitive: neighborsSensitive ?? this.neighborsSensitive,
      musicVolumeLimit: musicVolumeLimit ?? this.musicVolumeLimit,
      selfService: selfService ?? this.selfService,
      seatingRatio: seatingRatio ?? this.seatingRatio,
      weatherCondition: weatherCondition ?? this.weatherCondition,
      expectedTemperatureC: expectedTemperatureC ?? this.expectedTemperatureC,
    );
  }
}

class LocationType {
  final String id;
  final String labelDe;
  final String labelEn;

  const LocationType({required this.id, required this.labelDe, required this.labelEn});

  factory LocationType.fromJson(Map<String, dynamic> json) {
    return LocationType(
      id: json['id'] as String,
      labelDe: json['label_de'] as String,
      labelEn: json['label_en'] as String,
    );
  }

  String label(String lang) => lang == 'de' ? labelDe : labelEn;
}

class CountryOption {
  final String code;
  final String name;

  const CountryOption({required this.code, required this.name});

  factory CountryOption.fromJson(Map<String, dynamic> json) {
    return CountryOption(code: json['code'] as String, name: json['name'] as String);
  }
}

/// Antwort von `GET /api/v1/admin/party-context/metadata`.
class PartyContextMetadata {
  final List<LocationType> locationTypes;
  final List<CountryOption> countries;

  const PartyContextMetadata({required this.locationTypes, required this.countries});

  factory PartyContextMetadata.fromJson(Map<String, dynamic> json) {
    return PartyContextMetadata(
      locationTypes: (json['location_types'] as List)
          .map((e) => LocationType.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
      countries: (json['countries'] as List)
          .map((e) => CountryOption.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
    );
  }
}
