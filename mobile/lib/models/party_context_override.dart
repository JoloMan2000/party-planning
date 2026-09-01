/// Ein einzelner Admin-Override eines abgeleiteten Top-Level-Felds (mirroring
/// `party_context.domain.PartyContextOverride`), z.B. "Zelt mit Heizung ->
/// temperature_class warm trotz Winter".
class PartyContextOverride {
  final String key;
  final String value;
  final String? reason;

  const PartyContextOverride({required this.key, required this.value, this.reason});

  factory PartyContextOverride.fromJson(Map<String, dynamic> json) {
    return PartyContextOverride(
      key: json['key'] as String,
      value: json['value'] as String,
      reason: json['reason'] as String?,
    );
  }
}

/// Overridebare Felder + geschlossener Wertebereich je Feld (mirroring
/// `Party Planning.py`'s `_OVERRIDE_KEY_OPTIONS`).
const overrideKeyOptions = <String, List<String>>{
  'season': ['spring', 'summer', 'autumn', 'winter'],
  'temperature_class': ['cold', 'cool', 'mild', 'warm', 'hot'],
  'indoor_outdoor': ['indoor', 'outdoor', 'mixed'],
  'daypart_primary': ['morning', 'brunch', 'daytime', 'afternoon', 'evening', 'late_night'],
  'group_size_class': ['small_group', 'medium_group', 'large_group', 'very_large_group'],
};

const overrideKeyLabelKeys = <String, String>{
  'season': 'override_key_season',
  'temperature_class': 'override_key_temperature_class',
  'indoor_outdoor': 'override_key_indoor_outdoor',
  'daypart_primary': 'override_key_daypart_primary',
  'group_size_class': 'override_key_group_size_class',
};

const overrideValueLabelKeys = <String, Map<String, String>>{
  'season': {
    'spring': 'season_spring',
    'summer': 'season_summer',
    'autumn': 'season_autumn',
    'winter': 'season_winter',
  },
  'temperature_class': {
    'cold': 'temp_class_cold',
    'cool': 'temp_class_cool',
    'mild': 'temp_class_mild',
    'warm': 'temp_class_warm',
    'hot': 'temp_class_hot',
  },
  'indoor_outdoor': {
    'indoor': 'indoor_outdoor_indoor',
    'outdoor': 'indoor_outdoor_outdoor',
    'mixed': 'indoor_outdoor_mixed',
  },
  'daypart_primary': {
    'morning': 'daypart_morning',
    'brunch': 'daypart_brunch',
    'daytime': 'daypart_daytime',
    'afternoon': 'daypart_afternoon',
    'evening': 'daypart_evening',
    'late_night': 'daypart_late_night',
  },
  'group_size_class': {
    'small_group': 'group_size_small_group',
    'medium_group': 'group_size_medium_group',
    'large_group': 'group_size_large_group',
    'very_large_group': 'group_size_very_large_group',
  },
};
