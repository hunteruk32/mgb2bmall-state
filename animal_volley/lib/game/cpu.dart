// 연습 모드용 컴퓨터 상대
import 'dart:math' as math;
import 'world.dart';

enum CpuLevel { easy, normal, hard }

extension CpuLevelName on CpuLevel {
  String get label => switch (this) {
        CpuLevel.easy => '쉬움',
        CpuLevel.normal => '보통',
        CpuLevel.hard => '어려움',
      };
}

class CpuBrain {
  final int side;
  final CpuLevel level;
  final math.Random _rng;
  int _thinkDelay = 0;
  int _held = 0;
  SpikeDir _spikeChoice = SpikeDir.normal;
  double _offset = 0;

  CpuBrain(this.side, {this.level = CpuLevel.normal, int? seed})
      : _rng = math.Random(seed);

  // 난이도별 반응 속도 / 실수 정도
  int get _baseDelay => switch (level) {
        CpuLevel.easy => 7,
        CpuLevel.normal => 3,
        CpuLevel.hard => 1,
      };
  double get _sloppiness => switch (level) {
        CpuLevel.easy => 46,
        CpuLevel.normal => 22,
        CpuLevel.hard => 8,
      };
  double get _attackChance => switch (level) {
        CpuLevel.easy => 0.25,
        CpuLevel.normal => 0.6,
        CpuLevel.hard => 0.9,
      };

  /// 공이 내 몸 높이까지 내려올 때의 x 위치를 대략 예측한다.
  double _predictX(World w) {
    double x = w.ball.x, y = w.ball.y, vx = w.ball.vx, vy = w.ball.vy;
    const r = Tuning.ballRadius;
    final targetY = Court.groundY - Tuning.playerRadius * 2.2;
    for (var i = 0; i < 160; i++) {
      vy += Tuning.ballGravity;
      x += vx;
      y += vy;
      if (x < r) {
        x = r;
        vx = vx.abs();
      } else if (x > Court.width - r) {
        x = Court.width - r;
        vx = -vx.abs();
      }
      if (vy > 0 && y >= targetY) break;
    }
    return x;
  }

  int think(World w) {
    final me = w.players[side];
    final b = w.ball;
    final f = me.forward;
    final mySide = side == 0 ? b.x < Court.netX : b.x > Court.netX;

    if (w.phase == Phase.point || w.phase == Phase.gameOver) return 0;

    // 사람처럼 약간의 반응 지연
    if (_thinkDelay > 0) {
      _thinkDelay--;
      return _held;
    }
    _thinkDelay = _baseDelay + _rng.nextInt(3);

    int input = 0;
    final landX = _predictX(w);
    final landsMine =
        side == 0 ? landX < Court.netX : landX > Court.netX;

    double target;
    if (landsMine || mySide) {
      if (_rng.nextDouble() < 0.05) {
        _offset = (_rng.nextDouble() - 0.3) * _sloppiness;
      }
      // 공보다 살짝 뒤(네트 반대쪽)에 서야 앞으로 쳐 보낼 수 있다
      target = landX - f * (14 + _offset);
    } else {
      target = side == 0 ? 170 : Court.width - 170;
    }

    final dx = target - me.x;
    if (dx.abs() > 8) input |= dx > 0 ? Input.right : Input.left;

    final distX = (b.x - me.x).abs();
    final above = me.y - b.y;

    if (me.state == PlayerState.ground && mySide) {
      // 점프해서 스파이크할 타이밍
      if (distX < 60 && above > 90 && above < 210 && b.vy > -3 &&
          (b.x - Court.netX).abs() < 260 &&
          _rng.nextDouble() < _attackChance) {
        input |= Input.jump;
        // 공격적인 방향을 더 자주 고른다
        const choices = [
          SpikeDir.normal, SpikeDir.normal, SpikeDir.forward, SpikeDir.forward,
          SpikeDir.forwardDown, SpikeDir.forwardDown, SpikeDir.down,
          SpikeDir.forwardUp, SpikeDir.up, SpikeDir.back,
        ];
        _spikeChoice = choices[_rng.nextInt(choices.length)];
      }
      // 너무 멀면 다이빙
      final dist = landX - me.x;
      if (landsMine && dist.abs() > 110 && b.vy > 4 && b.y > 250 &&
          _rng.nextDouble() < _attackChance * 0.8) {
        input |= Input.hit | (dist > 0 ? Input.right : Input.left);
        input &= ~(dist > 0 ? Input.left : Input.right);
      }
    }

    if (me.state == PlayerState.air) {
      final d = math.sqrt(math.pow(b.x - me.x, 2) + math.pow(b.y - me.y, 2));
      if (d < 85) {
        input |= Input.hit;
        input &= ~(Input.left | Input.right | Input.down);
        input |= _spikeChoice.inputFor(f);
      }
    }

    // 버튼은 매번 새로 눌러야 하므로 직전에 누르고 있던 점프/히트는 한 번 뗀다
    // (공중에서는 위 방향 = 스파이크 방향이라 그대로 둔다)
    if (me.state == PlayerState.ground && _held & Input.jump != 0) {
      input &= ~Input.jump;
    }
    if (_held & Input.hit != 0) input &= ~Input.hit;

    _held = input;
    return input;
  }
}
