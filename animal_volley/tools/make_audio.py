#!/usr/bin/env python3
"""동물 배구의 효과음과 배경음악을 합성한다 (numpy + ffmpeg).

모든 소리는 이 스크립트에서 직접 만든다. 외부 음원은 쓰지 않는다.
사용법: python3 tools/make_audio.py   → assets/audio/*.ogg 생성
"""
import os
import subprocess
import tempfile
import wave

import numpy as np

SR = 32000
OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "audio")
rng = np.random.default_rng(42)


# ---------------------------------------------------------------------------
# 기본 재료
# ---------------------------------------------------------------------------
def t_(dur):
    return np.arange(int(SR * dur)) / SR


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def env(n, a=0.005, d=0.1, s=0.0, r=0.05, hold=None):
    """ADSR 엔벨로프. hold = 서스테인 길이(초)"""
    a_n, d_n, r_n = int(a * SR), int(d * SR), int(r * SR)
    h_n = n - a_n - d_n - r_n if hold is None else int(hold * SR)
    h_n = max(h_n, 0)
    e = np.concatenate([
        np.linspace(0, 1, a_n, endpoint=False),
        np.linspace(1, s, d_n, endpoint=False),
        np.full(h_n, s),
        np.linspace(s, 0, r_n),
    ])
    if len(e) < n:
        e = np.pad(e, (0, n - len(e)))
    return e[:n]


def exp_decay(n, tau):
    return np.exp(-np.arange(n) / (SR * tau))


def sweep(f0, f1, dur, shape="sine", curve=2.0):
    t = t_(dur)
    k = (t / dur) ** (1 / curve)
    f = f0 + (f1 - f0) * k
    ph = 2 * np.pi * np.cumsum(f) / SR
    return osc_ph(ph, shape)


def osc_ph(ph, shape):
    if shape == "sine":
        return np.sin(ph)
    if shape == "square":
        return np.sign(np.sin(ph)) * 0.6
    if shape == "tri":
        return 2 / np.pi * np.arcsin(np.sin(ph))
    if shape == "saw":
        return 2 * ((ph / (2 * np.pi)) % 1) - 1
    raise ValueError(shape)


def tone(freq, dur, shape="sine"):
    return osc_ph(2 * np.pi * freq * t_(dur), shape)


def onepole_lp(x, cutoff):
    """1차 저역통과 (벡터화가 어려워 블록 없이 루프, 짧은 소리에만 사용)"""
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def hp(x, cutoff):
    return x - onepole_lp(x, cutoff)


def noise(dur):
    return rng.uniform(-1, 1, int(SR * dur))


def pluck(freq, dur, bright=0.5, decay=0.996):
    """카플러스-스트롱 현 뜯는 소리 (주기 단위로 벡터화)"""
    n = int(SR * dur)
    p = max(2, int(round(SR / freq)))
    buf = rng.uniform(-1, 1, p)
    # 밝기: 초기 잡음을 살짝 저역통과
    for _ in range(int((1 - bright) * 4)):
        buf = 0.5 * (buf + np.roll(buf, 1))
    out = np.empty(n + p)
    out[:p] = buf
    k = p
    while k < n + p:
        prev = out[k - p:k]
        nxt = decay * 0.5 * (prev + np.concatenate([[prev[-1]], prev[:-1]]))
        m = min(p, n + p - k)
        out[k:k + m] = nxt[:m]
        k += m
    return out[p:]


def mallet(freq, dur, tau=0.18):
    """마림바 느낌: 기음 + 4배음, 빠른 감쇠"""
    t = t_(dur)
    x = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * freq * 4.0 * t) * exp_decay(len(t), tau * 0.25)
    return x * exp_decay(len(t), tau) * env(len(t), a=0.002, d=0.0, s=1.0, r=0.01)


def normalize(x, peak=0.9):
    m = np.max(np.abs(x)) or 1
    return x / m * peak


def mix_into(dst, src, at):
    i = int(at * SR)
    if i >= len(dst):
        return
    m = min(len(src), len(dst) - i)
    dst[i:i + m] += src[:m]


def save(name, x, quality=4):
    os.makedirs(OUT, exist_ok=True)
    x = np.clip(x, -1, 1)
    pcm = (x * 32767).astype(np.int16)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp = f.name
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    dst = os.path.join(OUT, name + ".ogg")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp,
                    "-c:a", "libvorbis", "-q:a", str(quality), dst], check=True)
    os.unlink(tmp)
    print(f"{dst}  {len(x) / SR:.2f}s")


