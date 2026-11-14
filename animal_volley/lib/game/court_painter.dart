// 해변 경기장 + 캐릭터 + 공을 그리는 Painter
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'characters.dart';
import 'world.dart';

class CourtPainter extends CustomPainter {
  final World world;
  final List<CharacterLook> looks;
  final double time;
  final Listenable repaintOn;

  CourtPainter({
    required this.world,
    required this.looks,
    required this.time,
    required this.repaintOn,
  }) : super(repaint: repaintOn);

  /// 화면 크기에 맞춰 800x450 논리 좌표를 얼마나 키울지
  static (double scale, Offset origin) fit(Size size) {
    final s = math.min(size.width / Court.width, size.height / Court.height);
    final origin = Offset((size.width - Court.width * s) / 2,
        (size.height - Court.height * s) / 2);
    return (s, origin);
  }

  @override
  void paint(Canvas canvas, Size size) {
    // 레터박스 영역도 하늘/모래로 채운다
    canvas.drawRect(Offset.zero & size, Paint()..color = const Color(0xFF8FD3F4));
    final (s, o) = fit(size);
    canvas.drawRect(
        Rect.fromLTRB(0, o.dy + 320 * s, size.width, size.height),
        Paint()..color = const Color(0xFFF6D99B));

    canvas.save();
    canvas.translate(o.dx, o.dy);
    canvas.scale(s);
    _background(canvas);
    _net(canvas);
    _shadows(canvas);
    _players(canvas);
    _ball(canvas);
    canvas.restore();
  }

