// 캐릭터 시안 확인용 화면 (개발용)
import 'package:flutter/material.dart';
import '../game/characters.dart';

void main() => runApp(const MaterialApp(debugShowCheckedModeBanner: false, home: _P()));

class _P extends StatelessWidget {
  const _P();
  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: const Color(0xFFFFF4DC),
        body: CustomPaint(size: Size.infinite, painter: _Painter()),
      );
}

class _Painter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    const poses = [Pose.idle, Pose.run, Pose.jump, Pose.spike, Pose.dive, Pose.win, Pose.lose];
    for (var a = 0; a < 4; a++) {
      for (var i = 0; i < 4; i++) {
        canvas.save();
        canvas.translate(70 + i * 110.0, 70 + a * 120.0);
        canvas.scale(1.1);
        paintCharacter(canvas, CharacterLook(Animal.values[a], i), Pose.idle, 0.3);
        canvas.restore();
      }
      for (var j = 0; j < poses.length; j++) {
        canvas.save();
        canvas.translate(520 + j * 100.0, 70 + a * 120.0);
        paintCharacter(canvas, CharacterLook(Animal.values[a], 0), poses[j], 0.13, facing: j.isOdd ? -1 : 1);
        canvas.restore();
      }
    }
    canvas.save();
    canvas.translate(60, 540);
    paintBall(canvas, 0.4, radius: 24);
    canvas.restore();
  }
  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
