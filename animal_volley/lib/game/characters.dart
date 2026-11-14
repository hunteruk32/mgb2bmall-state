// 캐릭터 4종(벌꿀오소리, 돼지, 킹콩, 바다사자)을 이미지 없이 Canvas로 직접 그린다.
// 모든 캐릭터는 (0,0)을 몸 중심으로, 오른쪽을 바라보는 모습으로 그린 뒤
// facing 값으로 좌우 반전한다. 몸 반지름은 대략 38.

import 'dart:math' as math;
import 'package:flutter/material.dart';

enum Animal { badger, pig, kong, sealion }

extension AnimalInfo on Animal {
  String get displayName => switch (this) {
        Animal.badger => '벌꿀오소리',
        Animal.pig => '돼지',
        Animal.kong => '킹콩',
        Animal.sealion => '바다사자',
      };

  List<Palette> get palettes => switch (this) {
        Animal.badger => const [
            Palette('기본', Color(0xFF3A3A44), Color(0xFF24242B), Color(0xFFEDEDED), Color(0xFF1A1A1F)),
            Palette('갈색', Color(0xFF6B4A33), Color(0xFF4A3222), Color(0xFFF3E2C4), Color(0xFF2B1C12)),
            Palette('남색', Color(0xFF2E3E6E), Color(0xFF1E2A4D), Color(0xFFDDE6FF), Color(0xFF121A33)),
            Palette('보라', Color(0xFF5B3A73), Color(0xFF3E2650), Color(0xFFF1DFFF), Color(0xFF261633)),
          ],
        Animal.pig => const [
            Palette('기본', Color(0xFFFFB3C1), Color(0xFFEB8FA3), Color(0xFFFF8FA6), Color(0xFF8A3B4F)),
            Palette('흑돼지', Color(0xFF4A4148), Color(0xFF332C31), Color(0xFF6E6169), Color(0xFF1E191C)),
            Palette('점박이', Color(0xFFF7E3D0), Color(0xFFE0C2A6), Color(0xFFF2A9A0), Color(0xFF7A4B3A)),
            Palette('민트', Color(0xFFA8E6CF), Color(0xFF7FCBB0), Color(0xFF6FC9A8), Color(0xFF2E6E58)),
          ],
        Animal.kong => const [
            Palette('기본', Color(0xFF3B3533), Color(0xFF26211F), Color(0xFF9C8678), Color(0xFF1A1514)),
            Palette('실버백', Color(0xFF55565C), Color(0xFF393A40), Color(0xFFB9B2AA), Color(0xFF1F2024)),
            Palette('적갈색', Color(0xFF6E3B2A), Color(0xFF4D281C), Color(0xFFC79A7E), Color(0xFF2E160F)),
            Palette('황금', Color(0xFFB8862E), Color(0xFF8C6420), Color(0xFFF2D49B), Color(0xFF4D3610)),
          ],
        Animal.sealion => const [
            Palette('기본', Color(0xFF8A6A4F), Color(0xFF6A4F39), Color(0xFFC4A584), Color(0xFF2B1F16)),
            Palette('회색', Color(0xFF7D8590), Color(0xFF5E656E), Color(0xFFB9C1CC), Color(0xFF22262B)),
            Palette('하늘', Color(0xFF6FA8DC), Color(0xFF4F86B8), Color(0xFFBFDDF5), Color(0xFF1C3A57)),
            Palette('초코', Color(0xFF4E3426), Color(0xFF362318), Color(0xFF8C6A55), Color(0xFF1A100A)),
          ],
      };
}

/// base: 몸 색, shade: 그림자/팔다리, accent: 배·얼굴·줄무늬 등 포인트 색, ink: 코/눈 등
class Palette {
  final String name;
  final Color base, shade, accent, ink;
  const Palette(this.name, this.base, this.shade, this.accent, this.ink);
}

enum Pose { idle, run, jump, spike, dive, win, lose }

class CharacterLook {
  final Animal animal;
  final int paletteIndex;
  const CharacterLook(this.animal, this.paletteIndex);
  Palette get palette => animal.palettes[paletteIndex];

  @override
  bool operator ==(Object other) =>
      other is CharacterLook &&
      other.animal == animal &&
      other.paletteIndex == paletteIndex;
  @override
  int get hashCode => Object.hash(animal, paletteIndex);
}

