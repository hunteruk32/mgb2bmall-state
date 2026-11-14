// 앱 아이콘을 그리는 개발용 화면.
// ?layer=full | fg | bg 로 레이어를 골라 1024x1024로 렌더링한 뒤
// tools/make_icons.py가 안드로이드 아이콘 크기로 잘라 넣는다.
import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../game/characters.dart';

void main() {
  final layer = Uri.base.queryParameters['layer'] ?? 'full';
  runApp(MaterialApp(
    debugShowCheckedModeBanner: false,
    color: Colors.transparent,
    home: ColoredBox(
      color: Colors.transparent,
      child: Align(
        alignment: Alignment.topLeft,
        child: CustomPaint(size: const Size(1024, 1024), painter: IconPainter(layer)),
      ),
    ),
  ));
}

class IconPainter extends CustomPainter {
  final String layer;
  IconPainter(this.layer);

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.width / 100; // 100 x 100 단위로 그린다
    canvas.scale(s);
    if (layer != 'fg') _background(canvas);
    if (layer != 'bg') {
      // 적응형 아이콘은 가운데 약 66%만 안전하게 보이므로 전경을 조금 줄인다
      if (layer == 'fg') {
        canvas.translate(50, 50);
        canvas.scale(0.72);
        canvas.translate(-50, -50);
      }
      _foreground(canvas);
    }
  }

  void _background(Canvas c) {
    c.drawRect(
      const Rect.fromLTWH(0, 0, 100, 100),
      Paint()
        ..shader = const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF4FB8F0), Color(0xFFA8E2FF)],
        ).createShader(const Rect.fromLTWH(0, 0, 100, 72)),
    );
    // 구름
    final cloud = Paint()..color = Colors.white.withValues(alpha: 0.85);
    c.drawOval(Rect.fromCenter(center: const Offset(20, 18), width: 18, height: 7), cloud);
    c.drawOval(Rect.fromCenter(center: const Offset(25, 15), width: 12, height: 8), cloud);
    // 바다
    c.drawRect(const Rect.fromLTWH(0, 66, 100, 10), Paint()..color = const Color(0xFF3FA7D6));
    // 모래
    c.drawRect(const Rect.fromLTWH(0, 74, 100, 26), Paint()..color = const Color(0xFFF6D99B));
    c.drawRect(const Rect.fromLTWH(0, 74, 100, 2), Paint()..color = const Color(0xFFFFF0C9));
  }

  void _foreground(Canvas c) {
    // 공 잔상
    for (var k = 3; k >= 1; k--) {
      c.drawCircle(
        Offset(69 - k * 5.0, 31 + k * 3.5),
        9.5 - k * 0.8,
        Paint()..color = const Color(0xFFFF8A3D).withValues(alpha: 0.18 * (4 - k)),
      );
    }
    // 그림자
    c.drawOval(Rect.fromCenter(center: const Offset(44, 86), width: 34, height: 5),
        Paint()..color = const Color(0x33000000));
    // 돼지 (스파이크 자세)
    c.save();
    c.translate(42, 56);
    c.scale(0.5);
    paintCharacter(c, const CharacterLook(Animal.pig, 0), Pose.spike, 0.2);
    c.restore();
    // 공
    c.save();
    c.translate(70, 29);
    c.rotate(0.3);
    paintBall(c, 0, radius: 11);
    c.restore();
    // 반짝임
    final star = Paint()..color = Colors.white;
    for (final (o, r) in [(const Offset(84, 18), 2.2), (const Offset(86, 40), 1.6)]) {
      final p = Path();
      for (var i = 0; i < 8; i++) {
        final a = i * math.pi / 4;
        final rr = i.isEven ? r * 1.8 : r * 0.5;
        final pt = o + Offset(math.cos(a) * rr, math.sin(a) * rr);
        i == 0 ? p.moveTo(pt.dx, pt.dy) : p.lineTo(pt.dx, pt.dy);
      }
      p.close();
      c.drawPath(p, star);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
