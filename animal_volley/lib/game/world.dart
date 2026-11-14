// 게임 물리/규칙. Flutter에 의존하지 않는 순수 Dart 코드라 테스트하기 쉽다.
//
// 좌표계: 가로 800 x 세로 450 (논리 단위), y는 아래로 증가.
// 고정 60fps 스텝 기준으로 값이 정해져 있다.

import 'dart:math' as math;
import 'dart:typed_data';

class Court {
  static const double width = 800;
  static const double height = 450;
  static const double groundY = 400;
  static const double netX = 400;
  static const double netHalfW = 6;
  static const double netTopY = 250;
}

class Tuning {
  static const double playerRadius = 36;
  static const double moveSpeed = 6.2;
  static const double jumpSpeed = 15.5;
  static const double playerGravity = 0.75;

  static const double ballRadius = 20;
  static const double ballGravity = 0.36;
  static const double ballMaxSpeed = 21;

  static const int diveFrames = 32;
  static const double diveSpeed = 10;
  static const int spikeFrames = 14; // 스파이크 판정이 유지되는 프레임
  static const int hitCooldown = 8;

  static const int pointPauseFrames = 80;
  static const int winScore = 15;
}

/// 입력 비트
class Input {
  static const int left = 1;
  static const int right = 2;
  static const int jump = 4;
  static const int hit = 8;
}

enum PlayerState { ground, air, dive }

enum Phase { serve, playing, point, gameOver }

class Player {
  final int side; // 0 = 왼쪽(P1), 1 = 오른쪽(P2)
  double x = 0, y = 0, vx = 0, vy = 0;
  PlayerState state = PlayerState.ground;
  int spikeTimer = 0; // >0 이면 스파이크 동작 중
  int diveTimer = 0;
  int diveDir = 0;
  int hitCooldown = 0;
  int prevInput = 0;

  /// 화면 연출용(물리에 영향 없음): 공을 친 직후 반짝임 등
  int hitFlash = 0;

  /// 환경설정의 '캐릭터 이동 속도' 배율
  double speedScale = 1.0;

  Player(this.side) {
    reset();
  }

  double get minX => side == 0
      ? Tuning.playerRadius
      : Court.netX + Court.netHalfW + Tuning.playerRadius;
  double get maxX => side == 0
      ? Court.netX - Court.netHalfW - Tuning.playerRadius
      : Court.width - Tuning.playerRadius;

  /// 상대 코트 방향 (+1 오른쪽, -1 왼쪽)
  int get forward => side == 0 ? 1 : -1;

  double get groundCenterY => Court.groundY - Tuning.playerRadius;

  void reset() {
    x = side == 0 ? 160 : Court.width - 160;
    y = groundCenterY;
    vx = vy = 0;
    state = PlayerState.ground;
    spikeTimer = diveTimer = hitCooldown = hitFlash = 0;
    diveDir = 0;
  }

  void step(int input) {
    final pressed = input & ~prevInput;
    prevInput = input;
    int dir = 0;
    if (input & Input.left != 0) dir -= 1;
    if (input & Input.right != 0) dir += 1;

    if (hitCooldown > 0) hitCooldown--;
    if (hitFlash > 0) hitFlash--;

    switch (state) {
      case PlayerState.ground:
        vx = dir * Tuning.moveSpeed * speedScale;
        if (pressed & Input.jump != 0) {
          vy = -Tuning.jumpSpeed;
          state = PlayerState.air;
        } else if (pressed & Input.hit != 0 && dir != 0) {
          // 다이빙
          state = PlayerState.dive;
          diveTimer = Tuning.diveFrames;
          diveDir = dir;
          vx = dir * Tuning.diveSpeed * speedScale;
          vy = -4;
        }
        break;
      case PlayerState.air:
        vx = dir * Tuning.moveSpeed * speedScale;
        if (pressed & Input.hit != 0 && spikeTimer == 0) {
          spikeTimer = Tuning.spikeFrames;
        }
        break;
      case PlayerState.dive:
        vx *= 0.94;
        diveTimer--;
        break;
    }

    if (spikeTimer > 0) spikeTimer--;

    vy += Tuning.playerGravity;
    x += vx;
    y += vy;

    if (x < minX) x = minX;
    if (x > maxX) x = maxX;

    if (y >= groundCenterY) {
      y = groundCenterY;
      vy = 0;
      if (state == PlayerState.air) {
        state = PlayerState.ground;
        spikeTimer = 0;
      } else if (state == PlayerState.dive && diveTimer <= 0) {
        state = PlayerState.ground;
        vx = 0;
      }
    }
  }
}

