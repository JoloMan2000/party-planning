/// Mirrort `backend/app/schemas/geo.py` 1:1 (gleiche JSON-Parsing-Konvention
/// wie `mobile/lib/models/party.dart`: `factory X.fromJson`, null-safe Casts).
library;

class GeoPoint {
  final double latitude;
  final double longitude;

  const GeoPoint({required this.latitude, required this.longitude});

  factory GeoPoint.fromJson(Map<String, dynamic> json) => GeoPoint(
        latitude: (json['latitude'] as num).toDouble(),
        longitude: (json['longitude'] as num).toDouble(),
      );

  Map<String, dynamic> toJson() => {'latitude': latitude, 'longitude': longitude};
}

class GeoAddress {
  final String? street;
  final String? houseNumber;
  final String? postalCode;
  final String? city;
  final String? district;
  final String? region;
  final String? countryCode;
  final String? countryName;
  final String formattedAddress;

  const GeoAddress({
    this.street,
    this.houseNumber,
    this.postalCode,
    this.city,
    this.district,
    this.region,
    this.countryCode,
    this.countryName,
    this.formattedAddress = '',
  });

  factory GeoAddress.fromJson(Map<String, dynamic> json) => GeoAddress(
        street: json['street'] as String?,
        houseNumber: json['house_number'] as String?,
        postalCode: json['postal_code'] as String?,
        city: json['city'] as String?,
        district: json['district'] as String?,
        region: json['region'] as String?,
        countryCode: json['country_code'] as String?,
        countryName: json['country_name'] as String?,
        formattedAddress: (json['formatted_address'] as String?) ?? '',
      );

  Map<String, dynamic> toJson() => {
        'street': street,
        'house_number': houseNumber,
        'postal_code': postalCode,
        'city': city,
        'district': district,
        'region': region,
        'country_code': countryCode,
        'country_name': countryName,
        'formatted_address': formattedAddress,
      };
}

class GeoSuggestion {
  final String providerPlaceId;
  final String primaryText;
  final String secondaryText;
  final String placeType;
  final String provider;

  const GeoSuggestion({
    required this.providerPlaceId,
    required this.primaryText,
    required this.secondaryText,
    required this.placeType,
    required this.provider,
  });

  factory GeoSuggestion.fromJson(Map<String, dynamic> json) => GeoSuggestion(
        providerPlaceId: json['provider_place_id'] as String,
        primaryText: json['primary_text'] as String,
        secondaryText: json['secondary_text'] as String,
        placeType: json['place_type'] as String,
        provider: json['provider'] as String,
      );
}

class GeoPlace {
  final String id;
  final String name;
  final String placeType;
  final GeoAddress address;
  final GeoPoint? point;
  final String provider;
  final String providerPlaceId;
  final String precision;

  const GeoPlace({
    required this.id,
    required this.name,
    required this.placeType,
    required this.address,
    required this.point,
    required this.provider,
    required this.providerPlaceId,
    required this.precision,
  });

  factory GeoPlace.fromJson(Map<String, dynamic> json) => GeoPlace(
        id: json['id'] as String,
        name: json['name'] as String,
        placeType: json['place_type'] as String,
        address: GeoAddress.fromJson((json['address'] as Map).cast<String, dynamic>()),
        point: json['point'] == null ? null : GeoPoint.fromJson((json['point'] as Map).cast<String, dynamic>()),
        provider: json['provider'] as String,
        providerPlaceId: json['provider_place_id'] as String,
        precision: json['precision'] as String,
      );
}

/// Antwort von `GET/PUT /api/v1/parties/{id}/location` - bereits
/// privacy-gefiltert serverseitig (`geo.privacy.build_party_location_view`);
/// enthält NIE mehr, als der aktuelle Nutzer sehen darf.
class PartyLocationView {
  final String visibilityLevel;
  final String displayLabel;
  final String? formattedAddress;
  final GeoPoint? point;
  final String? arrivalInstructions;

  const PartyLocationView({
    required this.visibilityLevel,
    required this.displayLabel,
    required this.formattedAddress,
    required this.point,
    required this.arrivalInstructions,
  });

  bool get isExact => visibilityLevel == 'exact';

  factory PartyLocationView.fromJson(Map<String, dynamic> json) => PartyLocationView(
        visibilityLevel: json['visibility_level'] as String,
        displayLabel: json['display_label'] as String,
        formattedAddress: json['formatted_address'] as String?,
        point: json['point'] == null ? null : GeoPoint.fromJson((json['point'] as Map).cast<String, dynamic>()),
        arrivalInstructions: json['arrival_instructions'] as String?,
      );
}
