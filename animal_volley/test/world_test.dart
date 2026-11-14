import 'package:flutter_test/flutter_test.dart';
import 'package:animal_volley/game/world.dart';
import 'package:animal_volley/game/cpu.dart';

void main() {
  test('서브 공이 떨어지면 서브한 쪽 코트에 닿아 상대가 득점한다', () {
    final w = World();
    for (var i = 0; i < 400 && w.phase != Phase.point; i++) {
      w.step([0, 0]);
    }
    // 왼쪽 선수 머리 위에서 떨어지므로 몸에 맞고 튀어 어딘가에 떨어진다
    expect(w.phase, Phase.point);
    expect(w.scores[0] + w.scores[1], 1);
  });

  test('공을 아무도 안 받으면 공이 떨어진 쪽의 상대가 점수를 얻는다', () {
    final w = World();
    w.phase = Phase.playing;
    w.players[0].x = 40;
    w.players[1].x = 760;
    w.ball
      ..x = 600
      ..y = 100
      ..vx = 0
      ..vy = 0;
    for (var i = 0; i < 200 && w.phase == Phase.playing; i++) {
      w.step([0, 0]);
    }
    expect(w.scores, [1, 0]);
  });

  test('점프 후 착지하고, 선수는 네트를 넘지 못한다', () {
    final w = World();
    final p = w.players[0];
    w.step([Input.jump, 0]);
    expect(p.state, PlayerState.air);
    for (var i = 0; i < 200; i++) {
      w.step([Input.right, 0]);
    }
    expect(p.state, PlayerState.ground);
    expect(p.x, lessThanOrEqualTo(Court.netX - Court.netHalfW - Tuning.playerRadius));
  });

  test('공중에서 스파이크하면 공이 상대 쪽으로 빠르게 날아간다', () {
    final w = World();
    w.phase = Phase.playing;
    final p = w.players[0];
    p.x = 300;
    p.y = 250;
    p.state = PlayerState.air;
    p.spikeTimer = 5;
    w.ball
      ..x = 320
      ..y = 200
      ..vx = 0
      ..vy = 1;
    w.step([0, 0]);
    expect(w.ball.vx, greaterThan(10));
    expect(w.events, contains(GameEvent.spike));
  });

  test('공은 네트를 통과하지 못한다', () {
    final w = World();
    w.phase = Phase.playing;
    w.players[0].x = 40;
    w.players[1].x = 760;
    w.ball
      ..x = 360
      ..y = 330
      ..vx = 12
      ..vy = -1;
    for (var i = 0; i < 10; i++) {
      w.step([0, 0]);
    }
    expect(w.ball.x, lessThan(Court.netX));
  });

  test('스냅샷을 주고받으면 상태가 그대로 복원된다', () {
    final a = World();
    for (var i = 0; i < 77; i++) {
      a.step([i % 3 == 0 ? Input.right : 0, Input.left | (i % 20 == 0 ? Input.jump : 0)]);
    }
    final b = World(authoritative: false)..applySnapshot(a.toSnapshot());
    expect(b.frame, a.frame);
    expect(b.scores, a.scores);
    expect(b.phase, a.phase);
    expect(b.ball.x, closeTo(a.ball.x, 1e-3));
    expect(b.players[1].y, closeTo(a.players[1].y, 1e-3));
    expect(b.players[1].state, a.players[1].state);
  });

  test('CPU끼리 붙이면 경기가 끝까지 진행된다(15점)', () {
    for (final level in CpuLevel.values) {
      final w = World();
      final c0 = CpuBrain(0, level: level, seed: 1);
      final c1 = CpuBrain(1, level: level, seed: 2);
      var frames = 0;
      while (w.phase != Phase.gameOver && frames < 60 * 60 * 30) {
        w.step([c0.think(w), c1.think(w)]);
        frames++;
      }
      expect(w.phase, Phase.gameOver, reason: '$level');
      expect(w.scores.reduce((a, b) => a > b ? a : b), Tuning.winScore);
      // ignore: avoid_print
      print('$level: ${w.scores} in ${(frames / 60).toStringAsFixed(0)}s');
    }
  });

  test('서브 연습: 상대 없이 공이 계속 다시 올라오고 기록이 쌓인다', () {
    final w = World(solo: true);
    final cpu = CpuBrain(0, level: CpuLevel.hard, seed: 3);
    for (var i = 0; i < 60 * 120; i++) {
      w.step([cpu.think(w), Input.left | Input.jump | Input.hit]);
      expect(w.phase, isNot(Phase.gameOver));
      // 오른쪽 선수는 경기장 밖에 있고 움직이지 않는다
      expect(w.players[1].x, greaterThan(Court.width));
    }
    expect(w.practiceTries, greaterThan(10));
    expect(w.practiceSuccess, greaterThan(0));
    expect(w.practiceSuccess, lessThanOrEqualTo(w.practiceTries));
    expect(w.bestStreak, greaterThanOrEqualTo(w.streak));
    expect(w.scores, [0, 0]);
  });

  test('서브 연습: 내 코트에 떨어지면 실패, 넘기면 성공', () {
    final w = World(solo: true);
    w.phase = Phase.playing;
    w.players[0].x = 40;
    w.ball..x = 200..y = 300..vx = 0..vy = 0;
    for (var i = 0; i < 100 && w.phase == Phase.playing; i++) {
      w.step([0, 0]);
    }
    expect(w.practiceTries, 1);
    expect(w.lastPracticeSuccess, isFalse);
    // 다음 서브가 시작되기를 기다린 뒤, 상대 코트로 공을 보낸다
    for (var i = 0; i < 100 && w.phase != Phase.serve; i++) {
      w.step([0, 0]);
    }
    w.phase = Phase.playing;
    w.players[0].x = 40;
    w.ball..x = 600..y = 300..vx = 0..vy = 0;
    for (var i = 0; i < 100 && w.phase == Phase.playing; i++) {
      w.step([0, 0]);
    }
    expect(w.practiceTries, 2);
    expect(w.practiceSuccess, 1);
    expect(w.lastPracticeSuccess, isTrue);
  });

  test('공 속도 설정: 궤적은 같고 빨라질수록 더 일찍 떨어진다', () {
    int framesToLand(double speed) {
      final w = World(ballSpeed: speed);
      w.phase = Phase.playing;
      w.players[0].x = 40;
      w.players[1].x = 760;
      w.ball..x = 300..y = 80..vx = 3..vy = -4;
      var n = 0;
      while (w.phase == Phase.playing && n < 1000) {
        w.step([0, 0]);
        n++;
      }
      return n;
    }
    final slow = framesToLand(0.6), normal = framesToLand(1.0), fast = framesToLand(1.6);
    expect(slow, greaterThan(normal));
    expect(normal, greaterThan(fast));
  });

  test('이동 속도 설정: 빠를수록 같은 시간에 더 멀리 간다', () {
    double distance(double move) {
      final w = World(moveSpeed: move);
      final x0 = w.players[0].x;
      for (var i = 0; i < 20; i++) {
        w.step([Input.right, 0]);
      }
      return w.players[0].x - x0;
    }
    expect(distance(1.5), greaterThan(distance(1.0) * 1.4));
    expect(distance(0.6), lessThan(distance(1.0) * 0.7));
  });
}
