import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import '../audio.dart';
import '../game/characters.dart';

const kInk = Color(0xFF2B2440);
const kCream = Color(0xFFFFF4DC);
const kOrange = Color(0xFFFF8A3D);
const kBlue = Color(0xFF3FA7D6);

class BigButton extends StatelessWidget {
  final String label;
  final String? sub;
  final IconData? icon;
  final Color color;
  final VoidCallback? onTap;
  const BigButton(this.label,
      {super.key, this.sub, this.icon, this.color = kOrange, this.onTap});

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    return Opacity(
      opacity: enabled ? 1 : 0.45,
      child: Material(
        color: color,
        borderRadius: BorderRadius.circular(18),
        elevation: enabled ? 3 : 0,
        child: InkWell(
          borderRadius: BorderRadius.circular(18),
          onTap: onTap == null
              ? null
              : () {
                  GameAudio.instance.play(Sfx.click);
                  onTap!();
                },
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 12),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (icon != null) ...[
                  Icon(icon, color: Colors.white, size: 26),
                  const SizedBox(width: 10),
                ],
                Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label,
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 20,
                            fontWeight: FontWeight.w800)),
                    if (sub != null)
                      Text(sub!,
                          style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.85),
                              fontSize: 12)),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// 계속 움직이는 캐릭터 한 마리
class CharacterView extends StatefulWidget {
  final CharacterLook look;
  final Pose pose;
  final double size;
  final int facing;
  const CharacterView(this.look,
      {super.key, this.pose = Pose.idle, this.size = 100, this.facing = 1});

  @override
  State<CharacterView> createState() => _CharacterViewState();
}

class _CharacterViewState extends State<CharacterView>
    with SingleTickerProviderStateMixin {
  late final Ticker _ticker;
  final _time = ValueNotifier<double>(0);

  @override
  void initState() {
    super.initState();
    _ticker = createTicker((e) => _time.value = e.inMicroseconds / 1e6)..start();
  }

  @override
  void dispose() {
    _ticker.dispose();
    _time.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.size,
      height: widget.size,
      child: CustomPaint(
        painter: _CharPainter(widget.look, widget.pose, widget.facing, _time),
      ),
    );
  }
}

class _CharPainter extends CustomPainter {
  final CharacterLook look;
  final Pose pose;
  final int facing;
  final ValueNotifier<double> time;
  _CharPainter(this.look, this.pose, this.facing, this.time)
      : super(repaint: time);

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.translate(size.width / 2, size.height / 2);
    canvas.scale(size.width / 110);
    paintCharacter(canvas, look, pose, time.value, facing: facing);
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _CharPainter old) =>
      old.look != look || old.pose != pose || old.facing != facing;
}

Future<void> showInfo(BuildContext context, String title, String body) {
  return showDialog(
    context: context,
    builder: (c) => AlertDialog(
      title: Text(title),
      content: Text(body),
      actions: [
        TextButton(onPressed: () => Navigator.pop(c), child: const Text('확인')),
      ],
    ),
  );
}
