#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import sys, math, random, time
from PyQt6.QtWidgets import (QApplication, QWidget, QMenu, QSystemTrayIcon)
from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPainterPath, QPolygonF,
    QFontMetrics, QCursor, QPixmap, QPen, QIcon)

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

BS = 32
MAX_BLOCKS = 500
MAX_WATER  = 150
MAX_PETS   = 20
PLACE_MIN_MS, PLACE_MAX_MS = 800, 2500
MAX_PLACE_DIST = 200
DAY_CYCLE_SEC = 240
INITIAL_DAY_PHASE = 0.10

PETS, CANVAS = [], None
GLOBALLY_HIDDEN = False
TRAY = None

_star_rnd = random.Random(42)
STARS = [(_star_rnd.uniform(0.02, 0.98),
          _star_rnd.uniform(0.02, 0.45),
          _star_rnd.randint(1, 2),
          _star_rnd.uniform(0, math.pi * 2)) for _ in range(80)]


def C(h, a=255):
    return QColor((h >> 16) & 0xFF, (h >> 8) & 0xFF, h & 0xFF, a)

def P(**kw):
    return {k: C(v) for k, v in kw.items()}

def to_logic(gx, gy):
    if CANVAS is None: return gx, gy
    return gx - CANVAS._ox, gy - CANVAS._oy

def lerp_rgba(c1, c2, t):
    return QColor(
        int(c1.red()   + (c2.red()   - c1.red())   * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue()  + (c2.blue()  - c1.blue())  * t),
        int(c1.alpha() + (c2.alpha() - c1.alpha()) * t))


# ===================== 12 种方块 =====================
BLOCK_KINDS = {
    'dirt': 0x8b6c3f, 'grass': 0x6a9a3a, 'stone': 0x808080, 'sand': 0xe0d0a0,
    'wood': 0x8a6030, 'leaves': 0x3a8030, 'diamond': 0x40d0e0, 'gold': 0xf0c040,
    'brick': 0xa05050, 'obsidian': 0x201030, 'bone': 0xe0e0d0, 'mossy': 0x608040,
}


# ===================== 15 个角色（全中文名） =====================
CHARACTERS = {
    'steve': dict(name='史蒂夫', blocks=['dirt', 'grass', 'wood', 'stone'],
        can_build=True, draw='humanoid', hp=20, cd=(200, 300), auto_water=0.25,
        colors=P(hair=0x4a2c14, skin=0xc69c6d, skin_dark=0xb0885a,
            shirt=0x1e908a, shirt_dark=0x146e6a, pants=0x2a2e8e,
            pants_dark=0x1e226a, shoes=0x202020, eye=0x203080, mouth=0x704028),
        say=["你好！", "天气不错~", "该挖矿了", "小心脚下！"]),
    'alex': dict(name='艾利克斯', blocks=['wood', 'leaves', 'grass', 'dirt'],
        can_build=True, draw='humanoid', hp=20, cd=(200, 300), auto_water=0.25,
        colors=P(hair=0xa04a20, skin=0xd8a878, skin_dark=0xb88858,
            shirt=0x3cb050, shirt_dark=0x28903c, pants=0x6a4a30,
            pants_dark=0x50361e, shoes=0x403020, eye=0x306840, mouth=0x906050),
        say=["嗨~", "来盖房子吧", "这木头真不错", "森林之友"]),
    'creeper': dict(name='苦力怕', blocks=[],
        can_build=False, draw='creeper', hp=10, cd=(300, 450),
        skill='explode', auto_water=0.15,
        say=["嘶——", "嘶！", "嘶嘶嘶"]),
    'zombie': dict(name='僵尸', blocks=[],
        can_build=False, draw='humanoid', hp=20, cd=(80, 130), skill='chase',
        colors=P(hair=0x2a3a20, skin=0x6a9a5a, skin_dark=0x506e40,
            shirt=0x3a5a9a, shirt_dark=0x2a406e, pants=0x3a3a5a,
            pants_dark=0x2a2a40, shoes=0x202018, eye=0x101010, mouth=0x203020),
        say=["大脑…", "饿了…", "呃啊…"]),
    'skeleton': dict(name='骷髅', blocks=[],
        can_build=False, draw='humanoid', hp=15, cd=(120, 200),
        skill='shoot_arrow', auto_water=0.10,
        colors=P(hair=0x808080, skin=0xdcdcd0, skin_dark=0xa0a098,
            shirt=0xb0b0a8, shirt_dark=0x808078, pants=0x909090,
            pants_dark=0x606060, shoes=0x404040, eye=0x101010, mouth=0x505050),
        say=["咔哒咔哒", "瞄准中…", "接箭！"]),
    'enderman': dict(name='末影人', blocks=[],
        can_build=False, draw='enderman', hp=20, cd=(200, 300),
        skill='teleport', auto_water=0.35,
        say=["…", "呜噗", "别看我的眼睛"]),
    'villager': dict(name='村民', blocks=[],
        can_build=False, draw='villager', hp=15, cd=(350, 550), skill='heal',
        auto_spawn='villager', auto_spawn_rate=0.10, auto_water=0.15,
        say=["嗯…", "交易吗？", "绿宝石？"]),
    'pig': dict(name='猪', blocks=[],
        can_build=False, draw='quadruped', hp=10, cd=(300, 500),
        colors=P(body=0xf0a8a8, body_d=0xd08888, face=0xd08888,
            eye=0x101010, extra=0xf7c8c8, snout=0xc07878, hoof=0x8a5050),
        size=(16, 12, 6), auto_spawn='pig', auto_spawn_rate=0.08,
        say=["哼哼", "呼噜呼噜"]),
    'herobrine': dict(name='Herobrine', blocks=[],
        can_build=False, draw='humanoid', hp=30, cd=(250, 400), skill='lightning',
        colors=P(hair=0x4a2c14, skin=0xc69c6d, skin_dark=0xb0885a,
            shirt=0x1e908a, shirt_dark=0x146e6a, pants=0x2a2e8e,
            pants_dark=0x1e226a, shoes=0x202020, eye=0xffffff, mouth=0x704028),
        say=["…", "我看到你了", "别回头"]),
    'slime': dict(name='史莱姆', blocks=[],
        can_build=False, draw='slime', hp=12, cd=(180, 280),
        skill='smash', auto_water=0.20,
        say=["啵~", "啪叽", "噗叽"]),
    'wolf': dict(name='狼', blocks=[],
        can_build=False, draw='quadruped', hp=20, cd=(100, 160), skill='chase',
        colors=P(body=0x808080, body_d=0x606060, face=0xa0a0a0,
            eye=0x202020, extra=0xd0d0d0, snout=0x404040, hoof=0x404040),
        size=(14, 12, 5), auto_spawn='wolf', auto_spawn_rate=0.06,
        say=["汪！", "嗷呜——", "汪汪"]),
    'spider': dict(name='蜘蛛', blocks=[],
        can_build=False, draw='spider', hp=16, cd=(80, 140), skill='crawl',
        colors=P(body=0x282828, body_d=0x101010, body_l=0x404040,
            eye=0xff2020, leg=0x202020),
        say=["嘶嘶…", "嘻嘻嘻", "啧啧"]),
    'allay': dict(name='悦灵', blocks=[],
        can_build=False, draw='allay', hp=15, cd=(250, 400), skill='sing',
        auto_water=0.05, can_fly=True,
        say=["♪", "♫", "啦啦~", "🎵", "嗯~", "🎶"]),
    'chicken': dict(name='鸡', blocks=[],
        can_build=False, draw='small_bird', hp=8, cd=(200, 350), skill='lay_egg',
        colors=P(body=0xf8f8f8, body_d=0xd0d0c8, beak=0xf0c040,
            comb=0xe03030, eye=0x101010, foot=0xf0a020),
        auto_spawn='chicken', auto_spawn_rate=0.15,
        say=["咯咯", "咕咕咕", "咯咯哒"]),
    'cow': dict(name='牛', blocks=[],
        can_build=False, draw='quadruped', hp=15, cd=(300, 450), skill='charge',
        colors=P(body=0x8a5a3a, body_d=0x5a3a20, face=0xc09878,
            eye=0x101010, extra=0xf0e8e0, snout=0xc07858, hoof=0x302020),
        size=(16, 14, 6), auto_spawn='cow', auto_spawn_rate=0.08,
        say=["哞——", "哞哞"]),
}


