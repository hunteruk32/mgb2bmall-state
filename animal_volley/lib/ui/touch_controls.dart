import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../game/world.dart';
import '../settings.dart';

class TouchControlsController {
  int bits = 0;
}

/// 터치 조작
/// - 화면 왼쪽 절반: 조이스틱. 엄지를 댄 자리에 생기고, 좌우로 밀면 이동,
///   위로 밀면 점프. 기준점이 손가락을 따라와서, 어디서든 반대로 조금만
///   움직이면 바로 방향이 바뀐다.
/// - 화면 오른쪽 절반: 스파이크 버튼 (땅에서 방향과 함께 누르면 다이빙)
class TouchControls extends StatefulWidget {
  final TouchControlsController controller;
  final Listenable repaint;
  const TouchControls(
      {super.key, required this.controller, required this.repaint});

  @override
  State<TouchControls> createState() => _TouchControlsState();
}

class _Stick {
  final int pointer;
  Offset origin; // 기준점 (손가락을 따라 움직인다)
  Offset finger;
  _Stick(this.pointer, Offset p)
      : origin = p,
        finger = p;
  Offset get delta => finger - origin;
}

class _TouchControlsState extends State<TouchControls> {
  Size _size = Size.zero;
  _Stick? _stick;
  final _hitPointers = <int>{};

  double get _stickRadius => math.min(_size.height * 0.13, 60.0);
  double get _hitRadius => math.min(_size.height * 0.15, 66.0);

  /// 아무것도 안 만질 때 조이스틱이 보이는 자리
  Offset get _restOrigin =>
      Offset(_stickRadius * 1.6, _size.height - _stickRadius * 1.35);
  Offset get _hitCenter =>
      Offset(_size.width - _hitRadius * 1.4, _size.height - _hitRadius * 1.25);

  /// 기준점이 따라오기 시작하는 거리(px). 감도가 높을수록 짧다.
  double get _followR =>
      38 - 22 * GameSettings.instance.stickSensitivity; // 38px ~ 16px
  double get _moveThr => math.max(4.0, _followR * 0.3);
  double get _jumpThr => _followR * 0.48;

  bool _jumpHeld = false;

  void _update() {
    int bits = 0;
    final s = _stick;
    if (s != null) {
      final d = s.delta;
      if (d.dx < -_moveThr) bits |= Input.left;
      if (d.dx > _moveThr) bits |= Input.right;
      // 점프: 위로 밀면 켜지고, 조금만 내려와도 다시 점프할 수 있게 풀린다
      if (d.dy < -_jumpThr) {
        _jumpHeld = true;
      } else if (d.dy > -_jumpThr * 0.4) {
        _jumpHeld = false;
      }
      if (_jumpHeld) bits |= Input.jump;
    } else {
      _jumpHeld = false;
    }
    if (_hitPointers.isNotEmpty) bits |= Input.hit;
    widget.controller.bits = bits;
  }

  // 점수판(위 가운데)·일시정지 버튼(오른쪽 위)만 피하고 거의 전체를 쓴다
  bool _isStickArea(Offset p) =>
      p.dx < _size.width / 2 && p.dy > _size.height * 0.12;
  bool _isHitArea(Offset p) =>
      p.dx >= _size.width / 2 &&
      p.dy > _size.height * 0.12 &&
      !(p.dx > _size.width - 90 && p.dy < 90);

  void _down(PointerDownEvent e) {
    final p = e.localPosition;
    if (_isStickArea(p) && _stick == null) {
      _stick = _Stick(e.pointer, p);
    } else if (_isHitArea(p)) {
      _hitPointers.add(e.pointer);
    }
    _update();
  }

  void _move(PointerMoveEvent e) {
    final s = _stick;
    if (s != null && s.pointer == e.pointer) {
      s.finger = e.localPosition;
      // 기준점을 손가락 쪽으로 끌고 온다 (가로/세로 따로)
      final r = _followR;
      var o = s.origin;
      final d = s.delta;
      if (d.dx > r) o = Offset(s.finger.dx - r, o.dy);
      if (d.dx < -r) o = Offset(s.finger.dx + r, o.dy);
      if (d.dy > r * 0.6) o = Offset(o.dx, s.finger.dy - r * 0.6);
      if (d.dy < -r) o = Offset(o.dx, s.finger.dy + r);
      s.origin = o;
      _update();
    }
  }