# ---------------------------------------------------------------------------
# 효과음
# ---------------------------------------------------------------------------
def sfx_hit():  # 리시브: 통통한 '뽕'
    d = 0.16
    x = sweep(620, 170, d, curve=1.5) * exp_decay(int(SR * d), 0.05)
    click = hp(noise(0.012), 2000) * 0.35
    x[:len(click)] += click
    return normalize(x, 0.8)


def sfx_spike():  # 스파이크: 쉭 + 퍽
    d = 0.32
    n = int(SR * d)
    whoosh = hp(noise(d), 1500) * env(n, a=0.04, d=0.0, s=1.0, r=0.0, hold=0.0) * 0
    swoosh = onepole_lp(noise(0.09), 3500) * np.linspace(0, 1, int(SR * 0.09)) ** 2
    thump = sweep(260, 55, 0.25, curve=1.2) * exp_decay(int(SR * 0.25), 0.07)
    crack = hp(noise(0.03), 2500) * exp_decay(int(SR * 0.03), 0.008)
    x = np.zeros(n)
    mix_into(x, swoosh * 0.5, 0)
    mix_into(x, thump * 1.0, 0.08)
    mix_into(x, crack * 0.8, 0.08)
    x += whoosh
    return normalize(x, 0.95)


def sfx_net():  # 네트: 줄 튕기는 소리
    a = pluck(196, 0.45, bright=0.9, decay=0.993)
    b = pluck(293.7, 0.45, bright=0.9, decay=0.993)
    return normalize(a + 0.6 * b, 0.6)


def sfx_wall():
    d = 0.12
    x = sweep(180, 90, d) * exp_decay(int(SR * d), 0.035)
    return normalize(x, 0.5)


def sfx_ground():  # 모래에 '퍽'
    d = 0.28
    n = int(SR * d)
    sand = onepole_lp(noise(d), 900) * exp_decay(n, 0.07)
    thud = sweep(120, 50, d) * exp_decay(n, 0.06)
    return normalize(sand * 1.4 + thud, 0.85)


def sfx_jump():
    d = 0.12
    x = sweep(300, 700, d, shape="tri", curve=0.8) * env(int(SR * d), a=0.005, d=0.11, s=0, r=0.005)
    return normalize(x, 0.35)


def sfx_dive():
    d = 0.22
    n = int(SR * d)
    x = onepole_lp(noise(d), 1400) * env(n, a=0.03, d=0.18, s=0, r=0.01)
    return normalize(x, 0.5)


def sfx_whistle():  # 서브 신호
    d = 0.32
    t = t_(d)
    f = 2300 + 60 * np.sin(2 * np.pi * 28 * t)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.15 * noise(d)
    x = onepole_lp(x, 5000)
    return normalize(x * env(len(t), a=0.01, d=0.0, s=1.0, r=0.06), 0.35)


def arp(notes, step, dur, shape="square", vol=0.5, tau=0.15):
    total = step * (len(notes) - 1) + dur
    x = np.zeros(int(SR * total) + 1)
    for i, n in enumerate(notes):
        s = tone(midi(n), dur, shape) * exp_decay(int(SR * dur), tau) * env(int(SR * dur), a=0.003, d=0, s=1, r=0.02)
        mix_into(x, s, i * step)
    return normalize(x, vol)


def sfx_point_win():
    return arp([72, 76, 79, 84], 0.07, 0.25, "square", 0.45)


def sfx_point_lose():
    return arp([67, 63, 60], 0.12, 0.3, "tri", 0.5, tau=0.2)


def sfx_game_win():
    x = np.zeros(int(SR * 2.0))
    seq = [(60, 0.0), (64, 0.12), (67, 0.24), (72, 0.36)]
    for n, at in seq:
        mix_into(x, mallet(midi(n), 0.4) + 0.3 * tone(midi(n), 0.4, "square") * exp_decay(int(SR * 0.4), 0.1), at)
    for n in (72, 76, 79):
        s = tone(midi(n), 1.2, "square") * env(int(SR * 1.2), a=0.01, d=0.2, s=0.5, r=0.5) * 0.4
        s += mallet(midi(n), 1.2, tau=0.4)
        mix_into(x, s, 0.55)
    return normalize(x, 0.6)


