import 'package:animal_volley/game/world.dart';
import 'package:animal_volley/settings.dart';
import 'package:animal_volley/ui/touch_controls.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late TouchControlsController ctl;

  Future<void> pump(WidgetTester t) async {
    t.view.physicalSize = const Size(844, 390);
    t.view.devicePixelRatio = 1;
    addTearDown(t.view.reset);
    ctl = TouchControlsController();
    await t.pumpWidget(MaterialApp(
      home: TouchControls(controller: ctl, repaint: ValueNotifier(0)),
    ));
  }

  setUp(() => GameSettings.instance.stickSensitivity = 0.7); // 기본값

  testWidgets('조금만 밀어도 이동한다', (t) async {
    await pump(t);
    final g = await t.startGesture(const Offset(150, 300));
    await g.moveBy(const Offset(8, 0));
    await t.pump();
    expect(ctl.bits & Input.right, isNot(0));
    await g.up();
    await t.pump();
    expect(ctl.bits, 0);
  });

  testWidgets('오른쪽 끝까지 밀었다가 왼쪽으로 조금만 움직이면 바로 왼쪽', (t) async {
    await pump(t);
    final g = await t.startGesture(const Offset(150, 300));
    await g.moveBy(const Offset(80, 0)); // 멀리 밀기
    await t.pump();
    expect(ctl.bits & Input.right, isNot(0));
    // 기준점이 따라왔기 때문에 손가락을 30px만 되돌려도 왼쪽이 된다
    await g.moveBy(const Offset(-30, 0));
    await t.pump();
    expect(ctl.bits & Input.left, isNot(0));
    expect(ctl.bits & Input.right, 0);
    await g.up();
  });

  testWidgets('위로 살짝 튕기면 점프, 내렸다 다시 올리면 또 점프', (t) async {
    await pump(t);
    final g = await t.startGesture(const Offset(150, 300));
    await g.moveBy(const Offset(0, -12));
    await t.pump();
    expect(ctl.bits & Input.jump, isNot(0));
    await g.moveBy(const Offset(0, 12));
    await t.pump();
    expect(ctl.bits & Input.jump, 0);
    await g.moveBy(const Offset(0, -12));
    await t.pump();
    expect(ctl.bits & Input.jump, isNot(0));
    await g.up();
  });

  testWidgets('조이스틱과 스파이크를 동시에 누를 수 있다', (t) async {
    await pump(t);
    final a = await t.startGesture(const Offset(150, 300));
    await a.moveBy(const Offset(10, -15));
    final b = await t.startGesture(const Offset(700, 200), pointer: 9);
    await t.pump();
    expect(ctl.bits & Input.right, isNot(0));
    expect(ctl.bits & Input.jump, isNot(0));
    expect(ctl.bits & Input.hit, isNot(0));
    await a.up();
    await b.up();
  });
}
