import 'package:flutter/material.dart';

/// Richtung eines committeten Swipes - rechts = "interessiert"
/// (`going`), hoch = "vielleicht" (`maybe`), links = "kein Interesse"
/// (`not_interested`). Siehe `DiscoverScreen` für das Mapping auf die
/// Backend-Action-Strings.
enum SwipeDirection { left, right, up }

/// Externe Steuerung für [SwipeCardStack] - erlaubt Tap-Buttons, exakt
/// denselben Exit-Animation-/Callback-Pfad wie eine echte Drag-Geste
/// auszulösen (Accessibility "for free", keine doppelte Swipe-Logik).
class SwipeCardStackController {
  dynamic _state;

  void _attach(dynamic state) => _state = state;
  void _detach(dynamic state) {
    if (_state == state) _state = null;
  }

  void swipeRight() => _state?._triggerSwipe(SwipeDirection.right);
  void swipeLeft() => _state?._triggerSwipe(SwipeDirection.left);
  void swipeUp() => _state?._triggerSwipe(SwipeDirection.up);
}

/// Generischer Tinder-Style Swipe-Card-Stack - kein Package, reine
/// `GestureDetector`/`Transform`/`AnimationController`-Implementierung (siehe
/// Discover-MVP-Plan). Rendert bis zu 3 gestapelte Karten (die hinteren zwei
/// als statische, skalierte/abgeblendete "Peek"-Karten, die vorderste
/// interaktiv), mit farbcodierten Stempel-Overlays, die proportional zur
/// Drag-Distanz einblenden.
class SwipeCardStack<T> extends StatefulWidget {
  final List<T> items;
  final Widget Function(BuildContext context, T item) cardBuilder;
  final void Function(T item, SwipeDirection direction) onSwiped;
  final VoidCallback? onDeckEmpty;
  final SwipeCardStackController? controller;

  const SwipeCardStack({
    super.key,
    required this.items,
    required this.cardBuilder,
    required this.onSwiped,
    this.onDeckEmpty,
    this.controller,
  });

  @override
  State<SwipeCardStack<T>> createState() => _SwipeCardStackState<T>();
}

class _SwipeCardStackState<T> extends State<SwipeCardStack<T>> with SingleTickerProviderStateMixin {
  static const double _dragThreshold = 120;
  static const double _velocityThreshold = 800;

  late List<T> _deck;
  Offset _dragOffset = Offset.zero;
  bool _dragging = false;
  late AnimationController _animController;
  Animation<Offset>? _offsetAnimation;
  bool _emptyReported = false;

  @override
  void initState() {
    super.initState();
    _deck = List.of(widget.items);
    widget.controller?._attach(this);
    _animController = AnimationController(vsync: this, duration: const Duration(milliseconds: 250));
    _animController.addListener(() {
      if (_offsetAnimation != null) {
        setState(() => _dragOffset = _offsetAnimation!.value);
      }
    });
  }

