// Rauch-Test für den App-Einstieg: verifiziert, dass `PartyApp` den
// Intro-Screen rendert. Im Testlauf gibt es keinen echten Server (Flutters
// Test-Binding beantwortet jeden HTTP-Request synchron mit Status 400), der
// `partyInfoProvider`-Request landet also im Fehlerzustand - der Test prüft
// daher nur, dass `IntroScreen` den dafür vorgesehenen Retry-Button rendert,
// statt auf einen echten Backend-Erfolg zu warten (siehe `IntroScreen`s
// `_ErrorRetry`).

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:mobile/main.dart';

void main() {
  testWidgets('PartyApp zeigt den Intro-Screen beim Start', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: PartyApp()));
    await tester.pumpAndSettle();

    expect(find.textContaining('Retry'), findsOneWidget);
  });
}