# ===================== 气泡 =====================
class SpeechBubble(QWidget):
    def __init__(self, text, pet):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput |
            Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._text = text; self._pet = pet
        self._font = QFont("Microsoft YaHei", 10)
        fm = QFontMetrics(self._font)
        w = max(fm.horizontalAdvance(text) + 28, 70)
        h = fm.height() + 18
        self.setFixedSize(w, h + 8)
        self._update_position()
        self._ft = QTimer(self)
        self._ft.timeout.connect(self._follow)
        self._ft.start(60)
        QTimer.singleShot(3000, self.close)

    def _follow(self):
        if (not self._pet or not self._pet.isVisible()
                or getattr(self._pet, '_dead', False)):
            self.close(); return
        self._update_position()

    def _update_position(self):
        if not self._pet: return
        screen = QApplication.primaryScreen().availableGeometry()
        tx = self._pet.x() + self._pet.width() // 2 - self.width() // 2
        ty = self._pet.y() - self.height() - 4
        tx = max(screen.left() + 4, min(tx, screen.right() - self.width() - 4))
        ty = max(screen.top() + 4, ty)
        self.move(tx, ty)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height() - 8, 10, 10)
        path.addPolygon(QPolygonF([
            QPointF(self.width() / 2 - 8, self.height() - 9),
            QPointF(self.width() / 2 + 8, self.height() - 9),
            QPointF(self.width() / 2, self.height() - 1)]))
        p.fillPath(path, QColor(255, 255, 255, 235))
        p.setPen(QColor(90, 90, 90)); p.drawPath(path)
        p.setPen(QColor(30, 30, 30)); p.setFont(self._font)
        p.drawText(self.rect().adjusted(0, 0, 0, -8),
                   Qt.AlignmentFlag.AlignCenter, self._text)


# ===================== 方块纹理 =====================
_block_pixmaps = {}