  @override
  void didUpdateWidget(covariant SwipeCardStack<T> oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      oldWidget.controller?._detach(this);
      widget.controller?._attach(this);
    }
    if (!identical(oldWidget.items, widget.items)) {
      _deck = List.of(widget.items);
      _emptyReported = false;
    }
  }

  @override
  void dispose() {
    widget.controller?._detach(this);
    _animController.dispose();
    super.dispose();
  }

  void _triggerSwipe(SwipeDirection direction) {
    if (_deck.isEmpty || _animController.isAnimating) return;
    _commit(direction);
  }

  void _onPanStart(DragStartDetails details) {
    if (_animController.isAnimating) return;
    _dragging = true;
    _animController.stop();
  }

  void _onPanUpdate(DragUpdateDetails details) {
    if (!_dragging) return;
    setState(() => _dragOffset += details.delta);
  }

  void _onPanEnd(DragEndDetails details) {
    if (!_dragging) return;
    _dragging = false;
    final velocity = details.velocity.pixelsPerSecond;
    final dx = _dragOffset.dx;
    final dy = _dragOffset.dy;

    final verticalDominant = dy < 0 && dy.abs() > dx.abs();
    final upTriggered = verticalDominant && (dy.abs() > _dragThreshold || velocity.dy < -_velocityThreshold);
    final horizontalTriggered = dx.abs() > _dragThreshold || velocity.dx.abs() > _velocityThreshold;

    if (upTriggered) {
      _commit(SwipeDirection.up);
    } else if (horizontalTriggered) {
      _commit(dx > 0 ? SwipeDirection.right : SwipeDirection.left);
    } else {
      _springBack();
    }
  }

  void _springBack() {
    _offsetAnimation = Tween<Offset>(begin: _dragOffset, end: Offset.zero).animate(
      CurvedAnimation(parent: _animController, curve: Curves.easeOutBack),
    );
    _animController.duration = const Duration(milliseconds: 200);
    _animController.forward(from: 0).then((_) => _offsetAnimation = null);
  }

  void _commit(SwipeDirection direction) {
    if (_deck.isEmpty) return;
    final size = MediaQuery.of(context).size;
    final Offset target;
    switch (direction) {
      case SwipeDirection.left:
        target = Offset(-size.width * 1.5, _dragOffset.dy);
        break;
      case SwipeDirection.right:
        target = Offset(size.width * 1.5, _dragOffset.dy);
        break;
      case SwipeDirection.up:
        target = Offset(_dragOffset.dx, -size.height * 1.5);
        break;
    }
    _offsetAnimation = Tween<Offset>(begin: _dragOffset, end: target).animate(
      CurvedAnimation(parent: _animController, curve: Curves.easeOut),
    );
    _animController.duration = const Duration(milliseconds: 250);
    final item = _deck.first;
    _animController.forward(from: 0).then((_) {
      setState(() {
        _deck.removeAt(0);
        _dragOffset = Offset.zero;
        _offsetAnimation = null;
      });
      widget.onSwiped(item, direction);
      if (_deck.isEmpty && !_emptyReported) {
        _emptyReported = true;
        widget.onDeckEmpty?.call();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_deck.isEmpty) return const SizedBox.shrink();

    final visible = _deck.take(3).toList();
    final children = <Widget>[];
    for (var i = visible.length - 1; i >= 0; i--) {
      children.add(i == 0 ? _buildTopCard(visible[i]) : _buildPeekCard(visible[i], i));
    }
    return Stack(alignment: Alignment.center, children: children);
  }

  Widget _buildPeekCard(T item, int depth) {
    return Transform.translate(
      offset: Offset(0, depth * 10.0),
      child: Transform.scale(
        scale: 1.0 - depth * 0.04,
        child: Opacity(
          opacity: 1.0 - depth * 0.25,
          child: widget.cardBuilder(context, item),
        ),
      ),
    );
  }

  Widget _buildTopCard(T item) {
    final rotation = (_dragOffset.dx / 300).clamp(-0.4, 0.4);
    final rightProgress = (_dragOffset.dx / _dragThreshold).clamp(0.0, 1.0);
    final leftProgress = (-_dragOffset.dx / _dragThreshold).clamp(0.0, 1.0);
    final upProgress = (-_dragOffset.dy / _dragThreshold).clamp(0.0, 1.0);

    return GestureDetector(
      onPanStart: _onPanStart,
      onPanUpdate: _onPanUpdate,
      onPanEnd: _onPanEnd,
      child: Transform.translate(
        offset: _dragOffset,
        child: Transform.rotate(
          angle: rotation,
          child: Stack(
            children: [
              widget.cardBuilder(context, item),
              if (rightProgress > 0) _buildStamp('INTERESTED', Colors.green, rightProgress, Alignment.topLeft),
              if (leftProgress > 0) _buildStamp('NOPE', Colors.red, leftProgress, Alignment.topRight),
              if (upProgress > 0) _buildStamp('MAYBE', Colors.blue, upProgress, Alignment.topCenter),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStamp(String label, Color color, double progress, Alignment alignment) {
    return Positioned.fill(
      child: Align(
        alignment: alignment,
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Opacity(
            opacity: progress,
            child: Transform.rotate(
              angle: -0.2,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  border: Border.all(color: color, width: 3),
                  borderRadius: BorderRadius.circular(8),
                  color: Colors.white.withValues(alpha: 0.7),
                ),
                child: Text(
                  label,
                  style: TextStyle(color: color, fontWeight: FontWeight.w900, fontSize: 22, letterSpacing: 1.5),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