/// 캐릭터 하나를 그린다. [t]는 초 단위 시간(애니메이션용), [facing]은 +1(오른쪽) / -1.
void paintCharacter(Canvas canvas, CharacterLook look, Pose pose, double t,
    {int facing = 1, double hitFlash = 0}) {
  final p = look.palette;
  canvas.save();
  canvas.scale(facing.toDouble(), 1);

  // 몸 전체 변형(통통 튀는 느낌)
  double sx = 1, sy = 1, rot = 0, oy = 0;
  switch (pose) {
    case Pose.idle:
      final b = math.sin(t * 4);
      sx = 1 + b * 0.025;
      sy = 1 - b * 0.025;
      break;
    case Pose.run:
      final b = math.sin(t * 18).abs();
      oy = -b * 5;
      rot = 0.08;
      break;
    case Pose.jump:
      sx = 0.94;
      sy = 1.07;
      break;
    case Pose.spike:
      rot = -0.18;
      break;
    case Pose.dive:
      rot = 0.12;
      oy = 14;
      sx = 1.18;
      sy = 0.74;
      break;
    case Pose.win:
      oy = -math.sin(t * 10).abs() * 10;
      break;
    case Pose.lose:
      sy = 0.92;
      oy = 4;
      rot = 0.12;
      break;
  }
  canvas.translate(0, oy);
  canvas.rotate(rot);
  canvas.scale(sx, sy);

  final ctx = _Ctx(canvas, p, pose, t);
  switch (look.animal) {
    case Animal.badger:
      _badger(ctx);
    case Animal.pig:
      _pig(ctx);
    case Animal.kong:
      _kong(ctx);
    case Animal.sealion:
      _sealion(ctx);
  }

  if (hitFlash > 0) {
    canvas.drawCircle(
        Offset.zero,
        42,
        Paint()
          ..color = Colors.white.withValues(alpha: 0.35 * hitFlash)
          ..blendMode = BlendMode.srcATop);
  }
  canvas.restore();
}

class _Ctx {
  final Canvas c;
  final Palette p;
  final Pose pose;
  final double t;
  _Ctx(this.c, this.p, this.pose, this.t);

  Paint fill(Color color) => Paint()..color = color;
  Paint get outline => Paint()
    ..color = p.ink.withValues(alpha: 0.85)
    ..style = PaintingStyle.stroke
    ..strokeWidth = 2.6
    ..strokeJoin = StrokeJoin.round
    ..strokeCap = StrokeCap.round;

  void oval(Offset center, double w, double h, Color color,
      {bool stroke = true}) {
    final r = Rect.fromCenter(center: center, width: w, height: h);
    c.drawOval(r, fill(color));
    if (stroke) c.drawOval(r, outline);
  }

  /// 발 두 개 (달리기 시 교차)
  void feet(Color color, {double y = 34, double spread = 13, double w = 20}) {
    double a = 0, b = 0;
    if (pose == Pose.run) {
      a = math.sin(t * 18) * 6;
      b = -a;
    }
    if (pose == Pose.jump || pose == Pose.spike) {
      a = -4;
      b = 3;
    }
    oval(Offset(-spread + a, y), w, 12, color);
    oval(Offset(spread + b, y), w, 12, color);
  }

  /// 앞팔. 스파이크 때는 위로 번쩍 든다.
  /// 팔 각도/어깨 위치 (오른쪽 = 0, 위 = -pi/2)
  (Offset, double) armPose() {
    switch (pose) {
      case Pose.spike:
        return (const Offset(6, -12), -1.6);
      case Pose.win:
        return (const Offset(10, -2), -0.85 + math.sin(t * 10) * 0.25);
      case Pose.jump:
        return (const Offset(2, 10), 2.3);
      case Pose.dive:
        return (const Offset(10, 8), 0.15);
      case Pose.run:
        return (const Offset(4, 12), 1.25 + math.sin(t * 18) * 0.55);
      default:
        return (const Offset(4, 12), 1.35 + math.sin(t * 4) * 0.05);
    }
  }

  /// 앞팔. 스파이크 때는 머리 위로 번쩍 든다.
  void frontArm(Color color, {double len = 22, double thick = 13}) {
    final (at, ang) = armPose();
    if (pose == Pose.spike) len *= 1.7;
    if (pose == Pose.win) len *= 1.3;
    c.save();
    c.translate(at.dx, at.dy);
    c.rotate(ang);
    final r = Rect.fromLTWH(-thick / 2, -thick / 2, len + thick / 2, thick);
    final rr = RRect.fromRectAndRadius(r, Radius.circular(thick / 2));
    c.drawRRect(rr, fill(color));
    c.drawRRect(rr, outline);
    c.restore();
  }

