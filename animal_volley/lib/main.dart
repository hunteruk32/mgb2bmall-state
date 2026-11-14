import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'audio.dart';
import 'settings.dart';
import 'ui/common.dart';
import 'ui/title_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // 가로 화면 고정
  SystemChrome.setPreferredOrientations([
    DeviceOrientation.landscapeLeft,
    DeviceOrientation.landscapeRight,
  ]);
  await GameSettings.instance.load();
  runApp(const AnimalVolleyApp());
  // 소리 파일은 화면을 띄운 뒤 천천히 불러온다
  GameAudio.instance.init().then((_) => GameAudio.instance.playBgm(Bgm.menu));
}

class AnimalVolleyApp extends StatefulWidget {
  const AnimalVolleyApp({super.key});

  @override
  State<AnimalVolleyApp> createState() => _AnimalVolleyAppState();
}

class _AnimalVolleyAppState extends State<AnimalVolleyApp> {
  late final AppLifecycleListener _life;

  @override
  void initState() {
    super.initState();
    // 앱이 화면에서 사라지면 음악 멈춤
    _life = AppLifecycleListener(
      onHide: () => GameAudio.instance.setPaused(true),
      onShow: () => GameAudio.instance.setPaused(false),
    );
  }

  @override
  void dispose() {
    _life.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '동물 배구',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: kOrange),
        useMaterial3: true,
      ),
      home: const TitleScreen(),
    );
  }
}
