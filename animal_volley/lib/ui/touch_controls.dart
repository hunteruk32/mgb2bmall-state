import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../game/world.dart';

class TouchControlsController {
  int bits = 0;
}

/// 멀티터치 버튼: 왼쪽 아래 ◀ ▶, 오른쪽 아래 점프 / 스파이크.
/// 손가락을 버튼 사이로 미끄러뜨려도 자연스럽게 바뀌도록 위치로 판정한다.
class TouchControls extends StatefulWidget {
  final TouchControlsController controller;
  final Listenable repaint;
  const TouchControls(
      {super.key, required this.controller, required this.repaint});

  @override
  State<TouchControls> createState() => _TouchControlsState();
}

class _Btn {
  final int bit;
  final String label;
  final Offset center;
  final double radius;
  _Btn(this.bit, this.label, this.center, this.radius);
}

class _TouchControlsState extends State<TouchControls> {
  final _pointers = <int, Offset>{};
  Size _size = Size.zero;

  List<_Btn> _buttons(Size s) {
    final r = math.min(s.height * 0.11, 50.0);
    final y = s.height - r - 8;
    return [
      _Btn(Input.left, '◀', Offset(r * 1.4, y), r),
      _Btn(Input.right, '▶', Offset(r * 3.9, y), r),
      _Btn(Input.jump, '점프', Offset(s.width - r * 3.9, y), r),
      _Btn(Input.hit, '스파이크', Offset(s.width - r * 1.4, y - r * 0.35), r * 1.05),
    ];
  }

  /// 손가락 위치 → 버튼. 화면 왼쪽 절반은 이동, 오른쪽 절반은 점프/스파이크.
  int _bitAt(Offset p) {
    final b = _buttons(_size);
    if (p.dx < _size.width / 2) {
      if (p.dy < _size.height * 0.35) return 0;
      final mid = (b[0].center.dx + b[1].center.dx) / 2;
      return p.dx < mid ? Input.left : Input.right;
    } else {
      if (p.dy < _size.height * 0.35) return 0;
      final mid = (b[2].center.dx + b[3].center.dx) / 2;
      return p.dx < mid ? Input.jump : Input.hit;
    }
  }

  void _update() {
    int bits = 0;
    for (final p in _pointers.values) {
      bits |= _bitAt(p);
    }
    widget.controller.bits = bits;
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, box) {
      _size = box.biggest;
      return Listener(
        behavior: HitTestBehavior.translucent,
        onPointerDown: (e) {
          _pointers[e.pointer] = e.localPosition;
          _update();
        },
        onPointerMove: (e) {
          _pointers[e.pointer] = e.localPosition;
          _update();
        },
        onPointerUp: (e) {
          _pointers.remove(e.pointer);
          _update();
        },
        onPointerCancel: (e) {
          _pointers.remove(e.pointer);
          _update();
        },
        child: CustomPaint(
          size: _size,
          painter: _ControlsPainter(
              _buttons(_size), widget.controller, widget.repaint),
        ),
      );
    });
  }
}

class _ControlsPainter extends CustomPainter {
  final List<_Btn> buttons;
  final TouchControlsController ctl;
  _ControlsPainter(this.buttons, this.ctl, Listenable repaint)
      : super(repaint: repaint);

  @override
  void paint(Canvas canvas, Size size) {
    for (final b in buttons) {
      final on = ctl.bits & b.bit != 0;
      canvas.drawCircle(
          b.center,
          b.radius,
          Paint()
            ..color = Colors.white
                .withValues(alpha: on ? 0.45 : 0.12));
      canvas.drawCircle(
          b.center,
          b.radius,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2.5
            ..color = Colors.white.withValues(alpha: on ? 0.8 : 0.45));
      final tp = TextPainter(
        text: TextSpan(
          text: b.label,
          style: TextStyle(
            color: Colors.white.withValues(alpha: on ? 0.95 : 0.7),
            shadows: const [Shadow(color: Color(0x66000000), blurRadius: 3)],
            fontSize: b.label.length > 2 ? b.radius * 0.36 : b.radius * 0.55,
            fontWeight: FontWeight.w900,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, b.center - Offset(tp.width / 2, tp.height / 2));
    }
  }

  @override
  bool shouldRepaint(covariant _ControlsPainter old) => true;
}
