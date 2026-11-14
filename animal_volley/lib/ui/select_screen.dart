import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';
import 'package:flutter/material.dart';
import '../game/characters.dart';
import '../game/cpu.dart';
import '../net/session.dart';
import '../settings.dart';
import 'common.dart';
import 'game_screen.dart';

/// 캐릭터 선택. [session]이 없으면 CPU 연습 모드.
class SelectScreen extends StatefulWidget {
  final NetSession? session;

  /// true면 '서브 연습' (상대 없음)
  final bool serveOnly;
  const SelectScreen({super.key, this.session, this.serveOnly = false});

  @override
  State<SelectScreen> createState() => _SelectScreenState();
}

class _SelectScreenState extends State<SelectScreen> {
  CharacterLook my = const CharacterLook(Animal.badger, 0);
  bool ready = false;
  CpuLevel level = CpuLevel.normal;
  StreamSubscription? _msgSub, _statusSub;
  bool _inGame = false;

  NetSession? get net => widget.session;
  bool get online => net != null;
  CharacterLook? get peer => net?.peerLook;

  @override
  void initState() {
    super.initState();
    if (online) {
      // 게스트는 기본값이 겹치지 않게 다른 동물로 시작
      if (!net!.isHost) my = const CharacterLook(Animal.pig, 0);
      _listen();
      net!.sendPick(my, false);
    }
  }

  void _listen() {
    _msgSub = net!.messages.listen(_onMsg);
    _statusSub = net!.statusChanges.listen((s) {
      if (s == LinkStatus.lost) _peerLeft();
    });
  }

  void _unlisten() {
    _msgSub?.cancel();
    _statusSub?.cancel();
    _msgSub = _statusSub = null;
  }

  void _onMsg(Uint8List m) {
    switch (m[0]) {
      case Msg.pick:
        setState(() {
          net!.peerLook = CharacterLook(Animal.values[m[1]], m[2]);
          net!.peerReady = m[3] == 1;
        });
        // 같은 동물·같은 색이 겹치면 게스트가 양보(다른 색으로 자동 변경)
        if (!net!.isHost && peer == my) {
          _choose(_freePalette(my.animal) ?? my);
          return;
        }
        if (net!.isHost) _maybeStart();
        break;
      case Msg.start:
        if (!net!.isHost) {
          // 호스트의 속도 설정을 그대로 따른다
          final ball = m.length > 2 ? m[1] / 100 : 1.0;
          final move = m.length > 2 ? m[2] / 100 : 1.0;
          _startGame(ballSpeed: ball, moveSpeed: move);
        }
        break;
      case Msg.leave:
        _peerLeft();
        break;
    }
  }

  int? _freePaletteIndex(Animal a) {
    for (var i = 0; i < a.palettes.length; i++) {
      if (!_taken(CharacterLook(a, i))) return i;
    }
    return null;
  }

  CharacterLook? _freePalette(Animal a) {
    final i = _freePaletteIndex(a);
    return i == null ? null : CharacterLook(a, i);
  }

  bool _taken(CharacterLook l) => online && peer == l;

  void _choose(CharacterLook l) {
    if (_taken(l)) return;
    setState(() {
      my = l;
      ready = false;
    });
    net?.sendPick(my, false);
  }

  void _toggleReady() {
    if (!online) {
      _startGame();
      return;
    }
    setState(() => ready = !ready);
    net!.sendPick(my, ready);
    if (net!.isHost) _maybeStart();
  }

  void _maybeStart() {
    if (ready && net!.peerReady && peer != null && peer != my) {
      final s = GameSettings.instance;
      net!.send([
        Msg.start,
        (s.ballSpeed * 100).round().clamp(1, 255),
        (s.moveSpeed * 100).round().clamp(1, 255),
      ]);
      _startGame();
    }
  }