  void eye(Offset at, {double size = 5.5, bool angry = false}) {
    if (pose == Pose.lose) {
      // 꽉 감은 눈 ><
      final pp = Paint()
        ..color = p.ink
        ..strokeWidth = 2.6
        ..strokeCap = StrokeCap.round;
      c.drawLine(at + const Offset(-4, -3), at + const Offset(3, 0), pp);
      c.drawLine(at + const Offset(-4, 3), at + const Offset(3, 0), pp);
      return;
    }
    if (pose == Pose.win) {
      // 웃는 눈 ^^
      final path = Path()
        ..moveTo(at.dx - 5, at.dy + 2)
        ..quadraticBezierTo(at.dx, at.dy - 5, at.dx + 5, at.dy + 2);
      c.drawPath(
          path,
          Paint()
            ..color = p.ink
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2.8
            ..strokeCap = StrokeCap.round);
      return;
    }
    c.drawCircle(at, size, fill(Colors.white));
    c.drawCircle(at + const Offset(1.5, 0.5), size * 0.6, fill(p.ink));
    c.drawCircle(at + const Offset(2.4, -1), size * 0.22, fill(Colors.white));
    if (angry || pose == Pose.spike) {
      c.drawLine(
          at + Offset(-size - 1, -size - 3),
          at + Offset(size + 1, -size + 0.5),
          Paint()
            ..color = p.ink
            ..strokeWidth = 3
            ..strokeCap = StrokeCap.round);
    }
  }

  void blush(Offset at, Color color) {
    c.drawOval(Rect.fromCenter(center: at, width: 11, height: 6),
        fill(color.withValues(alpha: 0.55)));
  }

  void mouth(Offset at, {double w = 7}) {
    final open = pose == Pose.spike || pose == Pose.win;
    if (open) {
      final r = Rect.fromCenter(center: at + const Offset(0, 1), width: w, height: w * 0.9);
      c.drawArc(r, 0, math.pi, true, fill(const Color(0xFF6B1E2A)));
      c.drawArc(r, 0, math.pi, true, outline..strokeWidth = 2);
    } else {
      final path = Path()
        ..moveTo(at.dx - w / 2, at.dy)
        ..quadraticBezierTo(at.dx, at.dy + (pose == Pose.lose ? -4 : 4),
            at.dx + w / 2, at.dy);
      c.drawPath(path, outline..strokeWidth = 2.2);
    }
  }
}

// ---------------------------------------------------------------------------
// 벌꿀오소리: 짙은 몸 + 머리부터 등까지 이어지는 흰 망토 무늬, 겁 없는 눈썹
// ---------------------------------------------------------------------------
void _badger(_Ctx k) {
  final c = k.c, p = k.p;
  k.feet(p.shade);
  // 꼬리
  k.oval(const Offset(-36, 10), 18, 12, p.shade);
  // 몸
  final body = Rect.fromCenter(center: const Offset(0, 2), width: 80, height: 72);
  c.drawOval(body, k.fill(p.base));
  // 흰 망토 무늬(몸 위쪽 + 뒤쪽)
  c.save();
  c.clipPath(Path()..addOval(body));
  final cape = Path()
    ..moveTo(36, -18)
    ..quadraticBezierTo(12, -6, -8, -2)
    ..quadraticBezierTo(-30, 2, -44, 16)
    ..lineTo(-44, -44)
    ..lineTo(44, -44)
    ..close();
  c.drawPath(cape, k.fill(p.accent));
  c.restore();
  c.drawOval(body, k.outline);
  // 귀
  k.oval(const Offset(-6, -34), 13, 11, p.accent);
  k.oval(const Offset(10, -33), 11, 9, p.accent);
  // 얼굴 쪽 주둥이
  k.oval(const Offset(30, 4), 24, 18, p.base);
  c.drawCircle(const Offset(41, 1), 5, k.fill(p.ink));
  k.eye(const Offset(18, -8), angry: true);
  k.mouth(const Offset(30, 11), w: 8);
  k.frontArm(p.shade, len: 20, thick: 14);
  // 발톱
  if (k.pose != Pose.dive) {
    final claw = Paint()
      ..color = p.accent
      ..strokeWidth = 1.8
      ..strokeCap = StrokeCap.round;
    for (var i = 0; i < 3; i++) {
      final x = 18.0 + i * 3;
      c.drawLine(Offset(x, 39), Offset(x + 2, 42), claw);
    }
  }
}

