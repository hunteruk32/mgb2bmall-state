import 'package:flutter/material.dart';
import '../audio.dart';
import '../settings.dart';
import 'common.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final s = GameSettings.instance;
    return Scaffold(
      backgroundColor: kCream,
      appBar: AppBar(
        title: const Text('환경설정', style: TextStyle(fontWeight: FontWeight.w800)),
        backgroundColor: kCream,
        foregroundColor: kInk,
        elevation: 0,
      ),
      body: ListenableBuilder(
        listenable: s,
        builder: (context, _) => ListView(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
          children: [
            _section('속도'),
            _speedRow(
              icon: Icons.sports_volleyball,
              title: '공 속도',
              value: s.ballSpeed,
              onChanged: (v) => s.update(ball: v),
            ),
            _speedRow(
              icon: Icons.directions_run,
              title: '캐릭터 이동 속도',
              value: s.moveSpeed,
              onChanged: (v) => s.update(move: v),
            ),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: s.resetSpeeds,
                icon: const Icon(Icons.restart_alt),
                label: const Text('기본값으로'),
              ),
            ),
            const Text(
              '블루투스 대전에서는 방을 만든 사람(호스트)의 속도 설정이 두 사람 모두에게 적용돼요.',
              style: TextStyle(fontSize: 12, color: Colors.black54),
            ),
            const SizedBox(height: 12),
            _section('조작'),
            Row(
              children: [
                const Icon(Icons.gamepad, color: kInk),
                const SizedBox(width: 10),
                const SizedBox(
                  width: 120,
                  child: Text('조이스틱 감도',
                      style: TextStyle(fontWeight: FontWeight.w700, color: kInk)),
                ),
                Expanded(
                  child: Slider(
                    value: s.stickSensitivity,
                    divisions: 10,
                    onChanged: (v) => s.update(stick: v),
                  ),
                ),
                SizedBox(
                  width: 110,
                  child: Text(
                    s.stickSensitivity < 0.35
                        ? '둔하게'
                        : s.stickSensitivity < 0.75
                            ? '보통'
                            : '민감하게',
                    textAlign: TextAlign.right,
                    style: const TextStyle(color: kInk),
                  ),
                ),
              ],
            ),
            const Text(
              '민감할수록 엄지를 조금만 움직여도 이동·점프해요.',
              style: TextStyle(fontSize: 12, color: Colors.black54),
            ),
            const SizedBox(height: 12),
            _section('소리'),
            _volumeRow(
              icon: Icons.music_note,
              title: '배경음악',
              value: s.bgmVolume,
              onChanged: (v) => s.update(bgm: v),
            ),
            _volumeRow(
              icon: Icons.volume_up,
              title: '효과음',
              value: s.sfxVolume,
              onChanged: (v) => s.update(sfx: v),
              onChangeEnd: (_) => GameAudio.instance.play(Sfx.hit),
            ),
          ],
        ),
      ),
    );
  }

  Widget _section(String t) => Padding(
        padding: const EdgeInsets.only(top: 8, bottom: 4),
        child: Text(t,
            style: const TextStyle(
                fontSize: 15, fontWeight: FontWeight.w800, color: kOrange)),
      );

  Widget _speedRow({
    required IconData icon,
    required String title,
    required double value,
    required ValueChanged<double> onChanged,
  }) {
    return Row(
      children: [
        Icon(icon, color: kInk),
        const SizedBox(width: 10),
        SizedBox(
          width: 120,
          child: Text(title,
              style: const TextStyle(fontWeight: FontWeight.w700, color: kInk)),
        ),
        Expanded(
          child: Slider(
            value: value,
            min: GameSettings.minSpeed,
            max: GameSettings.maxSpeed,
            divisions: 10,
            label: '×${value.toStringAsFixed(1)}',
            onChanged: onChanged,
          ),
        ),
        SizedBox(
          width: 110,
          child: Text(
            '${GameSettings.speedLabel(value)} ×${value.toStringAsFixed(1)}',
            textAlign: TextAlign.right,
            style: const TextStyle(color: kInk),
          ),
        ),
      ],
    );
  }

  Widget _volumeRow({
    required IconData icon,
    required String title,
    required double value,
    required ValueChanged<double> onChanged,
    ValueChanged<double>? onChangeEnd,
  }) {
    return Row(
      children: [
        Icon(value == 0 ? Icons.volume_off : icon, color: kInk),
        const SizedBox(width: 10),
        SizedBox(
          width: 120,
          child: Text(title,
              style: const TextStyle(fontWeight: FontWeight.w700, color: kInk)),
        ),
        Expanded(
          child: Slider(
            value: value,
            divisions: 10,
            label: '${(value * 100).round()}%',
            onChanged: onChanged,
            onChangeEnd: onChangeEnd,
          ),
        ),
        SizedBox(
          width: 110,
          child: Text(value == 0 ? '끔' : '${(value * 100).round()}%',
              textAlign: TextAlign.right, style: const TextStyle(color: kInk)),
        ),
      ],
    );
  }
}