  Future<void> _startGame({double? ballSpeed, double? moveSpeed}) async {
    if (_inGame) return;
    _inGame = true;
    _unlisten();

    late final List<CharacterLook> looks;
    if (online) {
      looks = net!.isHost ? [my, peer!] : [peer!, my];
    } else {
      // CPU는 내 캐릭터와 겹치지 않게 무작위
      final rng = math.Random();
      CharacterLook cpu;
      do {
        cpu = CharacterLook(Animal.values[rng.nextInt(4)], rng.nextInt(4));
      } while (cpu == my);
      looks = [my, cpu];
    }

    final result = await Navigator.push<GameExit>(
      context,
      MaterialPageRoute(
        builder: (_) => GameScreen(
          looks: looks,
          session: net,
          cpuLevel: level,
          solo: widget.serveOnly,
          ballSpeed: ballSpeed ?? GameSettings.instance.ballSpeed,
          moveSpeed: moveSpeed ?? GameSettings.instance.moveSpeed,
        ),
      ),
    );
    _inGame = false;
    if (!mounted) return;

    if (result == GameExit.select) {
      setState(() => ready = false);
      if (online) {
        net!.peerReady = false;
        _listen();
        net!.sendPick(my, false);
      }
    } else {
      // 나가기 / 연결 끊김
      if (online) await net!.close();
      if (mounted) Navigator.pop(context);
    }
  }

  bool _leftShown = false;
  Future<void> _peerLeft() async {
    if (_leftShown || !mounted) return;
    _leftShown = true;
    _unlisten();
    await showInfo(context, '연결 끊김', '상대방과 연결이 끊어졌어요.');
    await net?.close();
    if (mounted) Navigator.pop(context);
  }