// ---------------------------------------------------------------------------
// 돼지: 동글동글 분홍 몸, 큰 코, 접힌 귀, 돌돌 꼬리
// ---------------------------------------------------------------------------
void _pig(_Ctx k) {
  final c = k.c, p = k.p;
  k.feet(p.shade, w: 16);
  // 돌돌 꼬리
  final tail = Path()
    ..moveTo(-37, 4)
    ..cubicTo(-50, -4, -52, 12, -44, 10)
    ..cubicTo(-38, 8, -44, 0, -48, 4);
  c.drawPath(tail, k.outline..strokeWidth = 3);
  // 몸
  k.oval(const Offset(0, 2), 82, 74, p.base);
  // 점박이 무늬(점박이 팔레트일 때만 눈에 띔)
  if (p.name == '점박이') {
    k.oval(const Offset(-16, -14), 22, 16, p.shade, stroke: false);
    k.oval(const Offset(-22, 16), 14, 10, p.shade, stroke: false);
  }
  // 귀(삼각형, 앞으로 접힘)
  for (final dx in [-8.0, 12.0]) {
    final ear = Path()
      ..moveTo(dx - 9, -28)
      ..lineTo(dx + 1, -44)
      ..lineTo(dx + 10, -27)
      ..close();
    c.drawPath(ear, k.fill(p.shade));
    c.drawPath(ear, k.outline);
  }
  // 코
  k.oval(const Offset(36, 0), 20, 24, p.accent);
  c.drawOval(Rect.fromCenter(center: const Offset(35, -4), width: 4, height: 6),
      k.fill(p.ink));
  c.drawOval(Rect.fromCenter(center: const Offset(35, 5), width: 4, height: 6),
      k.fill(p.ink));
  k.eye(const Offset(18, -12));
  k.blush(const Offset(14, 6), p.accent);
  k.mouth(const Offset(25, 16), w: 7);
  k.frontArm(p.shade, len: 18, thick: 12);
}

// ---------------------------------------------------------------------------
// 킹콩(고릴라): 어깨가 넓은 몸, 밝은 얼굴 마스크와 굵은 눈두덩, 긴 팔
// ---------------------------------------------------------------------------
void _kong(_Ctx k) {
  final c = k.c, p = k.p;
  k.feet(p.shade, spread: 15, w: 22);
  // 뒷팔
  k.oval(const Offset(-30, 14), 18, 30, p.shade);
  // 몸(위가 넓은 형태)
  final body = Path()
    ..moveTo(-38, 10)
    ..cubicTo(-42, -30, -18, -42, 4, -42)
    ..cubicTo(30, -42, 44, -26, 40, 8)
    ..cubicTo(38, 34, 20, 40, 0, 40)
    ..cubicTo(-22, 40, -36, 32, -38, 10)
    ..close();
  c.drawPath(body, k.fill(p.base));
  c.drawPath(body, k.outline);
  // 머리 꼭대기 볏
  k.oval(const Offset(2, -40), 22, 12, p.base);
  // 가슴
  k.oval(const Offset(10, 18), 34, 26, p.accent, stroke: false);
  // 얼굴 마스크
  final face = Path()
    ..moveTo(10, -22)
    ..cubicTo(30, -28, 44, -18, 42, -2)
    ..cubicTo(40, 12, 24, 14, 14, 6)
    ..cubicTo(6, 0, 4, -16, 10, -22)
    ..close();
  c.drawPath(face, k.fill(p.accent));
  c.drawPath(face, k.outline);
  // 눈두덩
  c.drawRRect(
      RRect.fromRectAndRadius(
          Rect.fromCenter(center: const Offset(25, -17), width: 30, height: 7),
          const Radius.circular(4)),
      k.fill(p.shade));
  k.eye(const Offset(22, -11), size: 4.6);
  // 콧구멍
  c.drawOval(Rect.fromCenter(center: const Offset(34, -2), width: 5, height: 4),
      k.fill(p.ink));
  c.drawOval(Rect.fromCenter(center: const Offset(39, -3), width: 4, height: 4),
      k.fill(p.ink));
  k.mouth(const Offset(30, 6), w: 9);
  k.frontArm(p.shade, len: 28, thick: 15);
}

