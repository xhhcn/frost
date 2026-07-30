#!/usr/bin/env python3
"""
Frost 壁纸生成器 —— 参数化的日落山谷场景
========================================
一个 `scene()` 函数按「时刻」生成整张 SVG：换调色板就是换时段。
纯 SVG，每张几 KB；配合 daylight.py 的定时器可做成随时间变化的动态壁纸。

单独成文件而不是塞进 build-theme.py：壁纸是「内容」，主题 SVG 是「构件」，
两者改动频率和关注点都不一样。
"""

# ── 各时段调色板 ──
# 每个时段给一组颜色，场景结构完全相同，只换颜色 → 视觉上是同一个地方的不同时刻。
PALETTES = {
    "dawn": dict(   # 黎明：冷蓝转桃粉，太阳刚探头
        sky_top="#1b2a4a", sky_mid="#6b5a86", sky_low="#e8927c", sky_bot="#f6c9a0",
        sun="#ffd9a8", sun_glow="#ff9e6d", sun_y=0.415, sun_r=0.030,
        ridge=["#2b3a5c", "#3b4a6b", "#4a5570", "#59607a"],
        water_top="#8fa3c4", water_bot="#3d4a6b", reflect="#ffc9a0",
        haze="#ffb894",
    ),
    "day": dict(    # 白天：清透蓝，太阳高
        sky_top="#1e4e7a", sky_mid="#3b86b5", sky_low="#7fc0d8", sky_bot="#c8e6ee",
        sun="#ffffff", sun_glow="#ffe9b0", sun_y=0.22, sun_r=0.024,
        ridge=["#2e5570", "#3d6880", "#4d7a90", "#5f8ba0"],
        water_top="#9fd0e0", water_bot="#3f6a86", reflect="#ffffff",
        haze="#bfe2ec",
    ),
    "dusk": dict(   # 黄昏：暖橙金 —— 参考图那种气氛
        sky_top="#2b1b3d", sky_mid="#7a3f63", sky_low="#e0703f", sky_bot="#f6b45c",
        sun="#ffe3a3", sun_glow="#ff8c42", sun_y=0.395, sun_r=0.036,
        ridge=["#3a2740", "#4d3049", "#5e3a4e", "#6f4553"],
        water_top="#c98a5e", water_bot="#4a3350", reflect="#ffc46b",
        haze="#ff9d5c",
    ),
    # ── 登录界面专用：中性过渡色 ──
    # 登录壁纸是系统级设置（/var/lib/plasmalogin，root 所有），
    # 没法跟着时段自动切。但**构图可以保持完全一致** ——
    # 只要山、水、树的位置不动，眼睛就把它当同一个地方，
    # 进入桌面后的颜色变化会读成「光线变了」，而不是「换了张图」。
    #
    # 配色刻意坐落在四个时段之间：低饱和的暮蓝灰，
    # 无论下一张是 dawn（暖）/ day（亮）/ dusk（暖）/ night（暗），
    # 过渡幅度都不大。
    # 同时刻意压暗、压低对比 —— 登录界面上面要叠头像、用户名、密码框。
    "login": dict(
        sky_top="#141c28", sky_mid="#26313f", sky_low="#3a4655", sky_bot="#4e5a68",
        sun="#8fa0b4", sun_glow="#5d6e82", sun_y=0.40, sun_r=0.022,
        ridge=["#1b2430", "#222c39", "#2a3441", "#323d4a"],
        water_top="#41505f", water_bot="#1b2430", reflect="#93a4b8",
        haze="#41505f",
        sun_disc=False,   # 见 scene() 里的说明
    ),
    "night": dict(  # 夜：深蓝，月亮小而冷
        sky_top="#080d18", sky_mid="#111c31", sky_low="#1c2c45", sky_bot="#2a3d55",
        sun="#dfe8f5", sun_glow="#8fa8c8", sun_y=0.20, sun_r=0.016,
        ridge=["#0d1420", "#131c2b", "#1a2435", "#212d40"],
        water_top="#24344c", water_bot="#0d1420", reflect="#c8d8ee",
        haze="#25405e",
    ),
}


