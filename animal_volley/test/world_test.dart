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
}