def get_block_pixmap(kind):
    if kind in _block_pixmaps: return _block_pixmaps[kind]
    color = C(BLOCK_KINDS.get(kind, 0x8b6c3f))
    pm = QPixmap(BS, BS); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    cell = max(1, BS // 8)
    rnd = random.Random(hash(kind) & 0xFFFFFF)

    def noise(base_col, variations):
        for py in range(8):
            for px in range(8):
                v = rnd.choice(variations)
                p.fillRect(px * cell, py * cell, cell, cell,
                           QColor(max(0, min(255, base_col.red() + v)),
                                  max(0, min(255, base_col.green() + v)),
                                  max(0, min(255, base_col.blue() + v))))

    if kind == 'grass':
        for py in range(8):
            for px in range(8):
                v = rnd.choice([-15, -8, 0, 5, 10])
                base = QColor(0x6a, 0xa8, 0x3a) if py < 3 else QColor(0x8b, 0x6c, 0x3f)
                p.fillRect(px * cell, py * cell, cell, cell,
                           QColor(max(0, min(255, base.red() + v)),
                                  max(0, min(255, base.green() + v)),
                                  max(0, min(255, base.blue() + v))))
        p.fillRect(0, 3 * cell, BS, 2, QColor(0x50, 0x80, 0x28))
    elif kind == 'stone':
        noise(color, [-25, -15, -5, 0, 5, 15])
        for _ in range(3):
            px, py = rnd.randint(0, 6), rnd.randint(0, 6)
            p.fillRect(px * cell, py * cell, cell * 2, cell, color.darker(160))
    elif kind == 'wood':
        for px in range(8):
            v = rnd.choice([-15, -8, 0, 5, 12])
            p.fillRect(px * cell, 0, cell, BS,
                       QColor(max(0, min(255, color.red() + v)),
                              max(0, min(255, color.green() + v)),
                              max(0, min(255, color.blue() + v))))
        for _ in range(2):
            py = rnd.randint(0, 7)
            p.fillRect(0, py * cell, BS, 1, color.darker(160))
    elif kind == 'sand':
        noise(color, [-8, 0, 0, 5, 8])
        for _ in range(5):
            px, py = rnd.randint(0, 7), rnd.randint(0, 7)
            p.fillRect(px * cell, py * cell, cell // 2, cell // 2, color.lighter(130))
    elif kind == 'diamond':
        noise(color, [-10, 0, 5, 10])
        cx, cy = BS // 2, BS // 2
        p.setPen(QPen(color.lighter(200), 2))
        p.drawPolygon(QPolygonF([QPointF(cx, cy - 9), QPointF(cx + 9, cy),
                                  QPointF(cx, cy + 9), QPointF(cx - 9, cy)]))
    elif kind == 'gold':
        noise(color, [-10, 0, 10, 15])
        p.setPen(QPen(color.lighter(180), 1))
        p.drawLine(6, 6, BS - 6, BS - 6); p.drawLine(BS - 6, 6, 6, BS - 6)
    elif kind == 'brick':
        p.fillRect(0, 0, BS, BS, color)
        p.setPen(QPen(color.darker(180), 2))
        p.drawLine(0, BS // 2, BS, BS // 2)
        p.drawLine(BS // 2, 0, BS // 2, BS // 2)
        p.drawLine(BS // 4, BS // 2, BS // 4, BS)
        p.drawLine(3 * BS // 4, BS // 2, 3 * BS // 4, BS)
    elif kind == 'obsidian':
        noise(color, [-8, 0, 3, 8])
        for _ in range(3):
            px, py = rnd.randint(0, 6), rnd.randint(0, 6)
            p.fillRect(px * cell, py * cell, cell, cell, QColor(0xa0, 0x60, 0xe0))
    elif kind == 'bone':
        noise(color, [-8, 0, 5, 10])
        for _ in range(3):
            px, py = rnd.randint(0, 7), rnd.randint(0, 7)
            p.fillRect(px * cell, py * cell, cell, cell, color.lighter(140))
    elif kind == 'mossy':
        for py in range(8):
            for px in range(8):
                v = rnd.choice([-15, -8, 0, 8, 15])
                base = QColor(0x5a, 0xa0, 0x50) if rnd.random() < 0.35 else color
                p.fillRect(px * cell, py * cell, cell, cell,
                           QColor(max(0, min(255, base.red() + v)),
                                  max(0, min(255, base.green() + v)),
                                  max(0, min(255, base.blue() + v))))
    elif kind == 'leaves':
        for py in range(8):
            for px in range(8):
                if rnd.random() < 0.2:
                    p.fillRect(px * cell, py * cell, cell, cell, QColor(0x1a, 0x40, 0x10))
                else:
                    v = rnd.choice([-10, 0, 5, 10])
                    p.fillRect(px * cell, py * cell, cell, cell,
                               QColor(max(0, min(255, color.red() + v)),
                                      max(0, min(255, color.green() + v)),
                                      max(0, min(255, color.blue() + v))))
    else:
        noise(color, [-18, -10, -5, 0, 0, 0, 0, 5, 10, 18])

    p.fillRect(0, 0, BS, 2, color.lighter(150))
    p.fillRect(0, BS - 2, BS, 2, color.darker(140))
    p.setPen(QPen(color.darker(170), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(0, 0, BS - 1, BS - 1)
    p.end()
    _block_pixmaps[kind] = pm
    return pm


# ===================== 画布 =====================
class BlockCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput |
            Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        avail = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(avail)
        self._ox, self._oy = avail.x(), avail.y()

        self._blocks, self._occupied = [], set()
        self._water, self._water_occupied = [], set()
        self.projectiles, self.explosions, self.floaters = [], [], []
        self._debris = []
        self._place_rings = []

        self._start_time = time.time()
        self._day_phase = INITIAL_DAY_PHASE
        self._wave_t = 0
        self._phys_accum = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def add_block(self, gx, gy, kind):
        cx = (gx - self._ox) // BS
        cy = (gy - self._oy) // BS
        while (cx, cy) in self._occupied or (cx, cy) in self._water_occupied:
            cy -= 1
        if cy < 0: return
        self._occupied.add((cx, cy))
        self._blocks.append({'cx': cx, 'cy': cy, 'kind': kind, 'appear': 0.0})
        while len(self._blocks) > MAX_BLOCKS:
            old = self._blocks.pop(0)
            self._occupied.discard((old['cx'], old['cy']))

    def add_water(self, gx, gy):
        cx = (gx - self._ox) // BS
        cy = (gy - self._oy) // BS
        if (cx, cy) in self._occupied or (cx, cy) in self._water_occupied:
            return
        if len(self._water) >= MAX_WATER: return
        self._water_occupied.add((cx, cy))
        self._water.append({'cx': cx, 'cy': cy, 'life': 180})

    def clear_all(self):
        self._blocks.clear(); self._occupied.clear()
        self._water.clear(); self._water_occupied.clear()
        self.projectiles.clear(); self.explosions.clear(); self.floaters.clear()
        self._debris.clear(); self._place_rings.clear()
        self.update()

    def add_projectile(self, lx, ly, vx, vy, owner, kind='arrow', damage=3):
        self.projectiles.append({'x': lx, 'y': ly, 'vx': vx, 'vy': vy,
            'owner': owner, 'kind': kind, 'damage': damage, 'life': 150})

    def add_explosion(self, lx, ly, radius=80, source=None, kind='creeper'):
        exp = {'x': lx, 'y': ly, 'radius': radius, 't': 0,
               'duration': 22, 'kind': kind}
        self.explosions.append(exp)
        destroyed_kinds = self._apply_explosion(exp, source)
        n = min(20, max(6, len(destroyed_kinds) * 2))
        for _ in range(n):
            ang = random.uniform(0, math.pi * 2)
            spd = random.uniform(3, 9)
            kd = random.choice(destroyed_kinds) if destroyed_kinds else 'dirt'
            self._debris.append({
                'x': lx, 'y': ly,
                'vx': math.cos(ang) * spd,
                'vy': math.sin(ang) * spd - 3,
                'color': C(BLOCK_KINDS.get(kd, 0x8b6c3f)),
                'size': random.randint(3, 6),
                'life': 45,
            })

    def _apply_explosion(self, exp, source):
        r = exp['radius']
        remaining, destroyed_kinds = [], []
        for b in self._blocks:
            bx = b['cx'] * BS + BS // 2
            by = b['cy'] * BS + BS // 2
            if math.hypot(bx - exp['x'], by - exp['y']) <= r:
                self._occupied.discard((b['cx'], b['cy']))
                destroyed_kinds.append(b['kind'])
            else:
                remaining.append(b)
        self._blocks = remaining
        rem_w = []
        for w in self._water:
            wx = w['cx'] * BS + BS // 2
            wy = w['cy'] * BS + BS // 2
            if math.hypot(wx - exp['x'], wy - exp['y']) <= r:
                self._water_occupied.discard((w['cx'], w['cy']))
            else: rem_w.append(w)
        self._water = rem_w
        for pet in PETS:
            if pet is source or pet._dead: continue
            px, py = to_logic(pet.x() + pet.width() // 2,
                              pet.y() + pet.height() // 2)
            d = math.hypot(px - exp['x'], py - exp['y'])
            if d <= r:
                pet.take_damage(int(8 * (1 - d / r)) + 2, source)
        if destroyed_kinds:
            self.add_floater(exp['x'], exp['y'] - 30,
                             f"💥 方块 ×{len(destroyed_kinds)}", (255, 200, 100))
        return destroyed_kinds

    def add_floater(self, lx, ly, text, color=(255, 255, 255)):
        self.floaters.append({'x': lx, 'y': ly, 'text': text,
                              'color': color, 'life': 60, 'vy': -0.8})

    def _do_physics(self):
        rows = self.height() // BS + 1
        cols = self.width() // BS + 1
        changed = False
        self._blocks.sort(key=lambda b: -b['cy'])
        for b in self._blocks:
            if b['cy'] + 1 >= rows: continue
            below = (b['cx'], b['cy'] + 1)
            if below not in self._occupied and below not in self._water_occupied:
                self._occupied.discard((b['cx'], b['cy']))
                b['cy'] += 1
                self._occupied.add((b['cx'], b['cy']))
                changed = True
        new_water = []
        for w in self._water:
            w['life'] -= 3
            if w['life'] <= 0:
                self._water_occupied.discard((w['cx'], w['cy'])); continue
            if w['cy'] + 1 < rows:
                below = (w['cx'], w['cy'] + 1)
                if below not in self._occupied and below not in self._water_occupied:
                    self._water_occupied.discard((w['cx'], w['cy']))
                    w['cy'] += 1
                    self._water_occupied.add((w['cx'], w['cy']))
                    changed = True; new_water.append(w); continue
            if w['life'] > 80 and len(new_water) + len(self._water) < MAX_WATER:
                for dx in random.sample([-1, 1], 2):
                    nx = w['cx'] + dx
                    if 0 <= nx < cols:
                        tgt = (nx, w['cy'])
                        if tgt not in self._occupied and tgt not in self._water_occupied:
                            self._water_occupied.add(tgt)
                            new_water.append({'cx': nx, 'cy': w['cy'],
                                              'life': w['life'] - 50})
                            changed = True; break
            new_water.append(w)
        self._water = new_water
        return changed

    def set_day_phase(self, phase):
        self._start_time = time.time() - phase * DAY_CYCLE_SEC

    def _day_brightness(self):
        return (math.cos(self._day_phase * 2 * math.pi) + 1) / 2

    def _update_day(self):
        elapsed = time.time() - self._start_time
        self._day_phase = (elapsed / DAY_CYCLE_SEC + INITIAL_DAY_PHASE) % 1.0

    def add_place_ring(self, lx, ly):
        self._place_rings.append({'x': lx, 'y': ly, 'life': 18})

    def _tick(self):
        if not self.isVisible():
            return
        self._wave_t += 1
        self._update_day()
        changed = False

        for b in self._blocks:
            if b['appear'] < 1.0:
                b['appear'] = min(1.0, b['appear'] + 0.20)
                changed = True

        self._phys_accum += 1
        if self._phys_accum >= 3:
            self._phys_accum = 0
            if self._do_physics(): changed = True

        still = []
        for proj in self.projectiles:
            proj['x'] += proj['vx']; proj['y'] += proj['vy']; proj['life'] -= 1
            if (proj['x'] < -50 or proj['y'] < -50 or
                    proj['x'] > self.width() + 50 or
                    proj['y'] > self.height() + 50 or proj['life'] <= 0):
                changed = True; continue
            hit = False
            for pet in PETS:
                if pet is proj['owner'] or pet._dead: continue
                px, py = to_logic(pet.x() + pet.width() // 2,
                                  pet.y() + pet.height() // 2)
                if abs(px - proj['x']) < 30 and abs(py - proj['y']) < 40:
                    pet.take_damage(proj['damage'], proj['owner'])
                    hit = True; break
            if not hit: still.append(proj)
            changed = True
        self.projectiles = still

        still = []
        for exp in self.explosions:
            exp['t'] += 1
            if exp['t'] < exp['duration']: still.append(exp); changed = True
        self.explosions = still

        still = []
        for d in self._debris:
            d['vy'] += 0.55
            d['x'] += d['vx']; d['y'] += d['vy']
            d['vx'] *= 0.98
            d['life'] -= 1
            if d['life'] > 0 and d['y'] < self.height() - 4:
                still.append(d)
            changed = True
        self._debris = still

        still = []
        for r in self._place_rings:
            r['life'] -= 1
            if r['life'] > 0: still.append(r)
            changed = True
        self._place_rings = still

        still = []
        for fl in self.floaters:
            fl['y'] += fl['vy']; fl['life'] -= 1
            if fl['life'] > 0: still.append(fl)
            changed = True
        self.floaters = still

        if changed: self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self._paint_sky(p)
        self._paint_celestial(p)
        for w in self._water: self._draw_water(p, w)
        for b in self._blocks: self._draw_block(p, b)
        for proj in self.projectiles: self._draw_projectile(p, proj)
        for exp in self.explosions: self._draw_explosion(p, exp)
        for d in self._debris: self._draw_debris(p, d)
        for r in self._place_rings: self._draw_place_ring(p, r)
        for fl in self.floaters: self._draw_floater(p, fl)
        p.end()

    def _paint_sky(self, p):
        b = self._day_brightness()
        if b < 0.35:
            t = b / 0.35
            col = lerp_rgba(QColor(20, 20, 60, 90),
                            QColor(255, 120, 60, 45), t)
        elif b < 0.55:
            t = (b - 0.35) / 0.20
            col = lerp_rgba(QColor(255, 120, 60, 45),
                            QColor(0, 0, 0, 0), t)
        else:
            col = QColor(0, 0, 0, 0)
        if col.alpha() > 0:
            p.fillRect(0, 0, self.width(), self.height(), col)

    def _paint_celestial(self, p):
        b = self._day_brightness()
        cx, cy = self.width() - 70, 70
        if b > 0.3:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 200, 80, 55))
            p.drawEllipse(QPointF(cx, cy), 42, 42)
            alpha = int(180 + 75 * b)
            p.setBrush(QColor(255, 240, 150, alpha))
            p.drawEllipse(QPointF(cx, cy), 20, 20)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(200, 220, 255, 40))
            p.drawEllipse(QPointF(cx, cy), 36, 36)
            p.setBrush(QColor(240, 240, 255, 230))
            p.drawEllipse(QPointF(cx, cy), 18, 18)
            for fx, fy, size, phase in STARS:
                tw = int(140 + 100 * math.sin(self._wave_t * 0.05 + phase))
                p.fillRect(int(fx * self.width()), int(fy * self.height()),
                           size, size, QColor(255, 255, 255, tw))

    def _draw_block(self, p, b):
        x, y = b['cx'] * BS, b['cy'] * BS
        pm = get_block_pixmap(b['kind'])
        s = b['appear']
        if s >= 1.0:
            p.drawPixmap(x, y, pm)
        else:
            size = int(BS * s); off = (BS - size) // 2
            p.drawPixmap(x + off, y + off,
                         pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.FastTransformation))

    def _draw_water(self, p, w):
        x, y = w['cx'] * BS, w['cy'] * BS
        alpha = min(220, int(w['life'] * 220 / 180))
        p.fillRect(x, y, BS, BS, QColor(70, 140, 230, alpha))
        wave = int(math.sin(self._wave_t * 0.15 + w['cx'] * 0.7) * 2)
        p.fillRect(x, y + 3 + wave, BS, 3, QColor(220, 240, 255, alpha // 2))
        p.fillRect(x, y + BS - 3, BS, 2, QColor(160, 210, 255, alpha // 2))

    def _draw_projectile(self, p, proj):
        x, y = proj['x'], proj['y']
        vx, vy = proj['vx'], proj['vy']
        mag = math.hypot(vx, vy) or 1
        ux, uy = vx / mag, vy / mag
        if proj['kind'] == 'arrow':
            p.setPen(QPen(QColor(140, 90, 40), 2))
            p.drawLine(QPointF(x - ux * 15, y - uy * 15), QPointF(x, y))
            p.setPen(QPen(QColor(60, 60, 60), 1))
            p.setBrush(QColor(220, 220, 220))
            tip = QPointF(x + ux * 6, y + uy * 6)
            ax, ay = x - ux * 3, y - uy * 3
            p.drawPolygon(QPolygonF([tip,
                QPointF(ax - uy * 3, ay + ux * 3),
                QPointF(ax + uy * 3, ay - ux * 3)]))

    def _draw_explosion(self, p, exp):
        prog = exp['t'] / exp['duration']
        wave_r = exp['radius'] * 1.3 * prog
        wave_alpha = int(180 * (1 - prog))
        p.setPen(QPen(QColor(255, 255, 255, wave_alpha), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(exp['x'], exp['y']), wave_r, wave_r)
        r = exp['radius'] * math.sin(prog * math.pi)
        alpha = int(255 * (1 - prog))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 120, 40, alpha // 2))
        p.drawEllipse(QPointF(exp['x'], exp['y']), r, r)
        p.setBrush(QColor(255, 230, 100, alpha))
        p.drawEllipse(QPointF(exp['x'], exp['y']), r * 0.55, r * 0.55)
        p.setBrush(QColor(255, 255, 220, alpha))
        p.drawEllipse(QPointF(exp['x'], exp['y']), r * 0.25, r * 0.25)

    def _draw_debris(self, p, d):
        alpha = min(255, d['life'] * 6)
        color = QColor(d['color'].red(), d['color'].green(),
                       d['color'].blue(), alpha)
        p.fillRect(int(d['x']), int(d['y']), d['size'], d['size'], color)

    def _draw_place_ring(self, p, r):
        t = r['life'] / 18
        radius = 30 + (1 - t) * (MAX_PLACE_DIST * 0.9)
        alpha = int(160 * t)
        p.setPen(QPen(QColor(255, 255, 180, alpha), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(r['x'], r['y']), radius, radius)

    def _draw_floater(self, p, fl):
        alpha = min(255, int(fl['life'] / 60 * 255))
        r, g, b = fl['color']
        p.setPen(QColor(r, g, b, alpha))
        p.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
        p.drawText(int(fl['x'] - 50), int(fl['y']), 100, 24,
                   Qt.AlignmentFlag.AlignCenter, fl['text'])


# ===================== 桌宠 =====================
class MCPet(QWidget):
    GRID_W, GRID_H, PX, MARGIN = 16, 30, 4, 8

    def __init__(self, char_key, index=0):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._char = char_key
        self._config = CHARACTERS[char_key]
        w = self.GRID_W * self.PX + self.MARGIN * 2
        h = self.GRID_H * self.PX + self.MARGIN * 2
        self.setFixedSize(w, h)
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.right() - w - 40 - index * 90
        y = screen.bottom() - h - 40
        if x < screen.left() + 20:
            x = screen.left() + 20 + (index % 4) * 90
            y -= (index // 4) * 100
        if self._config.get('can_fly'):
            y = screen.top() + 150 + index * 60
        self.move(x, y)
        self._home = self.pos()

        self.max_hp = self._config.get('hp', 20)
        self.hp = self.max_hp
        self._dead = False; self._dead_ticks = 0; self._hit_flash = 0
        self._t = random.randint(0, 100)
        self._bob = 0.0
        self._jump_phase = 0; self._jump_offset = 0.0
        self._blink = False; self._blink_counter = 0; self._blink_duration = 0
        self._eye_shift = 0
        self._dragging = False; self._drag_offset = None
        self._bubble = None
        self._vy = 0
        self._skill_cd = random.randint(80, 200)
        self._breed_cd = 0
        self._fly_target = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)
        self._place_timer = QTimer(self); self._place_timer.setSingleShot(True)
        self._place_timer.timeout.connect(self._place_block)
        self._place_timer.start(random.randint(PLACE_MIN_MS, PLACE_MAX_MS))
        self._say_timer = QTimer(self); self._say_timer.setSingleShot(True)
        self._say_timer.timeout.connect(self._auto_say)
        self._say_timer.start(random.randint(8000, 18000))
        self._water_timer = QTimer(self); self._water_timer.setSingleShot(True)
        self._water_timer.timeout.connect(self._auto_water)
        self._water_timer.start(random.randint(15000, 35000))
        self._spawn_timer = QTimer(self); self._spawn_timer.setSingleShot(True)
        self._spawn_timer.timeout.connect(self._auto_spawn)
        self._spawn_timer.start(random.randint(20000, 45000))

    def _apply_gravity(self):
        if self._dragging or self._dead: return
        if self._config.get('can_fly'):
            self._fly_update()
            return
        screen = QApplication.primaryScreen().availableGeometry()
        pet_bottom = self.y() + self.height()
        if pet_bottom >= screen.bottom() - 3:
            self._vy = 0
            if pet_bottom > screen.bottom():
                self.move(self.x(), screen.bottom() - self.height())
            return
        if CANVAS:
            lx_l = self.x() + 15 - CANVAS._ox
            lx_r = self.x() + self.width() - 15 - CANVAS._ox
            ly_old = pet_bottom - CANVAS._oy
            self._vy = min(self._vy + 1.0, 12)
            new_y = self.y() + self._vy
            ly_new = (new_y + self.height()) - CANVAS._oy
            cy_from = int(ly_old // BS)
            cy_to = int(ly_new // BS)
            for cy in range(cy_from, cy_to + 1):
                for cx in range(int(lx_l // BS), int(lx_r // BS) + 1):
                    if (cx, cy) in CANVAS._occupied:
                        self.move(self.x(), CANVAS._oy + cy * BS - self.height())
                        self._vy = 0; return
            self.move(self.x(), int(new_y))
        else:
            self._vy = min(self._vy + 1.0, 12)
            self.move(self.x(), int(self.y() + self._vy))

    def _fly_update(self):
        if self._dragging: return
        screen = QApplication.primaryScreen().availableGeometry()
        if self._fly_target is None:
            if random.random() < 0.015:
                self._fly_target = (
                    random.randint(screen.left() + 60,
                                   screen.right() - self.width() - 60),
                    random.randint(screen.top() + 80,
                                   screen.bottom() - self.height() - 80),
                )
            return
        tx, ty = self._fly_target
        dx = tx - self.x(); dy = ty - self.y()
        dist = math.hypot(dx, dy)
        if dist < 8:
            self._fly_target = None; return
        step = 2.5
        nx = int(self.x() + dx / dist * step)
        ny = int(self.y() + dy / dist * step)
        nx = max(screen.left(), min(nx, screen.right() - self.width()))
        ny = max(screen.top(), min(ny, screen.bottom() - self.height()))
        self.move(nx, ny)

    def _resolve_collisions(self):
        if self._dead or not self.isVisible(): return
        for other in PETS:
            if other is self or other._dead or not other.isVisible(): continue
            r1x, r1y = self.x() + 15, self.y() + 30
            r1w, r1h = self.width() - 30, self.height() - 40
            r2x, r2y = other.x() + 15, other.y() + 30
            r2w, r2h = other.width() - 30, other.height() - 40
            if (r1x < r2x + r2w and r1x + r1w > r2x and
                    r1y < r2y + r2h and r1y + r1h > r2y):
                dx = (self.x() + self.width() // 2) - (other.x() + other.width() // 2)
                if dx == 0: dx = random.choice([-1, 1])
                push = 4 * (1 if dx > 0 else -1)
                screen = QApplication.primaryScreen().availableGeometry()
                self.move(max(screen.left(),
                              min(self.x() + push, screen.right() - self.width())),
                          self.y())
                other.move(max(screen.left(),
                               min(other.x() - push, screen.right() - other.width())),
                           other.y())

    def _check_breed(self):
        if self._char not in ('chicken', 'cow', 'pig', 'wolf'): return
        if self._breed_cd > 0 or self.hp < self.max_hp * 0.8: return
        if len(PETS) >= MAX_PETS: return
        for other in PETS:
            if (other is self or other._dead or other._char != self._char
                    or other._breed_cd > 0 or other.hp < other.max_hp * 0.8):
                continue
            if math.hypot(other.x() - self.x(), other.y() - self.y()) < 90:
                self._breed_cd = 900; other._breed_cd = 900
                self.hp = max(1, self.hp - 2)
                other.hp = max(1, other.hp - 2)
                mx = (self.x() + other.x()) // 2
                my = (self.y() + other.y()) // 2
                spawn_pet_at(self._char, mx, my)
                if CANVAS:
                    lx, ly = to_logic(mx + 30, my)
                    CANVAS.add_floater(lx, ly - 40, "💕 出生", (255, 150, 200))
                self._say(random.choice(["❤️", "宝贝~", "咕~"]))
                break

    def _tick(self):
        if self._dead:
            self._dead_ticks -= 1
            if self._dead_ticks <= 0: self._respawn()
            return
        if not self.isVisible(): return
        if self._hit_flash > 0: self._hit_flash -= 1
        if self._breed_cd > 0: self._breed_cd -= 1
        self._apply_gravity()
        self._resolve_collisions()
        self._check_breed()
        self._t += 1
        if self._char == 'allay':
            self._bob = math.sin(self._t * 0.10) * 3.5
        else:
            self._bob = math.sin(self._t * 0.12) * 1.5
        if self._jump_phase > 0:
            progress = 1 - (self._jump_phase / 12)
            self._jump_offset = math.sin(progress * math.pi) * 15
            self._jump_phase -= 1
        else: self._jump_offset = 0
        self._blink_counter += 1
        if not self._blink and self._blink_counter > random.randint(80, 160):
            self._blink = True; self._blink_counter = 0
            self._blink_duration = random.randint(4, 8)
        if self._blink:
            self._blink_duration -= 1
            if self._blink_duration <= 0: self._blink = False
        local = self.mapFromGlobal(QCursor.pos())
        dx = local.x() - self.width() / 2
        self._eye_shift = 1 if dx > 20 else (-1 if dx < -20 else 0)
        if self._config.get('skill') == 'explode':
            target, dist = self._find_nearest_target()
            if target and dist is not None and dist < 60 and self._skill_cd > 45:
                self._skill_cd = 30
        self._skill_cd -= 1
        if self._skill_cd <= 0:
            self._use_skill()
            self._skill_cd = random.randint(*self._config.get('cd', (200, 300)))
        self.update()

    def take_damage(self, amount, source=None):
        if self._dead: return
        self.hp -= amount; self._hit_flash = 8
        if CANVAS:
            lx, ly = to_logic(self.x() + self.width() // 2,
                              self.y() + self.height() // 2)
            CANVAS.add_floater(lx, ly - 40, f"-{amount}", (255, 80, 80))
        if self.hp <= 0: self._die()

    def _die(self):
        self._dead = True; self._dead_ticks = 180; self.hide()
        if self._bubble:
            try: self._bubble.close()
            except Exception: pass
        if CANVAS:
            lx, ly = to_logic(self.x() + self.width() // 2,
                              self.y() + self.height() // 2)
            CANVAS.add_floater(lx, ly - 50,
                               f"💀 {self._config['name']} 倒下", (255, 120, 120))

    def _respawn(self):
        self._dead = False; self.hp = self.max_hp
        self._hit_flash = 0; self._vy = 0
        self._fly_target = None
        screen = QApplication.primaryScreen().availableGeometry()
        x = random.randint(screen.left() + 60, screen.right() - self.width() - 60)
        y = random.randint(screen.top() + 60, screen.bottom() - self.height() - 60)
        self.move(x, y)
        if not GLOBALLY_HIDDEN: self.show(); self.raise_()
        self._place_timer.start(random.randint(PLACE_MIN_MS, PLACE_MAX_MS))
        self._say_timer.start(random.randint(8000, 18000))
        self._water_timer.start(random.randint(15000, 35000))
        self._spawn_timer.start(random.randint(20000, 45000))
        if CANVAS:
            lx, ly = to_logic(x + self.width() // 2, y + self.height() // 2)
            CANVAS.add_floater(lx, ly - 40,
                               f"✨ {self._config['name']} 复活", (150, 255, 150))

    def _find_nearest_target(self):
        best, best_d2 = None, float('inf')
        for pet in PETS:
            if pet is self or pet._dead: continue
            d2 = (pet.x() - self.x()) ** 2 + (pet.y() - self.y()) ** 2
            if d2 < best_d2: best_d2, best = d2, pet
        return best, (math.sqrt(best_d2) if best else None)

    def _use_skill(self):
        kind = self._config.get('skill')
        if not kind: return
        fn = getattr(self, f'_skill_{kind}', None)
        if fn: fn()

    def _skill_shoot_arrow(self):
        t, _ = self._find_nearest_target()
        if not t: return
        lx, ly = to_logic(self.x() + self.width() // 2, self.y() + self.height() // 2)
        tlx, tly = to_logic(t.x() + t.width() // 2, t.y() + t.height() // 2)
        dx, dy = tlx - lx, tly - ly; d = math.hypot(dx, dy) or 1
        if CANVAS: CANVAS.add_projectile(lx, ly, dx / d * 9, dy / d * 9, self, 'arrow', 3)
        self._say(random.choice(["瞄准！", "射箭！", "嗖！"]))

    def _skill_explode(self):
        lx, ly = to_logic(self.x() + self.width() // 2, self.y() + self.height() // 2)
        if CANVAS: CANVAS.add_explosion(lx, ly, radius=90, source=self)
        self._say(random.choice(["💥 轰！", "嘶嘶嘶！"]))
        self.take_damage(self.max_hp * 2)

    def _skill_teleport(self):
        screen = QApplication.primaryScreen().availableGeometry()
        if CANVAS:
            lx, ly = to_logic(self.x() + self.width() // 2, self.y() + self.height() // 2)
            CANVAS.add_floater(lx, ly - 40, "✦", (180, 100, 255))
        x = random.randint(screen.left() + 60, screen.right() - self.width() - 60)
        y = random.randint(screen.top() + 60, screen.bottom() - self.height() - 60)
        self.move(x, y); self._vy = 0
        self._say(random.choice(["呜噗", "闪！"]))

    def _skill_crawl(self):
        t, dist = self._find_nearest_target()
        if not t: return
        if dist is not None and dist < 60:
            t.take_damage(2, self)
            self._say("啧啧")
        else: self._move_toward(t, 20)

    def _skill_chase(self):
        t, dist = self._find_nearest_target()
        if not t or dist is None: return
        if dist < 55:
            t.take_damage(2, self)
            self._say(random.choice(["呃啊！", "饿了…", "汪！"]))
        else: self._move_toward(t, 18)

    def _skill_charge(self):
        t, _ = self._find_nearest_target()
        if not t: return
        self._move_toward(t, 25)
        if math.hypot(t.x() - self.x(), t.y() - self.y()) < 70:
            t.take_damage(4, self)
            self._say("哞！")

    def _skill_lightning(self):
        t, _ = self._find_nearest_target()
        if not t: return
        lx, ly = to_logic(t.x() + t.width() // 2, t.y() + t.height() // 2)
        if CANVAS: CANVAS.add_explosion(lx, ly, radius=55, source=self, kind='lightning')
        t.take_damage(6, self)
        self._say("⚡ 轰！")

    def _skill_smash(self):
        t, _ = self._find_nearest_target()
        if not t: return
        self._move_toward(t, 120)
        self._jump()
        lx, ly = to_logic(self.x() + self.width() // 2, self.y() + self.height() // 2)
        if CANVAS:
            CANVAS.add_explosion(lx, ly, radius=45, source=self, kind='slime')
            for p in PETS:
                if p is self or p._dead: continue
                if math.hypot(p.x() - self.x(), p.y() - self.y()) < 85:
                    p.take_damage(3, self)
        self._say(random.choice(["啵！", "啪叽！"]))

    def _skill_heal(self):
        healed = False
        for p in PETS:
            if p._dead: continue
            if p is self or math.hypot(p.x() - self.x(), p.y() - self.y()) < 220:
                if p.hp < p.max_hp:
                    p.hp = min(p.max_hp, p.hp + 5); healed = True
                    if CANVAS:
                        lx, ly = to_logic(p.x() + p.width() // 2, p.y() + p.height() // 2)
                        CANVAS.add_floater(lx, ly - 45, "+5", (100, 255, 100))
        if healed: self._say("交易~")

    def _skill_lay_egg(self):
        if CANVAS:
            lx, ly = to_logic(self.x() + self.width() // 2, self.y() + self.height())
            CANVAS.add_floater(lx, ly - 20, "🥚", (240, 240, 220))
        self._say("咯咯哒！")

    def _skill_sing(self):
        healed_count = 0
        for p in PETS:
            if p._dead: continue
            if p is self or math.hypot(p.x() - self.x(), p.y() - self.y()) < 250:
                if p.hp < p.max_hp:
                    p.hp = min(p.max_hp, p.hp + 4)
                    healed_count += 1
                    if CANVAS:
                        lx, ly = to_logic(p.x() + p.width() // 2,
                                          p.y() + p.height() // 2)
                        CANVAS.add_floater(lx, ly - 45, "+4", (150, 220, 255))
        if CANVAS:
            lx, ly = to_logic(self.x() + self.width() // 2,
                              self.y() + self.height() // 2)
            for _ in range(4):
                CANVAS.add_floater(
                    lx + random.randint(-40, 40),
                    ly - 50 + random.randint(-15, 15),
                    random.choice(["♪", "♫", "♬", "🎵", "🎶"]),
                    (150, 220, 255))
        if healed_count > 0:
            self._say(random.choice(["♪ 治愈了！", "♫ 啦啦~", "🎵 好了哦"]))
        else:
            self._say(random.choice(["♪", "♫", "啦啦~", "🎵"]))

    def _move_toward(self, target, step):
        sx, sy = self.x() + self.width() // 2, self.y() + self.height() // 2
        tx, ty = target.x() + target.width() // 2, target.y() + target.height() // 2
        dx, dy = tx - sx, ty - sy; d = math.hypot(dx, dy) or 1
        step = min(d, step)
        screen = QApplication.primaryScreen().availableGeometry()
        nx = max(screen.left(), min(int(self.x() + dx / d * step),
                 screen.right() - self.width()))
        ny = max(screen.top(), min(int(self.y() + dy / d * step),
                 screen.bottom() - self.height()))
        self.move(nx, ny)

    def _is_overlapping_pet(self, gx, gy):
        for pet in PETS:
            if pet._dead or not pet.isVisible(): continue
            px = pet.x() + 10
            py = pet.y() + 20
            pw = pet.width() - 20
            ph = pet.height() - 25
            if (gx < px + pw and gx + BS > px and
                    gy < py + ph and gy + BS > py):
                return True
        return False

    def _place_block(self):
        if not self._config.get('can_build', False):
            return
        if self._dead or not self.isVisible():
            self._place_timer.start(random.randint(PLACE_MIN_MS, PLACE_MAX_MS))
            return
        if CANVAS:
            cx = self.x() + self.width() // 2
            cy = self.y() + self.height() // 2
            screen = QApplication.primaryScreen().availableGeometry()
            for _ in range(8):
                side = random.choice([-1, 1])
                gx = cx + side * random.randint(50, MAX_PLACE_DIST)
                gy = cy + random.randint(20, 100)
                gx = max(screen.left(), min(gx, screen.right() - BS))
                gy = max(screen.top(),  min(gy, screen.bottom() - BS))
                if abs(gx - cx) > MAX_PLACE_DIST or abs(gy - cy) > MAX_PLACE_DIST:
                    continue
                if self._is_overlapping_pet(gx, gy): continue
                blocks = self._config.get('blocks', ['dirt'])
                kind = random.choice(blocks)
                CANVAS.add_block(gx, gy, kind)
                self._jump()
                lx, ly = to_logic(cx, cy)
                CANVAS.add_place_ring(lx, ly)
                break
        self._place_timer.start(random.randint(PLACE_MIN_MS, PLACE_MAX_MS))

    def _jump(self):
        if self._jump_phase == 0: self._jump_phase = 12

    def _auto_water(self):
        if not self._dead and self.isVisible() and not GLOBALLY_HIDDEN:
            rate = self._config.get('auto_water', 0)
            if rate > 0 and random.random() < rate:
                self._pour_water()
        self._water_timer.start(random.randint(15000, 35000))

    def _auto_spawn(self):
        if not self._dead and self.isVisible() and not GLOBALLY_HIDDEN:
            key = self._config.get('auto_spawn')
            rate = self._config.get('auto_spawn_rate', 0)
            if key and random.random() < rate and len(PETS) < MAX_PETS:
                spawn_pet(key)
        self._spawn_timer.start(random.randint(20000, 45000))

    def _auto_say(self):
        if self._dead or not self.isVisible(): return
        if random.random() < 0.6:
            qs = self._config.get('say', ["..."])
            self._say(random.choice(qs))
        self._say_timer.start(random.randint(12000, 30000))

    def _say(self, text):
        if self._bubble:
            try: self._bubble.close()
            except Exception: pass
        self._bubble = SpeechBubble(text, self)
        self._bubble.show()

    def _pour_water(self):
        if CANVAS and not self._dead:
            gx = self.x() + self.width() // 2
            gy = self.y() + self.height() + 10
            for dx in (-16, 0, 16): CANVAS.add_water(gx + dx, gy)
            self._say(random.choice(["💧 哗啦", "咕噜咕噜"]))

    def _delete_self(self): self.close()

    def closeEvent(self, e):
        for t in (self._timer, self._place_timer, self._say_timer,
                  self._water_timer, self._spawn_timer):
            t.stop()
        if self._bubble:
            try: self._bubble.close()
            except Exception: pass
        if self in PETS: PETS.remove(self)
        super().closeEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self._painter = p
        self._ox = (self.width() - self.GRID_W * self.PX) // 2
        self._oy = (self.height() - self.GRID_H * self.PX) // 2 + \
                   int(self._bob - self._jump_offset)
        fn = self._config['draw']
        if fn == 'humanoid': self._draw_humanoid(self._config['colors'])
        elif fn == 'creeper': self._draw_creeper()
        elif fn == 'enderman': self._draw_enderman()
        elif fn == 'villager': self._draw_villager()
        elif fn == 'quadruped':
            self._draw_quadruped(self._config['colors'], *self._config['size'])
        elif fn == 'slime': self._draw_slime()
        elif fn == 'spider': self._draw_spider(self._config['colors'])
        elif fn == 'allay': self._draw_allay()
        elif fn == 'small_bird': self._draw_chicken(self._config['colors'])
        if self._hit_flash > 0:
            p.fillRect(self._ox, self._oy, self.GRID_W * self.PX, self.GRID_H * self.PX,
                       QColor(255, 30, 30, 80))
        if 0 < self.hp < self.max_hp:
            bx, by = self.MARGIN, 2
            bw = self.width() - self.MARGIN * 2
            p.fillRect(bx, by, bw, 4, QColor(40, 40, 40, 220))
            frac = max(0, self.hp / self.max_hp)
            col = (QColor(90, 200, 90) if frac > 0.5 else
                   QColor(220, 180, 40) if frac > 0.25 else QColor(220, 60, 60))
            p.fillRect(bx, by, int(bw * frac), 4, col)
        p.end()

    def _rect(self, cx, cy, cw, ch, color):
        self._painter.fillRect(self._ox + cx * self.PX, self._oy + cy * self.PX,
                               cw * self.PX, ch * self.PX, color)

    def _draw_humanoid(self, P):
        shoes = P.get('shoes', C(0x202020))
        self._rect(4, 0, 8, 2, P['hair'])
        self._rect(4, 2, 1, 3, P['hair']); self._rect(11, 2, 1, 3, P['hair'])
        self._rect(5, 2, 6, 6, P['skin'])
        if self._blink:
            self._rect(5, 4, 1, 1, P['skin_dark']); self._rect(10, 4, 1, 1, P['skin_dark'])
        else:
            self._rect(5 + self._eye_shift, 4, 1, 1, P['eye'])
            self._rect(10 + self._eye_shift, 4, 1, 1, P['eye'])
        self._rect(7, 5, 2, 1, P['skin_dark']); self._rect(6, 6, 4, 1, P['mouth'])
        self._rect(4, 8, 8, 10, P['shirt'])
        self._rect(4, 8, 1, 10, P['shirt_dark']); self._rect(11, 8, 1, 10, P['shirt_dark'])
        self._rect(0, 8, 4, 4, P['shirt']); self._rect(0, 12, 4, 6, P['skin'])
        self._rect(0, 8, 1, 4, P['shirt_dark'])
        self._rect(12, 8, 4, 4, P['shirt']); self._rect(12, 12, 4, 6, P['skin'])
        self._rect(15, 8, 1, 4, P['shirt_dark'])
        self._rect(4, 18, 4, 9, P['pants']); self._rect(8, 18, 4, 9, P['pants'])
        for x in (4, 7, 8, 11): self._rect(x, 18, 1, 9, P['pants_dark'])
        self._rect(4, 27, 4, 1, shoes); self._rect(8, 27, 4, 1, shoes)

    def _draw_creeper(self):
        b, bd, bl = C(0x4ca04c), C(0x367c36), C(0x68b46c)
        f, s = C(0x101010), C(0x101010, 90)
        self._rect(4, 0, 8, 8, b); self._rect(4, 0, 1, 8, bd); self._rect(11, 0, 1, 8, bd)
        if not self._blink:
            self._rect(5 + self._eye_shift, 2, 2, 2, f); self._rect(9 + self._eye_shift, 2, 2, 2, f)
        else:
            self._rect(5, 2, 2, 1, f); self._rect(9, 2, 2, 1, f)
        self._rect(6, 4, 4, 2, f); self._rect(5, 6, 2, 1, f); self._rect(9, 6, 2, 1, f)
        self._rect(4, 8, 8, 12, b); self._rect(4, 8, 1, 12, bd); self._rect(11, 8, 1, 12, bd)
        self._rect(6, 11, 2, 2, bd); self._rect(9, 14, 2, 2, bl)
        self._rect(4, 20, 3, 8, b); self._rect(9, 20, 3, 8, b)
        self._rect(4, 20, 1, 8, bd); self._rect(9, 20, 1, 8, bd)
        self._rect(4, 28, 3, 1, s); self._rect(9, 28, 3, 1, s)

    def _draw_enderman(self):
        b, bd, e = C(0x141414), C(0x000000), C(0xc040e0)
        self._rect(5, 0, 6, 6, b); self._rect(5, 0, 1, 6, bd); self._rect(10, 0, 1, 6, bd)
        if not self._blink:
            self._rect(6 + self._eye_shift, 2, 2, 1, e); self._rect(9 + self._eye_shift, 2, 2, 1, e)
        else:
            self._rect(6, 3, 2, 1, bd); self._rect(9, 3, 2, 1, bd)
        self._rect(5, 6, 6, 12, b); self._rect(5, 6, 1, 12, bd); self._rect(10, 6, 1, 12, bd)
        self._rect(2, 6, 3, 20, b); self._rect(11, 6, 3, 20, b)
        self._rect(5, 18, 2, 10, b); self._rect(9, 18, 2, 10, b)

    def _draw_villager(self):
        sk, dk = C(0xc8a080), C(0xa07858); br = C(0x8a6040)
        rb, rbd = C(0x6a4028), C(0x503018); e = C(0x1a2a1a)
        self._rect(4, 0, 8, 8, sk)
        if not self._blink:
            self._rect(5 + self._eye_shift, 2, 1, 1, e); self._rect(10 + self._eye_shift, 2, 1, 1, e)
        else:
            self._rect(5, 2, 1, 1, dk); self._rect(10, 2, 1, 1, dk)
        self._rect(5, 1, 6, 1, br); self._rect(7, 3, 2, 3, dk)
        self._rect(4, 8, 8, 14, rb); self._rect(4, 8, 1, 14, rbd); self._rect(11, 8, 1, 14, rbd)
        self._rect(0, 8, 4, 10, sk); self._rect(12, 8, 4, 10, sk)
        self._rect(4, 20, 3, 8, rbd); self._rect(9, 20, 3, 8, rbd)

    def _draw_quadruped(self, P, bw, bh, hx):
        Y = 15
        self._rect(2, 3 + Y, bw - 2, bh - 2, P['body'])
        self._rect(2, 3 + Y, 1, bh - 2, P['body_d'])
        self._rect(bw - 1, 3 + Y, 1, bh - 2, P['body_d'])
        self._rect(1, 1 + Y, hx, hx, P['face'])
        self._rect(1, 1 + Y, 1, hx, P['body_d'])
        self._rect(2, Y, 2, 2, P['face']); self._rect(4, Y, 2, 2, P['face'])
        if not self._blink:
            self._rect(2 + self._eye_shift, 3 + Y, 1, 1, P['eye'])
            self._rect(4 + self._eye_shift, 3 + Y, 1, 1, P['eye'])
        self._rect(2, 5 + Y, 3, 2, P.get('snout', P['body_d']))
        for lx in (3, 6, 9, 12):
            self._rect(lx, 3 + Y + bh - 2, 2, 5, P.get('hoof', P['body_d']))
        self._rect(bw - 1, 3 + Y, 1, 2, P.get('extra', P['body']))

    def _draw_spider(self, P):
        b, bd, bl = P['body'], P['body_d'], P['body_l']
        e, leg = P['eye'], P['leg']
        for i, (lx, ly) in enumerate([(2, 10), (2, 13), (2, 16), (2, 19),
                                       (11, 10), (11, 13), (11, 16), (11, 19)]):
            dx = -1 if lx < 8 else 1
            self._rect(lx + dx * i % 3, ly, 3, 1, leg)
        self._rect(4, 10, 8, 10, b)
        self._rect(4, 10, 1, 10, bd); self._rect(11, 10, 1, 10, bd)
        self._rect(5, 12, 2, 2, bl); self._rect(9, 15, 2, 2, bl)
        self._rect(5, 20, 6, 5, b)
        self._rect(5, 20, 1, 5, bd); self._rect(10, 20, 1, 5, bd)
        if not self._blink:
            for ex in (6, 7, 9, 10): self._rect(ex, 22, 1, 1, e)
        else:
            for ex in (6, 7, 9, 10): self._rect(ex, 22, 1, 1, bd)

    def _draw_allay(self):
        body   = C(0x8fd0e8); body_d = C(0x60a8c8); body_l = C(0xc8ecf8)
        hair   = C(0xd8ecf8); eye = C(0x2a3a8a); eye_hl = C(0xffffff)
        mouth  = C(0x4080b0)
        wing_o = QColor(200, 225, 245, 200); wing_i = QColor(235, 248, 255, 230)

        self._rect(0, 4, 4, 3, wing_o)
        self._rect(0, 7, 4, 3, wing_i)
        self._rect(0, 10, 3, 2, wing_o)
        self._rect(12, 4, 4, 3, wing_o)
        self._rect(12, 7, 4, 3, wing_i)
        self._rect(13, 10, 3, 2, wing_o)

        self._rect(7, 0, 2, 2, hair); self._rect(6, 1, 1, 1, hair)

        self._rect(4, 2, 8, 8, body)
        self._rect(4, 2, 1, 8, body_d); self._rect(11, 2, 1, 8, body_d)
        self._rect(5, 2, 6, 1, body_l)

        if not self._blink:
            self._rect(5 + self._eye_shift, 4, 2, 2, eye)
            self._rect(9 + self._eye_shift, 4, 2, 2, eye)
            self._rect(5 + self._eye_shift, 4, 1, 1, eye_hl)
            self._rect(9 + self._eye_shift, 4, 1, 1, eye_hl)
        else:
            self._rect(5, 5, 2, 1, body_d); self._rect(9, 5, 2, 1, body_d)

        self._rect(7, 7, 2, 1, mouth)

        self._rect(5, 10, 6, 6, body)
        self._rect(5, 10, 1, 6, body_d); self._rect(10, 10, 1, 6, body_d)
        self._rect(6, 11, 4, 1, body_l)

        self._rect(4, 11, 1, 3, body); self._rect(11, 11, 1, 3, body)
        self._rect(6, 16, 2, 3, body_d); self._rect(8, 16, 2, 3, body_d)
        self._rect(6, 19, 2, 1, body); self._rect(8, 19, 2, 1, body)

    def _draw_chicken(self, P):
        Y = 12
        self._rect(4, 6 + Y, 8, 8, P['body'])
        self._rect(4, 6 + Y, 1, 8, P['body_d']); self._rect(11, 6 + Y, 1, 8, P['body_d'])
        self._rect(3, 8 + Y, 1, 4, P['body_d']); self._rect(12, 8 + Y, 1, 4, P['body_d'])
        self._rect(5, 2 + Y, 5, 5, P['body'])
        self._rect(6, 1 + Y, 3, 1, P['comb']); self._rect(7, 0 + Y, 1, 1, P['comb'])
        if not self._blink:
            self._rect(6 + self._eye_shift, 3 + Y, 1, 1, P['eye'])
            self._rect(9 + self._eye_shift, 3 + Y, 1, 1, P['eye'])
        self._rect(10, 4 + Y, 2, 1, P['beak'])
        self._rect(6, 14 + Y, 1, 3, P['foot']); self._rect(9, 14 + Y, 1, 3, P['foot'])
        self._rect(5, 17 + Y, 2, 1, P['foot']); self._rect(9, 17 + Y, 2, 1, P['foot'])

    def _draw_slime(self):
        g, gd, gl = C(0x70c050, 220), C(0x50903c, 220), C(0x90d070, 220)
        blk = C(0x101010)
        self._rect(2, 6, 12, 12, g)
        self._rect(2, 6, 1, 12, gd); self._rect(13, 6, 1, 12, gd)
        self._rect(2, 17, 12, 1, gd)
        self._rect(3, 6, 3, 2, gl); self._rect(4, 7, 1, 1, gl)
        if not self._blink:
            self._rect(5 + self._eye_shift, 9, 2, 2, blk)
            self._rect(9 + self._eye_shift, 9, 2, 2, blk)
        else:
            self._rect(5, 10, 2, 1, blk); self._rect(9, 10, 2, 1, blk)
        self._rect(6, 12, 4, 1, blk)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e):
        if self._dragging and self._drag_offset is not None:
            self.move(e.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = False; self._drag_offset = None; self._vy = 0

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self._dead:
            self._jump()
            self._say(random.choice(self._config.get('say', ["..."])))

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#2b2b2b; color:#eee; border:1px solid #555; padding:4px; }"
            "QMenu::item { padding:6px 24px; border-radius:3px; }"
            "QMenu::item:selected { background:#4a90d9; color:white; }"
            "QMenu::separator { height:1px; background:#555; margin:4px 8px; }")
        spawn = menu.addMenu("✨ 召唤角色")
        for key, cfg in CHARACTERS.items():
            spawn.addAction(cfg['name'], lambda k=key: spawn_pet(k))
        menu.addSeparator()
        menu.addAction("💧 放水", self._pour_water)
        menu.addAction("💬 说句话",
                       lambda: self._say(random.choice(self._config.get('say', ['...']))))
        menu.addAction("🏠 回到原位",
                       lambda: (self.move(self._home), setattr(self, '_vy', 0)))
        menu.addSeparator()
        menu.addAction("👁 隐遁全部 (Ctrl+Shift+H)", toggle_hide_all)
        menu.addAction("🗑 删除这个角色", self._delete_self)
        menu.addAction("🧹 清空方块", clear_all_blocks)
        menu.addSeparator()
        menu.addAction("❌ 退出全部", QApplication.instance().quit)
        menu.exec(e.globalPos())


def spawn_pet(char_key):
    if len(PETS) >= MAX_PETS: return
    pet = MCPet(char_key, index=len(PETS))
    if not GLOBALLY_HIDDEN: pet.show(); pet.raise_()
    PETS.append(pet)


def spawn_pet_at(char_key, x, y):
    if len(PETS) >= MAX_PETS: return
    pet = MCPet(char_key, index=len(PETS))
    pet.move(x, y)
    if not GLOBALLY_HIDDEN: pet.show(); pet.raise_()
    PETS.append(pet)


def toggle_hide_all():
    global GLOBALLY_HIDDEN
    GLOBALLY_HIDDEN = not GLOBALLY_HIDDEN
    if CANVAS:
        if GLOBALLY_HIDDEN: CANVAS.hide()
        else: CANVAS.show()
    for pet in PETS:
        if GLOBALLY_HIDDEN:
            pet.hide()
            if pet._bubble:
                try: pet._bubble.close()
                except Exception: pass
        else:
            if not pet._dead: pet.show(); pet.raise_()
    if TRAY:
        TRAY.setToolTip("MC 桌宠 — " + ("已隐藏" if GLOBALLY_HIDDEN else "显示中"))


def clear_all_blocks():
    if CANVAS: CANVAS.clear_all()


def setup_tray(app):
    global TRAY
    pm = QPixmap(32, 32); pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.fillRect(4, 4, 24, 24, QColor(0x4c, 0xa0, 0x4c))
    p.fillRect(4, 4, 1, 24, QColor(0x36, 0x7c, 0x36))
    p.fillRect(27, 4, 1, 24, QColor(0x36, 0x7c, 0x36))
    p.fillRect(8, 10, 4, 4, QColor(0x10, 0x10, 0x10))
    p.fillRect(20, 10, 4, 4, QColor(0x10, 0x10, 0x10))
    p.fillRect(10, 18, 12, 4, QColor(0x10, 0x10, 0x10))
    p.fillRect(12, 20, 2, 2, QColor(0x10, 0x10, 0x10))
    p.fillRect(18, 20, 2, 2, QColor(0x10, 0x10, 0x10))
    p.end()
    icon = QIcon(pm)
    TRAY = QSystemTrayIcon(icon, app)
    TRAY.setToolTip("MC 桌宠 — 显示中")
    menu = QMenu()
    menu.setStyleSheet(
        "QMenu { background:#2b2b2b; color:#eee; border:1px solid #555; padding:4px; }"
        "QMenu::item { padding:6px 24px; border-radius:3px; }"
        "QMenu::item:selected { background:#4a90d9; color:white; }"
        "QMenu::separator { height:1px; background:#555; margin:4px 8px; }")
    menu.addAction("👁 显隐全部 (Ctrl+Shift+H)", toggle_hide_all)

    time_menu = menu.addMenu("🌗 时间")
    time_menu.addAction("☀ 白天", lambda: CANVAS.set_day_phase(0.0))
    time_menu.addAction("🌗 黄昏", lambda: CANVAS.set_day_phase(0.25))
    time_menu.addAction("🌙 夜晚", lambda: CANVAS.set_day_phase(0.5))
    time_menu.addAction("🌅 黎明", lambda: CANVAS.set_day_phase(0.75))

    menu.addAction("🧹 清空方块", clear_all_blocks)
    menu.addSeparator()
    menu.addAction("❌ 退出", app.quit)
    TRAY.setContextMenu(menu)
    TRAY.show()


def setup_hotkey():
    if not HAS_KEYBOARD:
        print("提示：pip install keyboard 后可启用全局热键 Ctrl+Shift+H")
        return
    try:
        keyboard.add_hotkey('ctrl+shift+h',
                            lambda: QTimer.singleShot(0, toggle_hide_all))
        print("全局热键已启用：Ctrl+Shift+H 显隐桌宠")
    except Exception as e:
        print(f"热键注册失败（可能需要管理员权限）: {e}")


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    global CANVAS
    CANVAS = BlockCanvas(); CANVAS.show()
    setup_tray(app)
    setup_hotkey()

    args = sys.argv[1:]
    chars = []
    if not args:
        chars = [random.choice(['steve', 'alex', 'creeper'])]
    elif args[0].lower() == 'random':
        n = int(args[1]) if len(args) > 1 else 3
        chars = [random.choice(list(CHARACTERS.keys()))
                 for _ in range(min(n, MAX_PETS))]
    else:
        for a in args:
            if a.lower() in CHARACTERS: chars.append(a.lower())
    if not chars: chars = ['steve']
    chars = chars[:MAX_PETS]

    for i, key in enumerate(chars):
        pet = MCPet(key, index=i); pet.show(); PETS.append(pet)

    print("桌宠已启动！托盘图标在右下角。")

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
