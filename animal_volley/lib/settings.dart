// 환경설정 (기기에 저장됨)
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class GameSettings extends ChangeNotifier {
  GameSettings._();
  static final GameSettings instance = GameSettings._();

  static const double minSpeed = 0.6, maxSpeed = 1.6;

  /// 공 속도 배율 (1.0 = 기본)
  double ballSpeed = 1.0;

  /// 캐릭터 이동 속도 배율 (1.0 = 기본)
  double moveSpeed = 1.0;

  /// 0.0 ~ 1.0
  double bgmVolume = 0.6;
  double sfxVolume = 0.9;

  SharedPreferences? _prefs;

  Future<void> load() async {
    try {
      final p = _prefs = await SharedPreferences.getInstance();
      ballSpeed = p.getDouble('ballSpeed') ?? ballSpeed;
      moveSpeed = p.getDouble('moveSpeed') ?? moveSpeed;
      bgmVolume = p.getDouble('bgmVolume') ?? bgmVolume;
      sfxVolume = p.getDouble('sfxVolume') ?? sfxVolume;
    } catch (_) {
      // 저장소를 못 쓰는 환경이면 기본값으로 진행
    }
    notifyListeners();
  }

  void update({double? ball, double? move, double? bgm, double? sfx}) {
    if (ball != null) ballSpeed = ball;
    if (move != null) moveSpeed = move;
    if (bgm != null) bgmVolume = bgm;
    if (sfx != null) sfxVolume = sfx;
    notifyListeners();
    final p = _prefs;
    if (p != null) {
      p.setDouble('ballSpeed', ballSpeed);
      p.setDouble('moveSpeed', moveSpeed);
      p.setDouble('bgmVolume', bgmVolume);
      p.setDouble('sfxVolume', sfxVolume);
    }
  }

  void resetSpeeds() => update(ball: 1.0, move: 1.0);

  /// 배율을 사람이 읽기 쉬운 말로
  static String speedLabel(double v) {
    if (v < 0.75) return '아주 느림';
    if (v < 0.95) return '느림';
    if (v <= 1.05) return '보통';
    if (v <= 1.3) return '빠름';
    return '아주 빠름';
  }
}
