/// Ersetzt `{key}`-Platzhalter in einem Übersetzungs-String, mirroring
/// Python's `template.format(**kwargs)` (siehe `translations.py::t()`).
/// Beispiel: `tr(table, 'step1_header', {'n': 4})` für `"Schritt 1 von {n}"`.
String tr(Map<String, String> table, String key, [Map<String, Object?> params = const {}]) {
  var value = table[key] ?? key;
  for (final entry in params.entries) {
    value = value.replaceAll('{${entry.key}}', '${entry.value}');
  }
  return value;
}
