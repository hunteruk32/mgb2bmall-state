import 'package:flutter/material.dart';
import '../game/characters.dart';
import 'common.dart';
import 'lobby_screen.dart';
import 'select_screen.dart';

class TitleScreen extends StatelessWidget {
  const TitleScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF8FD3F4),
      body: Stack(
        children: [
          Positioned.fill(
            top: null,
            child: Container(height: 110, color: const Color(0xFFF6D99B)),
          ),
          SafeArea(
            child: Center(
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text('동물 배구',
                        style: TextStyle(
                            fontSize: 52,
                            fontWeight: FontWeight.w900,
                            color: Colors.white,
                            shadows: [
                              Shadow(color: kInk, offset: Offset(3, 3)),
                            ])),
                    const SizedBox(height: 4),
                    const Text('블루투스 1:1 비치발리볼',
                        style: TextStyle(
                            fontSize: 16,
                            color: kInk,
                            fontWeight: FontWeight.w600)),
                    const SizedBox(height: 10),
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        for (final (i, a) in Animal.values.indexed)
                          CharacterView(CharacterLook(a, 0),
                              pose: Pose.win, size: 84, facing: i < 2 ? 1 : -1),
                      ],
                    ),
                    const SizedBox(height: 16),
                    Wrap(
                      spacing: 14,
                      runSpacing: 10,
                      alignment: WrapAlignment.center,
                      children: [
                        BigButton('블루투스 대전',
                            sub: '친구 폰과 1:1',
                            icon: Icons.bluetooth,
                            color: kBlue,
                            onTap: () => Navigator.push(
                                context,
                                MaterialPageRoute(
                                    builder: (_) => const LobbyScreen()))),
                        BigButton('CPU와 연습',
                            sub: '혼자 하기',
                            icon: Icons.smart_toy_outlined,
                            onTap: () => Navigator.push(
                                context,
                                MaterialPageRoute(
                                    builder: (_) => const SelectScreen()))),
                        BigButton('조작법',
                            icon: Icons.help_outline,
                            color: const Color(0xFF8A7FB0),
                            onTap: () => showInfo(context, '조작법', _howTo)),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

const _howTo = '''◀ ▶  좌우 이동
점프  점프
스파이크
 · 점프 중에 누르면 스파이크
 · 앞으로 누른 채 → 빠른 직선 공격
 · 아무 방향도 안 누름 → 내리꽂기
 · 뒤로 누른 채 → 높이 띄우는 페인트
 · 땅에서 방향과 함께 누르면 다이빙

먼저 15점을 내면 승리!''';