  void _up(int pointer) {
    if (_stick?.pointer == pointer) _stick = null;
    _hitPointers.remove(pointer);
    _update();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, box) {
      _size = box.biggest;
      return Listener(
        behavior: HitTestBehavior.translucent,
        onPointerDown: _down,
        onPointerMove: _move,
        onPointerUp: (e) => _up(e.pointer),
        onPointerCancel: (e) => _up(e.pointer),
        child: CustomPaint(
          size: _size,
          painter: _ControlsPainter(this, widget.repaint),
        ),
      );
    });
  }
}

class _ControlsPainter extends CustomPainter {
  final _TouchControlsState s;
  _ControlsPainter(this.s, Listenable repaint) : super(repaint: repaint);

  @override
  void paint(Canvas canvas, Size size) {
    final bits = s.widget.controller.bits;
    final stick = s._stick;
    final r = s._stickRadius;
    final origin = stick?.origin ?? s._restOrigin;
    // 손잡이는 실제 이동량을 받침 크기에 맞춰 크게 보여준다
    var kd = stick == null ? Offset.zero : stick.delta / s._followR * r * 0.75;
    if (kd.distance > r * 0.8) kd = kd / kd.distance * r * 0.8;
    final knob = origin + kd;
    final active = stick != null;

    // 조이스틱 받침
    canvas.drawCircle(origin, r,
        Paint()..color = Colors.white.withValues(alpha: active ? 0.22 : 0.12));
    canvas.drawCircle(
        origin,
        r,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.5
          ..color = Colors.white.withValues(alpha: active ? 0.7 : 0.45));
    // 방향 표시 (◀ ▶ ▲점프)
    _arrow(canvas, origin + Offset(-r * 0.72, 0), math.pi, bits & Input.left != 0, r);
    _arrow(canvas, origin + Offset(r * 0.72, 0), 0, bits & Input.right != 0, r);
    _arrow(canvas, origin + Offset(0, -r * 0.72), -math.pi / 2, bits & Input.jump != 0, r);
    _text(canvas, '점프', origin + Offset(0, -r - 10), r * 0.24,
        bits & Input.jump != 0);
    // 손잡이
    canvas.drawCircle(knob, r * 0.42,
        Paint()..color = Colors.white.withValues(alpha: active ? 0.75 : 0.35));
    canvas.drawCircle(
        knob,
        r * 0.42,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2
          ..color = const Color(0x55000000));

    // 스파이크 버튼
    final hc = s._hitCenter;
    final hr = s._hitRadius;
    final on = bits & Input.hit != 0;
    canvas.drawCircle(hc, hr,
        Paint()..color = Colors.white.withValues(alpha: on ? 0.45 : 0.14));
    canvas.drawCircle(
        hc,
        hr,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.5
          ..color = Colors.white.withValues(alpha: on ? 0.85 : 0.5));
    _text(canvas, '스파이크', hc, hr * 0.3, on);
  }

  void _arrow(Canvas c, Offset at, double angle, bool on, double r) {
    final size = r * 0.16;
    c.save();
    c.translate(at.dx, at.dy);
    c.rotate(angle);
    final p = Path()
      ..moveTo(size, 0)
      ..lineTo(-size * 0.6, -size)
      ..lineTo(-size * 0.6, size)
      ..close();
    c.drawPath(p, Paint()..color = Colors.white.withValues(alpha: on ? 0.95 : 0.55));
    c.restore();
  }

  void _text(Canvas c, String t, Offset center, double fontSize, bool on) {
    final tp = TextPainter(
      text: TextSpan(
        text: t,
        style: TextStyle(
          color: Colors.white.withValues(alpha: on ? 0.95 : 0.7),
          fontSize: fontSize,
          fontWeight: FontWeight.w900,
          shadows: const [Shadow(color: Color(0x66000000), blurRadius: 3)],
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(c, center - Offset(tp.width / 2, tp.height / 2));
  }

  @override
  bool shouldRepaint(covariant _ControlsPainter old) => true;
}