def sfx_game_lose():
    x = np.zeros(int(SR * 2.0))
    for i, n in enumerate([67, 66, 65]):
        mix_into(x, tone(midi(n), 0.35, "saw") * env(int(SR * 0.35), a=0.01, d=0.1, s=0.6, r=0.1), i * 0.35)
    t = t_(0.9)
    f = midi(64) * (1 + 0.02 * np.sin(2 * np.pi * 6 * t)) * np.linspace(1, 0.94, len(t))
    s = osc_ph(2 * np.pi * np.cumsum(f) / SR, "saw") * env(len(t), a=0.02, d=0.1, s=0.7, r=0.4)
    mix_into(x, s, 1.05)
    x = onepole_lp(x, 1800)
    return normalize(x, 0.5)


def sfx_click():
    d = 0.05
    x = tone(1200, d, "sine") * exp_decay(int(SR * d), 0.012)
    return normalize(x, 0.4)


# ---------------------------------------------------------------------------
# 배경음악 (직접 작곡한 루프)
# ---------------------------------------------------------------------------
NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def n_(name):
    """'E5' 같은 이름 → MIDI 번호"""
    return 12 * (int(name[-1]) + 1) + NOTE[name[:-1]]


CHORDS = {
    "C": [0, 4, 7], "Am": [9, 12, 16], "F": [5, 9, 12], "G": [7, 11, 14],
    "Em": [4, 7, 11], "Dm": [2, 5, 9], "E": [4, 8, 11], "Bb": [10, 14, 17],
}


def kick():
    d = 0.25
    return sweep(150, 45, d, curve=1.0) * exp_decay(int(SR * d), 0.08)


_SHAKER = None


def shaker():
    global _SHAKER
    if _SHAKER is None:
        d = 0.06
        _SHAKER = hp(noise(d), 4500) * env(int(SR * d), a=0.01, d=0.05, s=0, r=0.0)
    return _SHAKER


_CLAP = None


def clap():
    global _CLAP
    if _CLAP is None:
        d = 0.18
        x = hp(onepole_lp(noise(d), 3000), 700)
        e = exp_decay(int(SR * d), 0.04)
        for k in (0.0, 0.01, 0.02):  # 손뼉 여러 번 겹친 느낌
            e[int(k * SR):] += 0.5 * exp_decay(len(e) - int(k * SR), 0.006)
        _CLAP = x * e
    return _CLAP


def render_song(bpm, progression, melody, root=48, swing=0.0, drums=True,
                strum_pattern=(0.5, 1.5, 2.5, 3.5), bass_pattern=(0, 1.5, 2, 3),
                lead_tau=0.22, lead_vol=0.55):
    beat = 60 / bpm
    bars = len(progression)
    total = bars * 4 * beat
    tail = 1.5
    x = np.zeros(int(SR * (total + tail)))

    def at(bar, b):
        # 8분음표 스윙
        frac = b % 1
        if abs(frac - 0.5) < 1e-6:
            b = b + swing
        return (bar * 4 + b) * beat

    for bar, ch in enumerate(progression):
        tones = CHORDS[ch]
        # 베이스
        for i, b in enumerate(bass_pattern):
            note = root - 12 + tones[0] + (7 if i % 2 == 1 else 0)
            s = tone(midi(note), beat * 0.9, "tri") * env(int(SR * beat * 0.9), a=0.005, d=0.25, s=0.4, r=0.05)
            mix_into(x, s * 0.5, at(bar, b))
        # 우쿨렐레 스트럼(엇박)
        for b in strum_pattern:
            for k, tn in enumerate(tones):
                s = pluck(midi(root + 12 + tn), beat * 1.2, bright=0.7, decay=0.994)
                mix_into(x, s * 0.16, at(bar, b) + k * 0.012)
        if drums:
            for b in (0, 2):
                mix_into(x, kick() * 0.7, at(bar, b))
            for b in (1, 3):
                mix_into(x, clap() * 0.28, at(bar, b))
            for k in range(8):
                mix_into(x, shaker() * (0.12 if k % 2 else 0.07), at(bar, k * 0.5))

    # 멜로디: (마디, 박, 음, 길이(박))
    for bar, b, name, length in melody:
        if name is None:
            continue
        f = midi(n_(name))
        d = length * beat + 0.2
        s = mallet(f, d, tau=lead_tau) + 0.12 * tone(f * 2, d, "sine") * exp_decay(int(SR * d), 0.08)
        mix_into(x, s * lead_vol, at(bar, b))

    # 아주 간단한 에코
    delay = int(SR * beat * 0.75)
    echo = np.zeros_like(x)
    echo[delay:] = x[:-delay] * 0.22
    x = x + echo

    # 끊김 없는 반복: 끝의 꼬리를 앞부분에 겹친다
    n_total = int(SR * total)
    loop = x[:n_total].copy()
    t_len = len(x) - n_total
    loop[:t_len] += x[n_total:]
    return normalize(loop, 0.75)