class Ball {
  double x = 0, y = 0, vx = 0, vy = 0;
  double angle = 0; // 회전(연출용)
  int powerTrail = 0; // 스파이크 공 잔상 표시 프레임

  void placeForServe(int side) {
    x = side == 0 ? 160 : Court.width - 160;
    y = 110;
    vx = 0;
    vy = 0;
    powerTrail = 0;
  }
}

/// 사운드/진동 같은 연출용 이벤트
enum GameEvent { hit, spike, net, wall, ground, point, win, jump, dive, serve }

class World {
  final players = [Player(0), Player(1)];
  final ball = Ball();
  final scores = [0, 0];
  Phase phase = Phase.serve;
  int phaseTimer = 0;
  int server = 0;
  int lastScorer = -1;
  int frame = 0;
  final int winScore;

  /// false면 득점 판정을 하지 않는다(블루투스 게스트 쪽 예측 시뮬레이션용).
  bool authoritative;

  /// 환경설정의 '공 속도' 배율. 궤적은 그대로 두고 시간만 빠르게/느리게 흐른다.
  final double ballSpeed;

  /// 서브 연습 모드: 오른쪽 선수 없이 왼쪽 선수 혼자 계속 서브한다.
  final bool solo;

  /// 서브 연습 기록
  int practiceTries = 0, practiceSuccess = 0, streak = 0, bestStreak = 0;
  bool lastPracticeSuccess = false;

  final List<GameEvent> events = [];

  World({
    this.winScore = Tuning.winScore,
    this.authoritative = true,
    this.ballSpeed = 1.0,
    double moveSpeed = 1.0,
    this.solo = false,
  }) {
    for (final p in players) {
      p.speedScale = moveSpeed;
    }
    startRound(0);
  }

  /// 서브 연습에서 오른쪽 선수는 경기장 밖에 세워 둔다
  void _parkSolo() {
    if (!solo) return;
    final p = players[1];
    p.x = Court.width + 400;
    p.y = p.groundCenterY;
    p.vx = p.vy = 0;
  }

  int? get winner {
    if (phase != Phase.gameOver) return null;
    return scores[0] > scores[1] ? 0 : 1;
  }

  void startRound(int serveSide) {
    server = serveSide;
    for (final p in players) {
      p.reset();
    }
    ball.placeForServe(serveSide);
    phase = Phase.serve;
    phaseTimer = 30;
    _parkSolo();
    events.add(GameEvent.serve);
  }

  void restart() {
    scores[0] = scores[1] = 0;
    practiceTries = practiceSuccess = streak = bestStreak = 0;
    lastScorer = -1;
    startRound(0);
  }

  /// 한 프레임 진행. inputs[0] = 왼쪽 플레이어, inputs[1] = 오른쪽 플레이어
  void _stepPlayers(List<int> inputs) {
    for (var i = 0; i < 2; i++) {
      if (solo && i == 1) continue;
      final p = players[i];
      final before = p.state;
      p.step(inputs[i]);
      if (before == PlayerState.ground && p.state == PlayerState.air) {
        events.add(GameEvent.jump);
      } else if (before != PlayerState.dive && p.state == PlayerState.dive) {
        events.add(GameEvent.dive);
      }
    }
  }

  void step(List<int> inputs) {
    frame++;
    events.clear();

    switch (phase) {
      case Phase.serve:
        _stepPlayers(inputs);
        // 서브 공은 잠깐 떠 있다가 떨어진다
        if (phaseTimer > 0) {
          phaseTimer--;
        } else {
          phase = Phase.playing;
        }
        _collidePlayers();
        break;
      case Phase.playing:
        _stepPlayers(inputs);
        _stepBall();
        _collidePlayers();
        break;
      case Phase.point:
        _stepPlayers(const [0, 0]);
        if (ball.y < Court.groundY - Tuning.ballRadius) {
          _stepBall(scoring: false);
        }
        if (authoritative) {
          phaseTimer--;
          if (phaseTimer <= 0) {
            if (solo) {
              startRound(0);
            } else if (scores[lastScorer] >= winScore) {
              phase = Phase.gameOver;
              events.add(GameEvent.win);
            } else {
              startRound(lastScorer);
            }
          }
        }
        break;
      case Phase.gameOver:
        _stepPlayers(const [0, 0]);
        break;
    }
  }