def _ridge(y_base, amp, seed, w, h, color, opacity=1.0):
    """一条山脊。用多段贝塞尔堆出高低不等的峰，避免「丘陵」感。
    seed 让每层的峰错开，不然层层对齐会很假。"""
    import math
    def Y(f):
        return y_base * h + amp * h * f
    # 每层用不同的相位和峰高，制造错落
    ph = seed * 0.37
    k  = lambda i: math.sin((i + ph) * 2.4) * 0.5 + math.sin((i + ph) * 1.1) * 0.5
    pts = []
    n = 7
    for i in range(n + 1):
        x = -0.02 + (1.04 / n) * i
        pts.append((x * w, Y(k(i))))
    d = f'M {pts[0][0]:.0f},{pts[0][1]:.0f} '
    for i in range(1, len(pts)):
        x0, y0 = pts[i - 1]; x1, y1 = pts[i]
        cx = (x0 + x1) / 2
        d += f'C {cx:.0f},{y0:.0f} {cx:.0f},{y1:.0f} {x1:.0f},{y1:.0f} '
    d += f'L {w*1.02:.0f},{h:.0f} L {-w*0.02:.0f},{h:.0f} Z'
    return f'  <path fill="{color}" opacity="{opacity}" d="{d}"/>\n'


def scene(when="dusk", w=3840, h=2400):
    """生成一张场景壁纸。when ∈ dawn/day/dusk/night。"""
    p = PALETTES[when]
    sun_x, sun_y = 0.68 * w, p["sun_y"] * h
    sun_r = p["sun_r"] * min(w, h) * 2.2
    horizon = 0.70                       # 水平线位置（山与水的分界）

    s = f'<?xml version="1.0" encoding="UTF-8"?>\n'
    s += f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'
    s += '  <defs>\n'
    s += (f'    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">\n'
          f'      <stop offset="0"    stop-color="{p["sky_top"]}"/>\n'
          f'      <stop offset="0.38" stop-color="{p["sky_mid"]}"/>\n'
          f'      <stop offset="0.62" stop-color="{p["sky_low"]}"/>\n'
          f'      <stop offset="0.78" stop-color="{p["sky_bot"]}"/>\n'
          f'    </linearGradient>\n')
    # 太阳光晕：让天空在太阳附近更亮，是整张图的光源
    s += (f'    <radialGradient id="sunglow" cx="{sun_x/w:.3f}" cy="{sun_y/h:.3f}" r="0.55">\n'
          f'      <stop offset="0"    stop-color="{p["sun_glow"]}" stop-opacity="0.75"/>\n'
          f'      <stop offset="0.30" stop-color="{p["sun_glow"]}" stop-opacity="0.28"/>\n'
          f'      <stop offset="1"    stop-color="{p["sun_glow"]}" stop-opacity="0"/>\n'
          f'    </radialGradient>\n')
    # 大气雾：贴着水平线的一层薄雾，把远山推远
    s += (f'    <linearGradient id="haze" x1="0" y1="0" x2="0" y2="1">\n'
          f'      <stop offset="0" stop-color="{p["haze"]}" stop-opacity="0"/>\n'
          f'      <stop offset="1" stop-color="{p["haze"]}" stop-opacity="0.55"/>\n'
          f'    </linearGradient>\n')
    s += (f'    <linearGradient id="water" x1="0" y1="0" x2="0" y2="1">\n'
          f'      <stop offset="0" stop-color="{p["water_top"]}"/>\n'
          f'      <stop offset="1" stop-color="{p["water_bot"]}"/>\n'
          f'    </linearGradient>\n')
    # 水面反光柱：太阳在水里的倒影
    s += (f'    <linearGradient id="reflect" x1="0" y1="0" x2="0" y2="1">\n'
          f'      <stop offset="0"   stop-color="{p["reflect"]}" stop-opacity="0.55"/>\n'
          f'      <stop offset="0.5" stop-color="{p["reflect"]}" stop-opacity="0.18"/>\n'
          f'      <stop offset="1"   stop-color="{p["reflect"]}" stop-opacity="0"/>\n'
          f'    </linearGradient>\n')
    # 上下暗角：面板坐落的区域压暗。
    # 这是解决「透明面板没有确定背景色」的关键 ——
    # 强调色从壁纸取，面板又透出壁纸，两者同源必然低对比。
    # 把面板所在的上下两条带子压暗，面板/图标/指示条就都有稳定的对比底。
    # macOS 在菜单栏后面做的是同一件事。
    s += (f'    <linearGradient id="vigTop" x1="0" y1="0" x2="0" y2="1">\n'
          f'      <stop offset="0"    stop-color="#000000" stop-opacity="0.42"/>\n'
          f'      <stop offset="0.55" stop-color="#000000" stop-opacity="0.14"/>\n'
          f'      <stop offset="1"    stop-color="#000000" stop-opacity="0"/>\n'
          f'    </linearGradient>\n')
    s += (f'    <linearGradient id="vigBot" x1="0" y1="1" x2="0" y2="0">\n'
          f'      <stop offset="0"    stop-color="#000000" stop-opacity="0.46"/>\n'
          f'      <stop offset="0.55" stop-color="#000000" stop-opacity="0.16"/>\n'
          f'      <stop offset="1"    stop-color="#000000" stop-opacity="0"/>\n'
          f'    </linearGradient>\n')
    s += '  </defs>\n\n'

    # 天空
    s += f'  <rect width="{w}" height="{h}" fill="url(#sky)"/>\n'
    s += f'  <rect width="{w}" height="{h}" fill="url(#sunglow)"/>\n'

    # 太阳 / 月亮。
    # 登录图（sun_disc=False）刻意不画盘子：启动画面是在登录图和当前时段图
    # 之间做交叉淡入，两张图的山脊、湖面、松树逐像素重合，唯独日月高度
    # 各时段不同（day 0.22 / dusk 0.395）。留着盘子，淡入时就会看到
    # 一个太阳在另一处慢慢浮出，像重影。只留光晕的话，
    # 淡入读起来是「太阳从雾里显出来」—— 本来就是自然现象。
    if p.get("sun_disc", True):
        s += (f'  <circle cx="{sun_x:.0f}" cy="{sun_y:.0f}" r="{sun_r:.0f}" '
              f'fill="{p["sun"]}" opacity="0.95"/>\n')

    # 远山→近山，四层，越近越暗、越低
    for i, col in enumerate(p["ridge"]):
        s += _ridge(y_base=0.44 + i * 0.058, amp=0.105 - i * 0.021,
                    seed=i * 3 + 1, w=w, h=h, color=col, opacity=1.0)

    # 贴水平线的雾（压在山上，制造纵深）
    s += (f'  <rect x="0" y="{horizon*h - 0.16*h:.0f}" width="{w}" height="{0.16*h:.0f}" '
          f'fill="url(#haze)"/>\n')

    # 水面
    s += f'  <rect x="0" y="{horizon*h:.0f}" width="{w}" height="{h - horizon*h:.0f}" fill="url(#water)"/>\n'
    # 太阳倒影：一堆长度递减、间距递增的横线。
    # 硬边矩形一眼假，横线堆叠才像水面把光打散。
    import random
    rng = random.Random(7)          # 固定种子，保证每次生成完全一样
    wy = horizon * h
    rows = 26
    for i in range(rows):
        t   = i / rows                       # 0=近水平线 1=近底部
        yy  = wy + (h - wy) * (t ** 1.25)
        wid = sun_r * 3.0 * (1 - t * 0.65) * rng.uniform(0.55, 1.25)
        off = rng.uniform(-1, 1) * sun_r * 0.5 * t
        op  = 0.50 * (1 - t) ** 1.6
        thick = max(2, (h - wy) * 0.006 * (0.6 + t))
        s += (f'  <rect x="{sun_x + off - wid/2:.0f}" y="{yy:.0f}" '
              f'width="{wid:.0f}" height="{thick:.0f}" rx="{thick/2:.1f}" '
              f'fill="{p["reflect"]}" opacity="{op:.3f}"/>\n')

    # 前景：一侧的针叶树剪影，给画面一个近景锚点
    fg = p["ridge"][-1]
    for tx, th_, op in [(0.045, 0.20, 1.0), (0.085, 0.15, 0.95),
                        (0.955, 0.17, 1.0), (0.915, 0.12, 0.95)]:
        bx, by = tx * w, h * 0.995
        tw = th_ * h * 0.30
        d = f'M {bx:.0f},{by:.0f} '
        layers = 6
        for L in range(layers):
            f0 = L / layers
            yy = by - th_ * h * (0.15 + f0 * 0.85)
            ww = tw * (1 - f0 * 0.78)
            d += f'L {bx - ww:.0f},{yy + th_*h*0.10:.0f} L {bx - ww*0.55:.0f},{yy:.0f} '
        d += f'L {bx:.0f},{by - th_*h:.0f} '
        for L in range(layers - 1, -1, -1):
            f0 = L / layers
            yy = by - th_ * h * (0.15 + f0 * 0.85)
            ww = tw * (1 - f0 * 0.78)
            d += f'L {bx + ww*0.55:.0f},{yy:.0f} L {bx + ww:.0f},{yy + th_*h*0.10:.0f} '
        d += 'Z'
        s += f'  <path d="{d}" fill="{fg}" opacity="{op}"/>\n'

    # 暗角画在最上层，压住所有内容
    s += f'  <rect x="0" y="0" width="{w}" height="{h*0.085:.0f}" fill="url(#vigTop)"/>\n'
    s += f'  <rect x="0" y="{h*0.905:.0f}" width="{w}" height="{h*0.095:.0f}" fill="url(#vigBot)"/>\n'

    s += '</svg>\n'
    return s


if __name__ == "__main__":
    import sys, os
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    for k in PALETTES:
        p = os.path.join(out, f"scene-{k}.svg")
        open(p, "w").write(scene(k))
        print(f"  {p}  {os.path.getsize(p)} 字节")