def mel(lines):
    """'마디:박:음:길이' 문자열 목록 → 튜플"""
    out = []
    for line in lines:
        for tok in line.split():
            bar, b, name, length = tok.split(":")
            out.append((int(bar), float(b), None if name == "-" else name, float(length)))
    return out


def bgm_game():
    prog = ["F", "G", "Em", "Am", "F", "G", "C", "C"] * 2
    a = [
        "0:0:A5:1 0:1:C6:0.5 0:1.5:A5:0.5 0:2:G5:1 0:3:F5:1",
        "1:0:G5:1.5 1:1.5:A5:0.5 1:2:B5:1 1:3:D6:1",
        "2:0:E6:1 2:1:D6:0.5 2:1.5:B5:0.5 2:2:G5:2",
        "3:0:A5:1 3:1:B5:0.5 3:1.5:C6:0.5 3:2:E6:1 3:3:C6:1",
        "4:0:A5:1 4:1:C6:0.5 4:1.5:A5:0.5 4:2:F5:1 4:3:A5:1",
        "5:0:B5:1 5:1:D6:0.5 5:1.5:B5:0.5 5:2:G5:1 5:3:B5:1",
        "6:0:C6:1.5 6:1.5:E6:0.5 6:2:G6:1 6:3:E6:1",
        "7:0:C6:3",
    ]
    b = [
        "8:0:F5:0.5 8:0.5:A5:0.5 8:1:C6:1 8:2:A5:0.5 8:2.5:C6:0.5 8:3:F6:1",
        "9:0:D6:1 9:1:B5:0.5 9:1.5:G5:0.5 9:2:B5:1 9:3:D6:1",
        "10:0:E6:0.5 10:0.5:D6:0.5 10:1:B5:0.5 10:1.5:G5:0.5 10:2:E5:1 10:3:G5:1",
        "11:0:A5:1.5 11:1.5:C6:0.5 11:2:E6:1 11:3:A6:1",
        "12:0:G6:0.5 12:0.5:F6:0.5 12:1:E6:0.5 12:1.5:C6:0.5 12:2:A5:1 12:3:C6:1",
        "13:0:D6:1 13:1:G6:1 13:2:F6:0.5 13:2.5:D6:0.5 13:3:B5:1",
        "14:0:C6:0.5 14:0.5:E6:0.5 14:1:G6:1 14:2:E6:0.5 14:2.5:D6:0.5 14:3:C6:1",
        "15:0:C6:2 15:2:G5:0.5 15:2.5:A5:0.5 15:3:B5:1",
    ]
    return render_song(132, prog, mel(a + b), root=48, swing=0.06)


def bgm_menu():
    prog = ["C", "Am", "Dm", "G", "C", "Am", "F", "G"]
    m = [
        "0:0:E5:1.5 0:1.5:G5:0.5 0:2:C6:2",
        "1:0:A5:1 1:1:G5:1 1:2:E5:2",
        "2:0:F5:1.5 2:1.5:A5:0.5 2:2:D6:1 2:3:C6:1",
        "3:0:B5:3 3:3:-:1",
        "4:0:E5:1.5 4:1.5:G5:0.5 4:2:C6:1 4:3:E6:1",
        "5:0:D6:1 5:1:C6:1 5:2:A5:2",
        "6:0:A5:1 6:1:C6:1 6:2:F6:1.5 6:3.5:E6:0.5",
        "7:0:D6:2 7:2:B5:1 7:3:G5:1",
    ]
    return render_song(100, prog, mel(m), root=48, swing=0.08,
                       strum_pattern=(0, 1.5, 2.5), bass_pattern=(0, 2),
                       lead_tau=0.35, lead_vol=0.5)


if __name__ == "__main__":
    for name, fn in [
        ("hit", sfx_hit), ("spike", sfx_spike), ("net", sfx_net), ("wall", sfx_wall),
        ("ground", sfx_ground), ("jump", sfx_jump), ("dive", sfx_dive),
        ("whistle", sfx_whistle), ("point_win", sfx_point_win),
        ("point_lose", sfx_point_lose), ("game_win", sfx_game_win),
        ("game_lose", sfx_game_lose), ("click", sfx_click),
    ]:
        save(name, fn(), quality=5)
    save("bgm_game", bgm_game(), quality=3)
    save("bgm_menu", bgm_menu(), quality=3)