  void _stepBall({bool scoring = true}) {
    final b = ball;
    final s = ballSpeed;
    b.vy += Tuning.ballGravity * s;
    b.x += b.vx * s;
    b.y += b.vy * s;
    b.angle += b.vx * 0.04 * s;
    if (b.powerTrail > 0) b.powerTrail--;

    const r = Tuning.ballRadius;

    // 벽
    if (b.x < r) {
      b.x = r;
      b.vx = b.vx.abs() * 0.9;
      events.add(GameEvent.wall);
    } else if (b.x > Court.width - r) {
      b.x = Court.width - r;
      b.vx = -b.vx.abs() * 0.9;
      events.add(GameEvent.wall);
    }
    // 천장
    if (b.y < r) {
      b.y = r;
      b.vy = b.vy.abs() * 0.6;
    }

    _collideNet();

    // 바닥
    if (b.y >= Court.groundY - r) {
      b.y = Court.groundY - r;
      if (scoring && phase == Phase.playing) {
        events.add(GameEvent.ground);
        if (authoritative && solo) {
          // 서브 연습: 네트 너머에 떨어지면 성공
          final ok = b.x > Court.netX;
          practiceTries++;
          lastPracticeSuccess = ok;
          if (ok) {
            practiceSuccess++;
            streak++;
            if (streak > bestStreak) bestStreak = streak;
          } else {
            streak = 0;
          }
          lastScorer = ok ? 0 : 1;
          phase = Phase.point;
          phaseTimer = 55;
          events.add(GameEvent.point);
        } else if (authoritative) {
          final scorer = b.x < Court.netX ? 1 : 0;
          scores[scorer]++;
          lastScorer = scorer;
          phase = Phase.point;
          phaseTimer = Tuning.pointPauseFrames;
          events.add(GameEvent.point);
        }
        b.vy = -b.vy.abs() * 0.45;
        b.vx *= 0.6;
      } else {
        b.vy = -b.vy.abs() * 0.45;
        b.vx *= 0.8;
        if (b.vy.abs() < 1.5) b.vy = 0;
      }
    }
  }

  void _collideNet() {
    final b = ball;
    const r = Tuning.ballRadius;
    const left = Court.netX - Court.netHalfW;
    const right = Court.netX + Court.netHalfW;

    if (b.y < Court.netTopY) {
      // 네트 꼭대기(둥근 캡)
      final dx = b.x - Court.netX;
      final dy = b.y - Court.netTopY;
      final d = math.sqrt(dx * dx + dy * dy);
      final minD = r + Court.netHalfW;
      if (d < minD && d > 0) {
        final nx = dx / d, ny = dy / d;
        b.x = Court.netX + nx * minD;
        b.y = Court.netTopY + ny * minD;
        final dot = b.vx * nx + b.vy * ny;
        if (dot < 0) {
          b.vx = (b.vx - 2 * dot * nx) * 0.8;
          b.vy = (b.vy - 2 * dot * ny) * 0.8;
        }
        events.add(GameEvent.net);
      }
    } else if (b.x + r > left && b.x - r < right) {
      // 네트 기둥 옆면
      if (b.x < Court.netX) {
        b.x = left - r;
        b.vx = -b.vx.abs() * 0.7;
      } else {
        b.x = right + r;
        b.vx = b.vx.abs() * 0.7;
      }
      events.add(GameEvent.net);
    }
  }

  void _collidePlayers() {
    if (phase != Phase.playing && phase != Phase.serve) return;
    final b = ball;
    for (final p in players) {
      if (solo && p.side == 1) continue;
      if (p.hitCooldown > 0) continue;
      // 다이빙 중에는 몸이 납작해지므로 판정 중심을 조금 내린다
      final py = p.state == PlayerState.dive ? p.y + 10 : p.y;
      final dx = b.x - p.x;
      final dy = b.y - py;
      final d = math.sqrt(dx * dx + dy * dy);
      final minD = Tuning.playerRadius + Tuning.ballRadius;
      if (d >= minD) continue;

      if (phase == Phase.serve) phase = Phase.playing;

      final nx = d > 0 ? dx / d : 0.0;
      final ny = d > 0 ? dy / d : -1.0;
      b.x = p.x + nx * minD;
      b.y = py + ny * minD;
      p.hitCooldown = Tuning.hitCooldown;
      p.hitFlash = 10;

      if (p.spikeTimer > 0 && p.state == PlayerState.air) {
        _spike(p);
      } else {
        // 일반 리시브: 몸에서 튕겨 나간다
        final speed = math.max(
            math.sqrt(b.vx * b.vx + b.vy * b.vy) * 0.85, 10.5);
        // 상대 코트 쪽으로 살짝 밀어 줘서 머리 위에서 무한히 튀지 않게 한다
        b.vx = nx * speed + p.vx * 0.4 + p.forward * 2.2;
        b.vy = ny * speed + p.vy * 0.3;
        if (b.vy > -7) b.vy = -7 - (1 - ny.abs()) * 2; // 항상 위로 띄워 준다
        b.powerTrail = 0;
        events.add(GameEvent.hit);
      }
      _clampBallSpeed();
    }
  }

