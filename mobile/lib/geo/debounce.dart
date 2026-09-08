import 'dart:async';

/// Kleiner, wiederverwendbarer Debouncer für tippgetriebene Netzwerkaufrufe
/// (z.B. Orts-Autocomplete) - verzögert [run] um [delay], verwirft dabei
/// jeden vorherigen, noch nicht ausgelösten Aufruf. Erster Debounce-Helfer in
/// dieser Codebase (siehe Geo-Platform-Plan).
class Debouncer {
  final Duration delay;
  Timer? _timer;

  Debouncer({this.delay = const Duration(milliseconds: 300)});

  void run(void Function() action) {
    _timer?.cancel();
    _timer = Timer(delay, action);
  }

  void dispose() {
    _timer?.cancel();
  }
}
