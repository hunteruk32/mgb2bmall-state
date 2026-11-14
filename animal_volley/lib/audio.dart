// 효과음 / 배경음악 재생
//
// 소리 파일은 tools/make_audio.py로 직접 합성해 assets/audio/에 넣어 둔 것이다.
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'settings.dart';

enum Sfx {
  hit,
  spike,
  net,
  wall,
  ground,
  jump,
  dive,
  whistle,
  pointWin,
  pointLose,
  gameWin,
  gameLose,
  click,
}

enum Bgm { menu, game }

class GameAudio {
  GameAudio._();
  static final GameAudio instance = GameAudio._();

  static const _files = {
    Sfx.hit: 'hit',
    Sfx.spike: 'spike',
    Sfx.net: 'net',
    Sfx.wall: 'wall',
    Sfx.ground: 'ground',
    Sfx.jump: 'jump',
    Sfx.dive: 'dive',
    Sfx.whistle: 'whistle',
    Sfx.pointWin: 'point_win',
    Sfx.pointLose: 'point_lose',
    Sfx.gameWin: 'game_win',
    Sfx.gameLose: 'game_lose',
    Sfx.click: 'click',
  };

  /// 효과음별 기본 음량(서로 균형 맞추기)
  static const _gain = {
    Sfx.jump: 0.5,
    Sfx.wall: 0.6,
    Sfx.dive: 0.7,
    Sfx.click: 0.6,
  };

  final _pools = <Sfx, AudioPool>{};
  final _lastPlayed = <Sfx, int>{};
  AudioPlayer? _bgmPlayer;
  Bgm? _current;
  bool _paused = false;
  bool _ready = false;

  final _settings = GameSettings.instance;

  Future<void> init() async {
    if (_ready) return;
    _ready = true;
    _settings.addListener(_onSettings);
    try {
      _bgmPlayer = AudioPlayer(playerId: 'bgm');
      await _bgmPlayer!.setReleaseMode(ReleaseMode.loop);
    } catch (e) {
      debugPrint('bgm init failed: $e');
    }
    for (final e in _files.entries) {
      try {
        _pools[e.key] = await AudioPool.createFromAsset(
          path: 'audio/${e.value}.ogg',
          maxPlayers: e.key == Sfx.hit || e.key == Sfx.ground ? 3 : 2,
        );
      } catch (err) {
        debugPrint('sfx ${e.value} load failed: $err');
      }
    }
  }

  void _onSettings() {
    _bgmPlayer?.setVolume(_settings.bgmVolume * 0.7);
  }

  void play(Sfx s, {double volume = 1.0}) {
    final v = _settings.sfxVolume * volume * (_gain[s] ?? 1.0);
    if (v <= 0.01) return;
    // 같은 소리가 너무 촘촘히 겹치지 않게
    final now = DateTime.now().millisecondsSinceEpoch;
    if (now - (_lastPlayed[s] ?? 0) < 60) return;
    _lastPlayed[s] = now;
    final pool = _pools[s];
    if (pool == null) return;
    pool.start(volume: v.clamp(0.0, 1.0)).catchError((Object e) {
      debugPrint('sfx play failed: $e');
      return () async {};
    });
  }

  Future<void> playBgm(Bgm b) async {
    final p = _bgmPlayer;
    if (p == null) return;
    if (_current == b && !_paused) return;
    _current = b;
    try {
      await p.stop();
      await p.setVolume(_settings.bgmVolume * 0.7);
      if (!_paused) {
        await p.play(AssetSource('audio/bgm_${b.name}.ogg'));
      }
    } catch (e) {
      debugPrint('bgm play failed: $e');
    }
  }

  /// 앱이 백그라운드로 가면 음악을 멈춘다
  Future<void> setPaused(bool paused) async {
    if (_paused == paused) return;
    _paused = paused;
    final p = _bgmPlayer;
    if (p == null) return;
    try {
      if (paused) {
        await p.pause();
      } else if (_current != null) {
        if (p.state == PlayerState.paused) {
          await p.resume();
        } else {
          await p.play(AssetSource('audio/bgm_${_current!.name}.ogg'));
        }
      }
    } catch (_) {}
  }
}
