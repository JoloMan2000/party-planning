/// Nur die für das read-only Context-Dashboard relevante Teilmenge von
/// `party_context.domain.DerivedPartyContext` (mirroring
/// `render_party_context_dashboard`'s angezeigte Felder). Weitere Felder
/// (Modifiers etc.) werden hier bewusst ignoriert - dieses Dashboard ist rein
/// informativ, keine weitere Engine-Logik.
class DerivedPartyContext {
  final String season;
  final String daypartPrimary;
  final String temperatureClass;
  final String groupSizeClass;
  final List<String> operationalConstraints;
  final String countryCode;
  final String countryName;
  final String countrySource;
  final List<String> explanations;

  const DerivedPartyContext({
    required this.season,
    required this.daypartPrimary,
    required this.temperatureClass,
    required this.groupSizeClass,
    required this.operationalConstraints,
    required this.countryCode,
    required this.countryName,
    required this.countrySource,
    required this.explanations,
  });

  factory DerivedPartyContext.fromJson(Map<String, dynamic> json) {
    return DerivedPartyContext(
      season: json['season'] as String? ?? 'summer',
      daypartPrimary: json['daypart_primary'] as String? ?? 'evening',
      temperatureClass: json['temperature_class'] as String? ?? 'mild',
      groupSizeClass: json['group_size_class'] as String? ?? 'medium_group',
      operationalConstraints:
          (json['operational_constraints'] as List? ?? []).map((e) => e as String).toList(),
      countryCode: json['country_code'] as String? ?? '',
      countryName: json['country_name'] as String? ?? '',
      countrySource: json['country_source'] as String? ?? 'unknown',
      explanations: (json['explanations'] as List? ?? []).map((e) => e as String).toList(),
    );
  }
}

const seasonLabelKeys = {
  'spring': 'season_spring',
  'summer': 'season_summer',
  'autumn': 'season_autumn',
  'winter': 'season_winter',
};
const daypartLabelKeys = {
  'morning': 'daypart_morning',
  'brunch': 'daypart_brunch',
  'daytime': 'daypart_daytime',
  'afternoon': 'daypart_afternoon',
  'evening': 'daypart_evening',
  'late_night': 'daypart_late_night',
};
const temperatureClassLabelKeys = {
  'cold': 'temp_class_cold',
  'cool': 'temp_class_cool',
  'mild': 'temp_class_mild',
  'warm': 'temp_class_warm',
  'hot': 'temp_class_hot',
};
const groupSizeLabelKeys = {
  'small_group': 'group_size_small_group',
  'medium_group': 'group_size_medium_group',
  'large_group': 'group_size_large_group',
  'very_large_group': 'group_size_very_large_group',
};
