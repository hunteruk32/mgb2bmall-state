// 블루투스(근거리) 연결과 메시지 프로토콜
//
// Google Nearby Connections를 사용한다. 인터넷 없이 블루투스/BLE(+가능하면 Wi-Fi Direct)로
// 근처 기기와 1:1로 연결된다. 안드로이드 전용.
//
// 구조: '방 만들기'를 누른 쪽이 호스트. 호스트가 게임 물리를 계산하고
// 게스트에게 상태를 보내며, 게스트는 자기 버튼 입력만 호스트에게 보낸다.

import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:nearby_connections/nearby_connections.dart';
import 'package:permission_handler/permission_handler.dart';

import '../game/characters.dart';

class Msg {
  static const int pick = 1; // [animal, palette, ready]
  static const int start = 2; // 호스트 → 게스트: 경기 시작
  static const int input = 3; // 게스트 → 호스트: [bits]
  static const int state = 4; // 호스트 → 게스트: [snapshot...]
  static const int toSelect = 5; // 캐릭터 선택으로 돌아가기
  static const int rematch = 6; // 같은 캐릭터로 다시 하기
  static const int leave = 7;
}

class FoundRoom {
  final String endpointId;
  final String name;
  FoundRoom(this.endpointId, this.name);
}

enum LinkStatus { idle, advertising, discovering, connecting, connected, lost }

class NetSession {
  static const _serviceId = 'com.animalvolley.game';
  final _nearby = Nearby();

  final String nickname =
      '배구왕${(math.Random().nextInt(900) + 100)}';

  bool isHost = false;
  String? peerId;
  String? peerName;
  LinkStatus status = LinkStatus.idle;

  final _messages = StreamController<Uint8List>.broadcast();
  final _statusCtl = StreamController<LinkStatus>.broadcast();
  final _rooms = <String, FoundRoom>{};
  final _roomsCtl = StreamController<List<FoundRoom>>.broadcast();

  Stream<Uint8List> get messages => _messages.stream;
  Stream<LinkStatus> get statusChanges => _statusCtl.stream;
  Stream<List<FoundRoom>> get rooms => _roomsCtl.stream;

  /// 상대가 고른 캐릭터(선택 화면에서 갱신)
  CharacterLook? peerLook;
  bool peerReady = false;
  CharacterLook? myLook;

  void _setStatus(LinkStatus s) {
    status = s;
    _statusCtl.add(s);
  }

  /// 안드로이드 버전에 맞는 권한 요청. 모두 허용되면 true.
  static Future<bool> requestPermissions() async {
    final perms = <Permission>[
      Permission.location,
      Permission.bluetooth,
      Permission.bluetoothScan,
      Permission.bluetoothAdvertise,
      Permission.bluetoothConnect,
      Permission.nearbyWifiDevices,
    ];
    final result = await perms.request();
    // 일부 권한은 OS 버전에 따라 존재하지 않아 restricted/denied로 올 수 있다.
    // 블루투스 연결/검색과 위치(구버전 필수) 정도만 확인한다.
    bool ok(Permission p) {
      final s = result[p];
      return s == null || s.isGranted || s.isLimited;
    }

    final modern = ok(Permission.bluetoothScan) &&
        ok(Permission.bluetoothConnect) &&
        ok(Permission.bluetoothAdvertise);
    return modern || ok(Permission.location);
  }

  Future<bool> host() async {
    isHost = true;
    _setStatus(LinkStatus.advertising);
    return _nearby.startAdvertising(
      nickname,
      Strategy.P2P_POINT_TO_POINT,
      serviceId: _serviceId,
      onConnectionInitiated: _onInitiated,
      onConnectionResult: _onResult,
      onDisconnected: _onDisconnected,
    );
  }

  Future<bool> discover() async {
    isHost = false;
    _rooms.clear();
    _roomsCtl.add([]);
    _setStatus(LinkStatus.discovering);
    return _nearby.startDiscovery(
      nickname,
      Strategy.P2P_POINT_TO_POINT,
      serviceId: _serviceId,
      onEndpointFound: (id, name, serviceId) {
        _rooms[id] = FoundRoom(id, name);
        _roomsCtl.add(_rooms.values.toList());
      },
      onEndpointLost: (id) {
        _rooms.remove(id);
        _roomsCtl.add(_rooms.values.toList());
      },
    );
  }

  Future<void> join(FoundRoom room) async {
    _setStatus(LinkStatus.connecting);
    await _nearby.requestConnection(
      nickname,
      room.endpointId,
      onConnectionInitiated: _onInitiated,
      onConnectionResult: _onResult,
      onDisconnected: _onDisconnected,
    );
  }

  void _onInitiated(String id, ConnectionInfo info) {
    peerName = info.endpointName;
    // 1:1 게임이라 별도 확인 없이 자동 수락
    _nearby.acceptConnection(id, onPayLoadRecieved: (endpointId, payload) {
      final bytes = payload.bytes;
      if (payload.type == PayloadType.BYTES && bytes != null && bytes.isNotEmpty) {
        _messages.add(bytes);
      }
    });
  }

  void _onResult(String id, Status s) {
    if (s == Status.CONNECTED) {
      peerId = id;
      _nearby.stopAdvertising();
      _nearby.stopDiscovery();
      _setStatus(LinkStatus.connected);
    } else if (status != LinkStatus.connected) {
      _setStatus(isHost ? LinkStatus.advertising : LinkStatus.discovering);
    }
  }

  void _onDisconnected(String id) {
    if (id == peerId) {
      peerId = null;
      _setStatus(LinkStatus.lost);
    }
  }

  void send(List<int> bytes) {
    final id = peerId;
    if (id == null) return;
    _nearby.sendBytesPayload(id, Uint8List.fromList(bytes));
  }

  void sendPick(CharacterLook look, bool ready) {
    myLook = look;
    send([Msg.pick, look.animal.index, look.paletteIndex, ready ? 1 : 0]);
  }

  Future<void> close() async {
    if (peerId != null) send([Msg.leave]);
    await _nearby.stopAdvertising();
    await _nearby.stopDiscovery();
    await _nearby.stopAllEndpoints();
    peerId = null;
    _setStatus(LinkStatus.idle);
  }
}