  void _spike(Player p) {
    final b = ball;
    final input = p.prevInput;
    final f = p.forward;
    final holdForward =
        (f > 0 && input & Input.right != 0) || (f < 0 && input & Input.left != 0);
    final holdBack =
        (f > 0 && input & Input.left != 0) || (f < 0 && input & Input.right != 0);

    if (holdForward) {
      // 직선 강타
      b.vx = 19.0 * f;
      b.vy = 2.5;
    } else if (holdBack) {
      // 페인트(높이 띄워 넘기기)
      b.vx = 7.5 * f;
      b.vy = -11;
    } else {
      // 기본 내리꽂기
      b.vx = 14.5 * f;
      b.vy = 10;
    }
    b.powerTrail = holdBack ? 0 : 40;
    p.spikeTimer = 0;
    events.add(GameEvent.spike);
  }

  void _clampBallSpeed() {
    final b = ball;
    final s = math.sqrt(b.vx * b.vx + b.vy * b.vy);
    if (s > Tuning.ballMaxSpeed) {
      b.vx *= Tuning.ballMaxSpeed / s;
      b.vy *= Tuning.ballMaxSpeed / s;
    }
  }

  // ---------------------------------------------------------------------------
  // 네트워크 동기화: 호스트가 게스트에게 보내는 상태 스냅샷
  // ---------------------------------------------------------------------------

  static const int snapshotSize = 4 + 2 * 2 + 4 + 2 * 28 + 24;

  Uint8List toSnapshot() {
    final bd = ByteData(snapshotSize);
    var o = 0;
    bd.setUint32(o, frame);
    o += 4;
    bd.setUint16(o, scores[0]);
    o += 2;
    bd.setUint16(o, scores[1]);
    o += 2;
    bd.setUint8(o++, phase.index);
    bd.setUint8(o++, server);
    bd.setInt8(o++, lastScorer);
    bd.setUint8(o++, phaseTimer.clamp(0, 255));
    for (final p in players) {
      bd.setFloat32(o, p.x);
      bd.setFloat32(o + 4, p.y);
      bd.setFloat32(o + 8, p.vx);
      bd.setFloat32(o + 12, p.vy);
      bd.setUint8(o + 16, p.state.index);
      bd.setUint8(o + 17, p.spikeTimer);
      bd.setUint8(o + 18, p.diveTimer.clamp(0, 255));
      bd.setInt8(o + 19, p.diveDir);
      bd.setUint8(o + 20, p.hitCooldown);
      bd.setUint8(o + 21, p.prevInput);
      bd.setUint8(o + 22, p.hitFlash);
      o += 28;
    }
    bd.setFloat32(o, ball.x);
    bd.setFloat32(o + 4, ball.y);
    bd.setFloat32(o + 8, ball.vx);
    bd.setFloat32(o + 12, ball.vy);
    bd.setFloat32(o + 16, ball.angle);
    bd.setUint8(o + 20, ball.powerTrail);
    return bd.buffer.asUint8List();
  }

  void applySnapshot(Uint8List data) {
    final bd = ByteData.sublistView(data);
    var o = 0;
    frame = bd.getUint32(o);
    o += 4;
    scores[0] = bd.getUint16(o);
    o += 2;
    scores[1] = bd.getUint16(o);
    o += 2;
    phase = Phase.values[bd.getUint8(o++)];
    server = bd.getUint8(o++);
    lastScorer = bd.getInt8(o++);
    phaseTimer = bd.getUint8(o++);
    for (final p in players) {
      p.x = bd.getFloat32(o);
      p.y = bd.getFloat32(o + 4);
      p.vx = bd.getFloat32(o + 8);
      p.vy = bd.getFloat32(o + 12);
      p.state = PlayerState.values[bd.getUint8(o + 16)];
      p.spikeTimer = bd.getUint8(o + 17);
      p.diveTimer = bd.getUint8(o + 18);
      p.diveDir = bd.getInt8(o + 19);
      p.hitCooldown = bd.getUint8(o + 20);
      p.prevInput = bd.getUint8(o + 21);
      p.hitFlash = bd.getUint8(o + 22);
      o += 28;
    }
    ball.x = bd.getFloat32(o);
    ball.y = bd.getFloat32(o + 4);
    ball.vx = bd.getFloat32(o + 8);
    ball.vy = bd.getFloat32(o + 12);
    ball.angle = bd.getFloat32(o + 16);
    ball.powerTrail = bd.getUint8(o + 20);
  }
}
