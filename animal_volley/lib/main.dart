import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'ui/common.dart';
import 'ui/title_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // 가로 화면 고정
  SystemChrome.setPreferredOrientations([
    DeviceOrientation.landscapeLeft,
    DeviceOrientation.landscapeRight,
  ]);
  runApp(const AnimalVolleyApp());
}

class AnimalVolleyApp extends StatelessWidget {
  const AnimalVolleyApp({super.key});

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