  void _background(Canvas c) {
    const w = Court.width;
    final sky = Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [Color(0xFF6EC6F5), Color(0xFFBDE8FF)],
      ).createShader(const Rect.fromLTWH(0, 0, w, 300));
    c.drawRect(const Rect.fromLTWH(-400, 0, w + 800, 300), sky);
    // 해
    c.drawCircle(const Offset(680, 70), 34, Paint()..color = const Color(0xFFFFE27A));
    c.drawCircle(const Offset(680, 70), 46,
        Paint()..color = const Color(0x33FFE27A));
    // 구름
    final cloud = Paint()..color = Colors.white.withValues(alpha: 0.9);
    for (var i = 0; i < 3; i++) {
      final x = ((time * (8 + i * 4) + i * 300) % (w + 200)) - 100;
      final y = 50.0 + i * 38;
      c.drawOval(Rect.fromCenter(center: Offset(x, y), width: 70, height: 26), cloud);
      c.drawOval(Rect.fromCenter(center: Offset(x + 24, y - 10), width: 50, height: 30), cloud);
      c.drawOval(Rect.fromCenter(center: Offset(x - 22, y - 6), width: 40, height: 22), cloud);
    }
    // 바다
    c.drawRect(const Rect.fromLTWH(-400, 280, w + 800, 45),
        Paint()..color = const Color(0xFF3FA7D6));
    final wave = Paint()
      ..color = Colors.white.withValues(alpha: 0.6)
      ..strokeWidth = 2.5
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    for (var i = 0; i < 9; i++) {
      final x = i * 100.0 + math.sin(time + i) * 14;
      c.drawLine(Offset(x, 296 + (i % 2) * 12), Offset(x + 26, 296 + (i % 2) * 12), wave);
    }
    // 모래사장
    c.drawRect(const Rect.fromLTWH(-400, 320, w + 800, 200),
        Paint()..color = const Color(0xFFF6D99B));
    c.drawRect(const Rect.fromLTWH(-400, 320, w + 800, 8),
        Paint()..color = const Color(0xFFFFF0C9));
    // 코트 라인
    c.drawLine(const Offset(10, Court.groundY + 2), const Offset(w - 10, Court.groundY + 2),
        Paint()
          ..color = Colors.white.withValues(alpha: 0.85)
          ..strokeWidth = 3);
    // 모래 점
    final dot = Paint()..color = const Color(0xFFE2BE78);
    final rng = math.Random(7);
    for (var i = 0; i < 60; i++) {
      c.drawCircle(Offset(rng.nextDouble() * w, 335 + rng.nextDouble() * 110),
          1.2 + rng.nextDouble(), dot);
    }
  }

  void _net(Canvas c) {
    const x = Court.netX, top = Court.netTopY;
    // 기둥
    c.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromLTRB(x - Court.netHalfW, top, x + Court.netHalfW, Court.groundY + 4),
            const Radius.circular(4)),
        Paint()..color = const Color(0xFF5A6273));
    // 그물
    const meshTop = top + 6, meshBottom = top + 78;
    final mesh = Paint()
      ..color = Colors.white.withValues(alpha: 0.75)
      ..strokeWidth = 1.2;
    for (var y = meshTop; y <= meshBottom; y += 9) {
      c.drawLine(Offset(x - 5, y), Offset(x + 5, y), mesh);
    }
    c.drawRect(Rect.fromLTRB(x - 8, top - 2, x + 8, top + 8),
        Paint()..color = Colors.white);
    c.drawCircle(const Offset(x, top), Court.netHalfW + 1,
        Paint()..color = const Color(0xFFE85D5D));
  }

  void _shadows(Canvas c) {
    final sh = Paint()..color = const Color(0x33000000);
    for (final p in world.players) {
      if (world.solo && p.side == 1) continue;
      final h = (p.groundCenterY - p.y).clamp(0, 200) / 200;
      final w = 60 * (1 - h * 0.5);
      c.drawOval(
          Rect.fromCenter(center: Offset(p.x, Court.groundY + 3), width: w, height: 10),
          sh);
    }
    final b = world.ball;
    final h = ((Court.groundY - b.y) / 400).clamp(0.0, 1.0);
    c.drawOval(
        Rect.fromCenter(
            center: Offset(b.x, Court.groundY + 3),
            width: 34 * (1 - h * 0.6),
            height: 7),
        sh);
  }

  Pose _poseFor(int i) {
    final p = world.players[i];
    if (world.phase == Phase.gameOver) {
      return world.winner == i ? Pose.win : Pose.lose;
    }
    if (world.phase == Phase.point && world.phaseTimer < 60) {
      return world.lastScorer == i ? Pose.win : Pose.lose;
    }
    switch (p.state) {
      case PlayerState.dive:
        return Pose.dive;
      case PlayerState.air:
        return p.spikeTimer > 0 ? Pose.spike : Pose.jump;
      case PlayerState.ground:
        return p.vx.abs() > 0.5 ? Pose.run : Pose.idle;
    }
  }

  void _players(Canvas c) {
    for (var i = 0; i < 2; i++) {
      if (world.solo && i == 1) continue;
      final p = world.players[i];
      c.save();
      c.translate(p.x, p.y);
      int facing = p.forward;
      if (p.state == PlayerState.dive) facing = p.diveDir;
      paintCharacter(c, looks[i], _poseFor(i), time + i * 0.37,
          facing: facing, hitFlash: p.hitFlash / 10);
      c.restore();
    }
  }

  void _ball(Canvas c) {
    final b = world.ball;
    if (b.powerTrail > 0) {
      for (var k = 4; k >= 1; k--) {
        final a = 0.12 * (5 - k) * (b.powerTrail / 40);
        c.drawCircle(Offset(b.x - b.vx * k * 1.2, b.y - b.vy * k * 1.2),
            Tuning.ballRadius * (1 - k * 0.08),
            Paint()..color = const Color(0xFFFF8A3D).withValues(alpha: a));
      }
    }
    c.save();
    c.translate(b.x, b.y);
    paintBall(c, b.angle, radius: Tuning.ballRadius);
    c.restore();
  }

  @override
  bool shouldRepaint(covariant CourtPainter old) => true;
}
