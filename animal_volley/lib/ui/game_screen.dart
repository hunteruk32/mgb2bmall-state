import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import '../audio.dart';
import '../game/characters.dart';
import '../game/court_painter.dart';
import '../game/cpu.dart';
import '../game/world.dart';
import '../net/session.dart';
import 'common.dart';
import 'touch_controls.dart';

enum GameExit { select, leave }

/// 경기 화면. [session]이 없으면 CPU 연습.
class GameScreen extends StatefulWidget {
  final List<CharacterLook> looks;
  final NetSession? session;
  final CpuLevel cpuLevel;

  /// 서브 연습 모드
  final bool solo;
  final double ballSpeed;
  final double moveSpeed;
  const GameScreen(
      {super.key,
      required this.looks,
      this.session,
      this.cpuLevel = CpuLevel.normal,
      this.solo = false,
      this.ballSpeed = 1.0,
      this.moveSpeed = 1.0});

  @override
  State<GameScreen> createState() => _GameScreenState();
}

class _GameScreenState extends State<GameScreen>
    with SingleTickerProviderStateMixin {
  static const _dt = 1 / 60;

  late final World world;
  late final Ticker _ticker;
  final _frame = ValueNotifier<int>(0);
  final _controls = TouchControlsController();
  CpuBrain? cpu;

  Duration _last = Duration.zero;
  late List<int> _lastScores;
  int _lastTries = 0;
  Phase _lastPhase = Phase.serve;
  double _acc = 0;
  double _time = 0;
  bool paused = false;

  // 네트워크
  StreamSubscription? _msgSub, _statusSub;
  int _remoteInput = 0; // 호스트: 게스트가 보낸 입력
  int _lastSentInput = -1; // 게스트: 마지막으로 보낸 입력
  Uint8List? _pendingSnapshot; // 게스트: 아직 적용 안 한 최신 상태
  bool _exiting = false;

  NetSession? get net => widget.session;
  bool get online => net != null;
  bool get isHost => !online || net!.isHost;

  /// 내가 조종하는 쪽 (호스트/연습 = 왼쪽, 게스트 = 오른쪽)
  int get mySide => isHost ? 0 : 1;

  @override
  void initState() {
    super.initState();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    world = World(
      authoritative: isHost,
      solo: widget.solo,
      ballSpeed: widget.ballSpeed,
      moveSpeed: widget.moveSpeed,
    );
    if (!online && !widget.solo) cpu = CpuBrain(1, level: widget.cpuLevel);
    _lastScores = List.of(world.scores);
    GameAudio.instance.playBgm(Bgm.game);
    GameAudio.instance.play(Sfx.whistle);
    if (online) {
      _msgSub = net!.messages.listen(_onMsg);
      _statusSub = net!.statusChanges.listen((s) {
        if (s == LinkStatus.lost) _disconnected();
      });
    }
    _ticker = createTicker(_tick)..start();
  }

  @override
  void dispose() {
    GameAudio.instance.playBgm(Bgm.menu);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    _ticker.dispose();
    _msgSub?.cancel();
    _statusSub?.cancel();
    _frame.dispose();
    super.dispose();
  }

  // ---------------------------------------------------------------------------

  int _readLocalInput() {
    int bits = _controls.bits;
    // 키보드(테스트/태블릿 키보드용): ← → 이동, ↑ 점프, 스페이스/Z 스파이크
    final keys = HardwareKeyboard.instance.logicalKeysPressed;
    if (keys.contains(LogicalKeyboardKey.arrowLeft)) bits |= Input.left;
    if (keys.contains(LogicalKeyboardKey.arrowRight)) bits |= Input.right;
    if (keys.contains(LogicalKeyboardKey.arrowUp)) bits |= Input.jump;
    if (keys.contains(LogicalKeyboardKey.space) ||
        keys.contains(LogicalKeyboardKey.keyZ)) {
      bits |= Input.hit;
    }
    return bits;
  }

  void _tick(Duration now) {
    var dt = (now - _last).inMicroseconds / 1e6;
    _last = now;
    if (dt > 0.1) dt = 0.1; // 앱이 잠깐 멈췄다 돌아온 경우
    if (paused && !online) return;
    _time += dt;
    _acc += dt;

    final mine = _readLocalInput();

    if (online && !isHost) {
      // 게스트: 입력이 바뀔 때만 전송
      if (mine != _lastSentInput) {
        net!.send([Msg.input, mine]);
        _lastSentInput = mine;
      }
      final snap = _pendingSnapshot;
      if (snap != null) {
        world.applySnapshot(snap);
        _pendingSnapshot = null;
      }
    }

    var steps = 0;
    while (_acc >= _dt && steps < 5) {
      _acc -= _dt;
      steps++;
      final inputs = [0, 0];
      inputs[mySide] = mine;
      if (!online) {
        inputs[1] = cpu?.think(world) ?? 0;
      } else if (isHost) {
        inputs[1] = _remoteInput;
      } else {
        // 게스트 쪽 예측: 호스트 입력은 마지막으로 받은 값을 유지
        inputs[0] = world.players[0].prevInput;
      }
      final before = world.phase;
      world.step(inputs);
      _sounds();
      if (before != Phase.gameOver && world.phase == Phase.gameOver) {
        setState(() {});
      }

      // 호스트: 2프레임(약 30Hz)마다 상태 전송
      if (online && isHost && world.frame.isEven) {
        final snap = world.toSnapshot();
        final msg = Uint8List(snap.length + 1)
          ..[0] = Msg.state
          ..setRange(1, snap.length + 1, snap);
        net!.send(msg);
      }
    }
    if (_acc > _dt * 5) _acc = 0;
    if (online && !isHost) _scoreSounds(); // 게스트는 스냅샷으로 점수가 바뀐다
    _frame.value++;
  }

  /// 물리 이벤트 → 효과음
  void _sounds() {
    final a = GameAudio.instance;
    for (final e in world.events) {
      switch (e) {
        case GameEvent.hit:
          a.play(Sfx.hit);
        case GameEvent.spike:
          a.play(Sfx.spike);
          HapticFeedback.lightImpact();
        case GameEvent.net:
          a.play(Sfx.net);
        case GameEvent.wall:
          a.play(Sfx.wall);
        case GameEvent.ground:
          a.play(Sfx.ground);
        case GameEvent.jump:
          a.play(Sfx.jump);
        case GameEvent.dive:
          a.play(Sfx.dive);
        default:
          break;
      }
    }
    if (isHost) _scoreSounds();
  }

  /// 점수 / 서브 / 경기 종료 → 효과음 (호스트·게스트 모두 상태 변화로 판단)
  void _scoreSounds() {
    final a = GameAudio.instance;
    final w = world;
    if (w.solo) {
      if (w.practiceTries != _lastTries) {
        _lastTries = w.practiceTries;
        a.play(w.lastPracticeSuccess ? Sfx.pointWin : Sfx.pointLose);
      }
    } else if (w.scores[0] != _lastScores[0] || w.scores[1] != _lastScores[1]) {
      final mineUp = w.scores[mySide] > _lastScores[mySide];
      _lastScores = List.of(w.scores);
      if (w.scores[0] + w.scores[1] > 0) {
        a.play(mineUp ? Sfx.pointWin : Sfx.pointLose);
      }
    }
    if (w.phase != _lastPhase) {
      if (w.phase == Phase.gameOver) {
        a.play(w.winner == mySide ? Sfx.gameWin : Sfx.gameLose);
      } else if (w.phase == Phase.serve && _lastPhase == Phase.point && !w.solo) {
        a.play(Sfx.whistle, volume: 0.6);
      }
      _lastPhase = w.phase;
    }
  }

  void _onMsg(Uint8List m) {
    switch (m[0]) {
      case Msg.input:
        if (isHost && m.length > 1) _remoteInput = m[1];
        break;
      case Msg.state:
        if (!isHost) {
          final wasOver = world.phase == Phase.gameOver;
          _pendingSnapshot = Uint8List.sublistView(m, 1);
          // 게임 종료 표시가 바뀌면 화면 갱신
          final p = Phase.values[m[1 + 4 + 4]];
          if ((p == Phase.gameOver) != wasOver) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (mounted) setState(() {});
            });
          }
        }
        break;
      case Msg.rematch:
        if (isHost) _rematch();
        break;
      case Msg.toSelect:
        _exit(GameExit.select, notify: false);
        break;
      case Msg.leave:
        _disconnected();
        break;
    }
  }

  void _rematch() {
    if (online && !isHost) {
      net!.send([Msg.rematch]);
      return;
    }
    setState(() {
      world.restart();
      _lastScores = List.of(world.scores);
      _lastTries = 0;
      paused = false;
    });
    GameAudio.instance.play(Sfx.whistle);
  }

  void _exit(GameExit e, {bool notify = true}) {
    if (_exiting) return;
    _exiting = true;
    if (online && notify && e == GameExit.select) net!.send([Msg.toSelect]);
    Navigator.pop(context, e);
  }

  Future<void> _disconnected() async {
    if (_exiting) return;
    _exiting = true;
    _ticker.stop();
    await showInfo(context, '연결 끊김', '상대방과 연결이 끊어졌어요.');
    if (mounted) Navigator.pop(context, GameExit.leave);
  }

  Future<void> _menu() async {
    if (!online) setState(() => paused = true);
    final r = await showDialog<String>(
      context: context,
      builder: (c) => SimpleDialog(
        title: Text(online ? '메뉴' : '일시정지'),
        children: [
          SimpleDialogOption(
              onPressed: () => Navigator.pop(c, 'resume'),
              child: const Text('계속하기')),
          if (widget.solo)
            SimpleDialogOption(
                onPressed: () => Navigator.pop(c, 'reset'),
                child: const Text('기록 초기화')),
          SimpleDialogOption(
              onPressed: () => Navigator.pop(c, 'select'),
              child: const Text('캐릭터 다시 고르기')),
          SimpleDialogOption(
              onPressed: () => Navigator.pop(c, 'leave'),
              child: const Text('나가기', style: TextStyle(color: Colors.red))),
        ],
      ),
    );
    if (!mounted) return;
    if (r == 'reset') {
      _rematch();
    } else if (r == 'select') {
      _exit(GameExit.select);
    } else if (r == 'leave') {
      _exit(GameExit.leave);
    } else {
      setState(() => paused = false);
    }
  }

  // ---------------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _menu();
      },
      child: Scaffold(
        backgroundColor: const Color(0xFF8FD3F4),
        body: Stack(
          children: [
            Positioned.fill(
              child: CustomPaint(
                painter: _LiveCourtPainter(this),
              ),
            ),
            Positioned.fill(child: _Hud(state: this)),
            Positioned.fill(
                child: TouchControls(controller: _controls, repaint: _frame)),
            Positioned(
              top: 6,
              right: 6,
              child: SafeArea(
                child: IconButton.filledTonal(
                  icon: const Icon(Icons.pause),
                  onPressed: _menu,
                ),
              ),
            ),
            if (world.phase == Phase.gameOver) _gameOver(),
          ],
        ),
      ),
    );
  }

  Widget _gameOver() {
    final iWon = world.winner == mySide;
    return Container(
      color: Colors.black.withValues(alpha: 0.35),
      alignment: Alignment.center,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: kCream,
          borderRadius: BorderRadius.circular(24),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(iWon ? '승리! 🎉' : '아쉬워요...',
                style: const TextStyle(
                    fontSize: 34, fontWeight: FontWeight.w900, color: kInk)),
            Text('${world.scores[0]} : ${world.scores[1]}',
                style: const TextStyle(fontSize: 22, color: kInk)),
            const SizedBox(height: 14),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              alignment: WrapAlignment.center,
              children: [
                BigButton('다시 하기', icon: Icons.replay, onTap: _rematch),
                BigButton('캐릭터 변경',
                    icon: Icons.pets,
                    color: kBlue,
                    onTap: () => _exit(GameExit.select)),
                BigButton('나가기',
                    icon: Icons.logout,
                    color: const Color(0xFF8A7FB0),
                    onTap: () => _exit(GameExit.leave)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _LiveCourtPainter extends CustomPainter {
  final _GameScreenState s;
  _LiveCourtPainter(this.s) : super(repaint: s._frame);

  @override
  void paint(Canvas canvas, Size size) {
    CourtPainter(
      world: s.world,
      looks: s.widget.looks,
      time: s._time,
      repaintOn: s._frame,
    ).paint(canvas, size);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => true;
}

/// 점수판과 안내 문구
class _Hud extends StatelessWidget {
  final _GameScreenState state;
  const _Hud({required this.state});

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: ValueListenableBuilder(
        valueListenable: state._frame,
        builder: (context, _, _) {
          final w = state.world;
          String? banner;
          if (w.solo) {
            if (w.phase == Phase.serve && w.practiceTries == 0) {
              banner = '공을 네트 너머로!';
            } else if (w.phase == Phase.point) {
              banner = w.lastPracticeSuccess ? '성공!' : '실패...';
            }
          } else if (w.phase == Phase.serve && w.frame < 150 && w.scores[0] + w.scores[1] == 0) {
            banner = '${w.winScore}점 선취!';
          } else if (w.phase == Phase.point) {
            banner = w.lastScorer == state.mySide ? '득점!' : '실점...';
          }
          return SafeArea(
            child: Column(
              children: [
                const SizedBox(height: 6),
                if (w.solo)
                  _practiceBoard(w)
                else
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      _score(w.scores[0], state.widget.looks[0], state.mySide == 0),
                      const SizedBox(width: 24),
                      _score(w.scores[1], state.widget.looks[1], state.mySide == 1),
                    ],
                  ),
                const Spacer(),
                if (banner != null)
                  Text(banner,
                      style: const TextStyle(
                          fontSize: 44,
                          fontWeight: FontWeight.w900,
                          color: Colors.white,
                          shadows: [Shadow(color: kInk, offset: Offset(3, 3))])),
                const Spacer(flex: 2),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _practiceBoard(World w) {
    final rate = w.practiceTries == 0
        ? '-'
        : '${(w.practiceSuccess * 100 / w.practiceTries).round()}%';
    Widget cell(String label, String value) => Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text(label, style: const TextStyle(fontSize: 11, color: kInk)),
            Text(value,
                style: const TextStyle(
                    fontSize: 22, fontWeight: FontWeight.w900, color: kInk)),
          ]),
        );
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.8),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        cell('성공', '${w.practiceSuccess}/${w.practiceTries}'),
        cell('성공률', rate),
        cell('연속', '${w.streak}'),
        cell('최고 연속', '${w.bestStreak}'),
      ]),
    );
  }

  Widget _score(int v, CharacterLook look, bool me) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.8),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: look.palette.base, width: 3),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Text(me ? '나 ' : '상대 ',
            style: const TextStyle(fontSize: 14, color: kInk, fontWeight: FontWeight.w700)),
        Text('$v',
            style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w900, color: kInk)),
      ]),
    );
  }
}