// ---------------------------------------------------------------------------
// 바다사자: 매끈한 물방울 몸, 지느러미 팔, 수염
// ---------------------------------------------------------------------------
void _sealion(_Ctx k) {
  final c = k.c, p = k.p;
  // 뒷지느러미(발 대신)
  double a = 0;
  if (k.pose == Pose.run) a = math.sin(k.t * 18) * 0.3;
  c.save();
  c.translate(-20, 34);
  c.rotate(-0.3 + a);
  k.oval(Offset.zero, 30, 11, p.shade);
  c.restore();
  c.save();
  c.translate(8, 36);
  c.rotate(0.2 - a);
  k.oval(Offset.zero, 26, 10, p.shade);
  c.restore();
  // 몸(아래가 넓은 물방울)
  final body = Path()
    ..moveTo(-34, 30)
    ..cubicTo(-46, 0, -28, -30, 6, -40)
    ..cubicTo(30, -46, 46, -28, 42, -8)
    ..cubicTo(40, 10, 34, 36, 4, 40)
    ..cubicTo(-16, 42, -28, 38, -34, 30)
    ..close();
  c.drawPath(body, k.fill(p.base));
  // 배
  c.save();
  c.clipPath(body);
  k.oval(const Offset(16, 18), 40, 50, p.accent, stroke: false);
  c.restore();
  c.drawPath(body, k.outline);
  // 귀(작은 귓바퀴)
  k.oval(const Offset(8, -32), 7, 9, p.shade);
  // 주둥이
  k.oval(const Offset(34, -12), 22, 16, p.accent);
  c.drawOval(Rect.fromCenter(center: const Offset(43, -17), width: 9, height: 6),
      k.fill(p.ink));
  // 수염
  final w = Paint()
    ..color = p.ink.withValues(alpha: 0.7)
    ..strokeWidth = 1.4
    ..strokeCap = StrokeCap.round;
  for (var i = 0; i < 3; i++) {
    c.drawLine(Offset(38, -10.0 + i * 3), Offset(52, -13.0 + i * 5), w);
  }
  k.eye(const Offset(20, -22), size: 5.8);
  k.mouth(const Offset(34, -4), w: 6);
  // 앞지느러미
  final (at, ang) = k.armPose();
  c.save();
  c.translate(at.dx, at.dy);
  c.rotate(ang);
  final fin = Path()
    ..moveTo(-4, -6)
    ..quadraticBezierTo(22, -8, 30, 2)
    ..quadraticBezierTo(18, 8, -4, 6)
    ..close();
  c.drawPath(fin, k.fill(p.shade));
  c.drawPath(fin, k.outline);
  c.restore();
}

/// 배구공
void paintBall(Canvas canvas, double angle, {double radius = 20}) {
  canvas.save();
  canvas.rotate(angle);
  final r = radius;
  canvas.drawCircle(Offset.zero, r, Paint()..color = Colors.white);
  final seam = Paint()
    ..color = const Color(0xFF2F6FD6)
    ..style = PaintingStyle.stroke
    ..strokeWidth = r * 0.22;
  final yellow = Paint()
    ..color = const Color(0xFFFFC93C)
    ..style = PaintingStyle.stroke
    ..strokeWidth = r * 0.22;
  canvas.save();
  canvas.clipPath(Path()..addOval(Rect.fromCircle(center: Offset.zero, radius: r)));
  canvas.drawArc(Rect.fromCircle(center: Offset(-r, -r * 0.2), radius: r * 1.1),
      -0.6, 1.6, false, seam);
  canvas.drawArc(Rect.fromCircle(center: Offset(r * 0.9, r * 0.6), radius: r * 1.1),
      2.4, 1.6, false, yellow);
  canvas.drawArc(Rect.fromCircle(center: Offset(r * 0.2, -r * 1.2), radius: r * 1.1),
      0.9, 1.4, false, seam);
  canvas.restore();
  canvas.drawCircle(
      Offset.zero,
      r,
      Paint()
        ..color = const Color(0xFF1B2A44)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.2);
  canvas.restore();
}