  @override
  void dispose() {
    _unlisten();
    if (online && !_inGame) net!.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kCream,
      body: SafeArea(
        child: LayoutBuilder(builder: (context, box) {
          final wide = box.maxWidth > box.maxHeight;
          final picker = _picker();
          final preview = _preview();
          return Stack(children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
              child: wide
                  ? Row(children: [
                      Expanded(flex: 5, child: picker),
                      const SizedBox(width: 12),
                      Expanded(flex: 4, child: preview),
                    ])
                  : Column(children: [
                      Expanded(child: picker),
                      SizedBox(height: 260, child: preview),
                    ]),
            ),
            Positioned(
              left: 0,
              top: 0,
              child: IconButton(
                icon: const Icon(Icons.arrow_back, color: kInk),
                onPressed: () => Navigator.pop(context),
              ),
            ),
          ]);
        }),
      ),
    );
  }

  Widget _picker() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 4),
        const Center(
          child: Text('캐릭터 선택',
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900, color: kInk)),
        ),
        const SizedBox(height: 6),
        Expanded(
          child: Row(
            children: [
              for (final a in Animal.values)
                Expanded(
                  child: _animalCard(a),
                ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text('색  ', style: TextStyle(fontWeight: FontWeight.w700, color: kInk)),
            for (var i = 0; i < my.animal.palettes.length; i++) _swatch(i),
          ],
        ),
        const SizedBox(height: 4),
      ],
    );
  }

  Widget _animalCard(Animal a) {
    final selected = my.animal == a;
    final idx = selected
        ? my.paletteIndex
        : (_taken(CharacterLook(a, 0)) ? (_freePaletteIndex(a) ?? 0) : 0);
    return GestureDetector(
      onTap: () {
        if (my.animal == a) return;
        final free = _freePalette(a);
        if (free != null) _choose(free);
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        margin: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: selected ? Colors.white : Colors.white.withValues(alpha: 0.5),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
              color: selected ? kOrange : Colors.transparent, width: 3),
        ),
        child: LayoutBuilder(builder: (context, box) {
          final s = math.min(box.maxWidth, box.maxHeight - 26) * 0.95;
          return Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              CharacterView(CharacterLook(a, idx),
                  pose: selected ? Pose.win : Pose.idle, size: math.max(s, 20)),
              Text(a.displayName,
                  style: TextStyle(
                      fontWeight: selected ? FontWeight.w900 : FontWeight.w600,
                      color: kInk,
                      fontSize: 14)),
            ],
          );
        }),
      ),
    );
  }

  Widget _swatch(int i) {
    final l = CharacterLook(my.animal, i);
    final pal = my.animal.palettes[i];
    final selected = my.paletteIndex == i;
    final taken = _taken(l);
    return GestureDetector(
      onTap: taken ? null : () => _choose(l),
      child: Tooltip(
        message: taken ? '${pal.name} (상대가 사용 중)' : pal.name,
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 6),
          width: 38,
          height: 38,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: LinearGradient(colors: [pal.base, pal.accent]),
            border: Border.all(color: selected ? kOrange : Colors.white, width: selected ? 4 : 2),
          ),
          child: taken
              ? const Icon(Icons.block, color: Colors.white, size: 22)
              : null,
        ),
      ),
    );
  }

  Widget _preview() {
    final opp = online
        ? peer
        : null;
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFFBDE8FF),
        borderRadius: BorderRadius.circular(20),
      ),
      padding: const EdgeInsets.all(10),
      child: Column(
        children: [
          Expanded(
            child: Row(
              children: [
                Expanded(child: _side('나', my, ready || !online)),
                const Text('VS',
                    style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900, color: kOrange)),
                Expanded(
                  child: online
                      ? (opp == null
                          ? const Center(child: Text('상대 선택 중...'))
                          : _side(net!.peerName ?? '상대', opp, net!.peerReady,
                              facing: -1))
                      : widget.serveOnly
                          ? _serveSide()
                          : _cpuSide(),
                ),
              ],
            ),
          ),
          const SizedBox(height: 6),
          online
              ? BigButton(ready ? '준비 취소' : '준비 완료',
                  sub: ready
                      ? (net!.peerReady ? '곧 시작해요!' : '상대를 기다리는 중...')
                      : '둘 다 준비하면 시작',
                  icon: ready ? Icons.close : Icons.check,
                  color: ready ? const Color(0xFF8A7FB0) : kOrange,
                  onTap: _toggleReady)
              : BigButton('시작!', icon: Icons.play_arrow, onTap: _toggleReady),
        ],
      ),
    );
  }

  Widget _side(String label, CharacterLook look, bool isReady, {int facing = 1}) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text(label, style: const TextStyle(fontWeight: FontWeight.w800, color: kInk)),
        Flexible(
          child: LayoutBuilder(builder: (context, box) {
            final s = math.max(20.0, math.min(box.maxWidth, box.maxHeight));
            return CharacterView(look, size: s, facing: facing,
                pose: isReady ? Pose.win : Pose.idle);
          }),
        ),
        Text('${look.animal.displayName} · ${look.palette.name}',
            style: const TextStyle(fontSize: 12, color: kInk)),
        if (online)
          Text(isReady ? '준비 완료' : '고르는 중',
              style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: isReady ? Colors.green[700] : Colors.black45)),
      ],
    );
  }

  Widget _serveSide() {
    return const Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(Icons.sports_volleyball, size: 44, color: kInk),
        Text('서브 연습',
            style: TextStyle(fontWeight: FontWeight.w800, color: kInk)),
        SizedBox(height: 4),
        Text('상대 없이 공이 계속\n내 머리 위로 올라와요.\n네트 너머로 넘기면 성공!',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 12, color: kInk)),
      ],
    );
  }

  Widget _cpuSide() {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const Icon(Icons.smart_toy_outlined, size: 44, color: kInk),
        const Text('CPU', style: TextStyle(fontWeight: FontWeight.w800, color: kInk)),
        const Text('(랜덤 동물)', style: TextStyle(fontSize: 12, color: kInk)),
        const SizedBox(height: 8),
        Wrap(
          spacing: 4,
          runSpacing: 4,
          alignment: WrapAlignment.center,
          children: [
            for (final l in CpuLevel.values)
              ChoiceChip(
                label: Text(l.label),
                selected: level == l,
                onSelected: (_) => setState(() => level = l),
                visualDensity: VisualDensity.compact,
              ),
          ],
        ),
      ],
    );
  }
}
