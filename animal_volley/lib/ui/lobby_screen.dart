import 'dart:async';
import 'package:flutter/material.dart';
import '../net/session.dart';
import 'common.dart';
import 'select_screen.dart';

/// 블루투스 방 만들기 / 찾기
class LobbyScreen extends StatefulWidget {
  const LobbyScreen({super.key});
  @override
  State<LobbyScreen> createState() => _LobbyScreenState();
}

class _LobbyScreenState extends State<LobbyScreen> {
  final session = NetSession();
  StreamSubscription? _statusSub, _roomsSub;
  List<FoundRoom> rooms = [];
  bool _movedOn = false;
  String? error;

  @override
  void initState() {
    super.initState();
    _statusSub = session.statusChanges.listen((s) {
      if (!mounted) return;
      setState(() {});
      if (s == LinkStatus.connected && !_movedOn) {
        _movedOn = true;
        Navigator.pushReplacement(
            context,
            MaterialPageRoute(
                builder: (_) => SelectScreen(session: session)));
      }
    });
    _roomsSub = session.rooms.listen((r) {
      if (mounted) setState(() => rooms = r);
    });
  }

  @override
  void dispose() {
    _statusSub?.cancel();
    _roomsSub?.cancel();
    if (!_movedOn) session.close();
    super.dispose();
  }

  Future<bool> _perm() async {
    try {
      final ok = await NetSession.requestPermissions();
      if (!ok && mounted) {
        setState(() => error = '블루투스/근처 기기 권한이 필요해요. 설정에서 허용해 주세요.');
      }
      return ok;
    } catch (e) {
      setState(() => error = '이 기기에서는 블루투스 대전을 쓸 수 없어요.\n($e)');
      return false;
    }
  }

  Future<void> _host() async {
    setState(() => error = null);
    if (!await _perm()) return;
    try {
      final ok = await session.host();
      if (!ok) setState(() => error = '방을 만들지 못했어요. 블루투스가 켜져 있는지 확인해 주세요.');
    } catch (e) {
      setState(() => error = '방을 만들지 못했어요. 블루투스와 위치가 켜져 있는지 확인해 주세요.\n($e)');
    }
  }

  Future<void> _find() async {
    setState(() => error = null);
    if (!await _perm()) return;
    try {
      final ok = await session.discover();
      if (!ok) setState(() => error = '방 찾기를 시작하지 못했어요. 블루투스가 켜져 있는지 확인해 주세요.');
    } catch (e) {
      setState(() => error = '방 찾기를 시작하지 못했어요. 블루투스와 위치가 켜져 있는지 확인해 주세요.\n($e)');
    }
  }

  Future<void> _cancel() async {
    await session.close();
    if (mounted) setState(() => rooms = []);
  }

  @override
  Widget build(BuildContext context) {
    final s = session.status;
    Widget body;
    if (s == LinkStatus.advertising) {
      body = _waiting('친구를 기다리는 중...',
          '친구 폰에서 [방 찾기]를 누르고\n"${session.nickname}"을(를) 선택하세요.');
    } else if (s == LinkStatus.connecting) {
      body = _waiting('연결하는 중...', '잠시만 기다려 주세요.');
    } else if (s == LinkStatus.discovering) {
      body = Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('근처의 방',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: kInk)),
          const SizedBox(height: 8),
          if (rooms.isEmpty)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                SizedBox(
                    width: 18, height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2.5)),
                SizedBox(width: 10),
                Text('찾는 중... 친구가 [방 만들기]를 눌렀는지 확인하세요.'),
              ]),
            ),
          for (final r in rooms)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: BigButton(r.name,
                  sub: '눌러서 입장', icon: Icons.sports_volleyball,
                  color: kBlue, onTap: () => session.join(r)),
            ),
          const SizedBox(height: 10),
          TextButton(onPressed: _cancel, child: const Text('취소')),
        ],
      );
    } else {
      body = Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('블루투스 대전',
              style: TextStyle(fontSize: 28, fontWeight: FontWeight.w900, color: kInk)),
          const SizedBox(height: 6),
          const Text('한 명은 방을 만들고, 다른 한 명은 방을 찾아 들어가요.',
              style: TextStyle(color: kInk)),
          const SizedBox(height: 18),
          Wrap(spacing: 14, runSpacing: 10, alignment: WrapAlignment.center, children: [
            BigButton('방 만들기', sub: '내가 호스트', icon: Icons.add_circle_outline, onTap: _host),
            BigButton('방 찾기', sub: '친구 방에 입장', icon: Icons.search, color: kBlue, onTap: _find),
          ]),
          if (s == LinkStatus.lost) ...[
            const SizedBox(height: 12),
            const Text('연결이 끊어졌어요.', style: TextStyle(color: Colors.red)),
          ],
        ],
      );
    }

    return Scaffold(
      backgroundColor: kCream,
      appBar: AppBar(backgroundColor: kCream, elevation: 0, foregroundColor: kInk),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            body,
            if (error != null)
              Padding(
                padding: const EdgeInsets.only(top: 14),
                child: Text(error!,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.red)),
              ),
          ]),
        ),
      ),
    );
  }

  Widget _waiting(String title, String sub) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const CircularProgressIndicator(),
          const SizedBox(height: 16),
          Text(title,
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: kInk)),
          const SizedBox(height: 6),
          Text(sub, textAlign: TextAlign.center, style: const TextStyle(color: kInk)),
          const SizedBox(height: 14),
          TextButton(onPressed: _cancel, child: const Text('취소')),
        ],
      );
}
