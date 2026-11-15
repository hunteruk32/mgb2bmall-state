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

  test('스파이크 범위: 몸에서 조금 떨어진 공도 스파이크로 칠 수 있다', () {
    final w = World();
    w.phase = Phase.playing;
    final p = w.players[0];
    p
      ..x = 300
      ..y = 220
      ..state = PlayerState.air
      ..spikeTimer = 5;
    // 몸 판정(56)보다 멀고 스파이크 범위(78)보다 가까운 거리
    w.ball..x = 300 + 50..y = 220 - 45..vx = 0..vy = 0;
    w.step([Input.hit, 0]);
    expect(w.lastSpikeSide, 0);
    // 스파이크가 아니면 같은 거리의 공에 닿지 않는다
    final w2 = World();
    w2.phase = Phase.playing;
    w2.players[0]..x = 300..y = 220..state = PlayerState.air;
    w2.ball..x = 350..y = 175..vx = 0..vy = 0;
    w2.step([0, 0]);
    expect(w2.events, isNot(contains(GameEvent.hit)));
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

  group('8방향 스파이크', () {
    // 네트 근처에서 점프한 상태로 스파이크했을 때 공이 어디에 떨어지는지
    (SpikeDir, double) spikeAndLand(SpikeDir dir, {int side = 0}) {
      final w = World();
      w.phase = Phase.playing;
      final p = w.players[side];
      final o = w.players[1 - side];
      o.x = side == 0 ? 780 : 20; // 상대는 구석에 (방해 안 되게)
      final nearNet = side == 0 ? 330.0 : 470.0;
      p
        ..x = nearNet
        ..y = 205 // 점프 꼭대기 근처
        ..vy = 0
        ..state = PlayerState.air
        ..spikeTimer = 5;
      w.ball
        ..x = nearNet + p.forward * 15
        ..y = 150
        ..vx = 0
        ..vy = 1;
      final inputs = [0, 0];
      inputs[side] = dir.inputFor(p.forward) | Input.hit;
      // 공에 닿을 때까지 방향을 누르고 있는다
      for (var i = 0; i < 20 && w.lastSpikeSide < 0; i++) {
        w.step(inputs);
        inputs[side] &= ~Input.hit; // 스파이크 버튼은 한 번만
      }
      expect(w.lastSpikeSide, side, reason: '스파이크가 맞지 않음');
      final got = w.lastSpike;
      for (var i = 0; i < 400 && w.phase == Phase.playing; i++) {
        w.step([0, 0]);
      }
      return (got, w.ball.x);
    }

    for (final dir in SpikeDir.values) {
      test('${dir.label}: 방향이 인식되고 상대 코트에 떨어진다', () {
        for (final side in [0, 1]) {
          final (got, landX) = spikeAndLand(dir, side: side);
          expect(got, dir, reason: 'side $side');
          if (side == 0) {
            expect(landX, greaterThan(Court.netX), reason: 'side 0 land $landX');
          } else {
            expect(landX, lessThan(Court.netX), reason: 'side 1 land $landX');
          }
          // ignore: avoid_print
          if (side == 0) print('${dir.label}: ${landX.toStringAsFixed(0)}');
        }
      });
    }

    test('입력 → 방향 해석', () {
      SpikeDir d(int input, int f) => SpikeDirInfo.fromInput(input, f);
      expect(d(0, 1), SpikeDir.normal);
      expect(d(Input.right | Input.down, 1), SpikeDir.forwardDown);
      expect(d(Input.left | Input.down, -1), SpikeDir.forwardDown); // 오른쪽 선수는 왼쪽이 앞
      expect(d(Input.right, -1), SpikeDir.back);
      expect(d(Input.up, 1), SpikeDir.up);
      expect(d(Input.right | Input.up, 1), SpikeDir.forwardUp);
      expect(d(Input.down, 1), SpikeDir.down);
    });
  });
}
