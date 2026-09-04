// Rauch-Test für den App-Einstieg: verifiziert, dass `PartyApp` den
// Login-Screen rendert (Phase-3-Account-Flow, siehe `main.dart`-Routing).
// Im Testlauf gibt es kein `flutter_secure_storage`-Platform-Channel-Mock -
// ein echter `AuthNotifier.build()`-Aufruf würde dort auf eine Antwort
// warten, die nie kommt, und `pumpAndSettle` liefe in einen Timeout (der
// Ladeindikator auf `LoginScreen` animiert unbegrenzt weiter). Der Test
// überschreibt `authProvider` daher mit einer Fake-Notifier, die sofort
// `null` liefert (= kein gespeichertes Token), ohne den Storage anzufassen.

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:mobile/main.dart';
import 'package:mobile/state/auth_providers.dart';

class _FakeAuthNotifier extends AuthNotifier {
  @override
  Future<TokenPair?> build() async => null;
}

void main() {
  testWidgets('PartyApp zeigt den Login-Screen beim Start', (WidgetTester tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [authProvider.overrideWith(_FakeAuthNotifier.new)],
        child: const PartyApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Log in'), findsOneWidget);
  });
}
