import 'package:flutter/foundation.dart' show immutable;
import 'package:flutter/material.dart' show TimeOfDay;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/song_request.dart';

const int totalWizardSteps = 4;

/// Mirroring der `st.session_state`-Felder aus `render_guest_form()`
/// (Schritt-Zähler + alle 4 Formular-Schritte + `submitted`-Flag).
@immutable
class WizardState {
  final int step;
  final String name;
  final TimeOfDay startTime;
  final List<String> drinks;
  final String drinksFreetext;
  final List<String> food;
  final String foodFreetext;
  final List<SongRequest> songs;
  final bool submitted;
  final bool submitting;
  final String? submitError;

  const WizardState({
    this.step = 1,
    this.name = '',
    this.startTime = const TimeOfDay(hour: 19, minute: 0),
    this.drinks = const [],
    this.drinksFreetext = '',
    this.food = const [],
    this.foodFreetext = '',
    this.songs = const [],
    this.submitted = false,
    this.submitting = false,
    this.submitError,
  });

  WizardState copyWith({
    int? step,
    String? name,
    TimeOfDay? startTime,
    List<String>? drinks,
    String? drinksFreetext,
    List<String>? food,
    String? foodFreetext,
    List<SongRequest>? songs,
    bool? submitted,
    bool? submitting,
    String? submitError,
  }) {
    return WizardState(
      step: step ?? this.step,
      name: name ?? this.name,
      startTime: startTime ?? this.startTime,
      drinks: drinks ?? this.drinks,
      drinksFreetext: drinksFreetext ?? this.drinksFreetext,
      food: food ?? this.food,
      foodFreetext: foodFreetext ?? this.foodFreetext,
      songs: songs ?? this.songs,
      submitted: submitted ?? this.submitted,
      submitting: submitting ?? this.submitting,
      submitError: submitError,
    );
  }

  String get startTimeFormatted =>
      '${startTime.hour.toString().padLeft(2, '0')}:${startTime.minute.toString().padLeft(2, '0')}';
}

class WizardNotifier extends Notifier<WizardState> {
  @override
  WizardState build() => const WizardState();

  void setName(String name) => state = state.copyWith(name: name);

  void setStartTime(TimeOfDay time) => state = state.copyWith(startTime: time);

  void setDrinks(List<String> ids) => state = state.copyWith(drinks: ids);

  void setDrinksFreetext(String value) => state = state.copyWith(drinksFreetext: value);

  void setFood(List<String> ids) => state = state.copyWith(food: ids);

  void setFoodFreetext(String value) => state = state.copyWith(foodFreetext: value);

  void addSong(SongRequest song) => state = state.copyWith(songs: [...state.songs, song]);

  void removeSongAt(int index) {
    final updated = [...state.songs]..removeAt(index);
    state = state.copyWith(songs: updated);
  }

  void goToStep(int step) => state = state.copyWith(step: step);

  void nextStep() => state = state.copyWith(step: state.step + 1);

  void previousStep() => state = state.copyWith(step: state.step - 1);

  void markSubmitting() => state = state.copyWith(submitting: true, submitError: null);

  void markSubmitted() => state = state.copyWith(submitted: true, submitting: false);

  void markSubmitError(String message) =>
      state = state.copyWith(submitting: false, submitError: message);
}

final wizardProvider = NotifierProvider<WizardNotifier, WizardState>(WizardNotifier.new);
