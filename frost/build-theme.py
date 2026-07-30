#!/usr/bin/env python3
"""
Frost — 简约毛玻璃 Plasma 主题生成器
=====================================
改下面的设计变量，重跑本脚本，整套 SVG 重新生成。
    python3 build-theme.py && bash install-frost.sh

SVG 画布分三个区域（互不重叠，便于预览与调试）：
    第 1 行  形状九宫格   topleft / top / ... / center
    第 2 行  模糊遮罩     mask-*
    第 3 行  边距提示     hint-*-margin / hint-*-inset
Plasma 按元素 ID 单独渲染，区域划分只是为了人眼可读。
"""
import ast, collections, json, os, shutil, sys, textwrap

# ─────────────────────────── 设计变量 ───────────────────────────
NAME   = "Frost"
AUTHOR = "xhhcn"
# 版本号只在这里定义。package-frost.sh 的 VER 是从 look-and-feel 的
# metadata.json 里读回来的（不是自己写一份），所以改这一处就够。
VERSION = "1.0"

# ── 各时段的强调色 ──
# 规则：**强调色 = 该场景光源的颜色**（太阳 / 月亮）。
# 壁纸按时段切换时，强调色一起换 —— 黄昏的暖橙场景配暖金强调色，
# 夜里的冷月场景配冰蓝，视觉上是同一束光在照 UI 和风景。
#
# 每个值都实测过对该时段面板底的对比度（面板底 = 壁纸 + 0.22 玻璃 + 暗角）：
#   dawn 7.65:1 · day 6.34:1 · dusk 8.47:1 · night 12.82:1  全部 ≥4.5
#
# 不能沿用「跟随壁纸自动取色」—— 那会取到和面板同源的颜色，实测只有 1.42:1。
SCENE_ACCENTS = {
    "dawn":  (255, 179, 122),   # 柔桃，呼应日出的暖光
    "day":   (104, 203, 223),   # 天青，取自正午天空（190°）
    "dusk":  (245, 185,  66),   # 暖金，呼应落日
    "night": (152, 173, 230),   # 夜靛，取自夜空而非月亮本体（224°）
}
DEFAULT_ACCENT = SCENE_ACCENTS["dusk"]

# 壁纸包的 Description（系统设置 → 壁纸 里的副标题）。英文，同 metadata 规矩。
# 描述的是画面本身，不是「几点钟」—— 用户可能手工选一张固定用，
# 那时「dawn」只是个画面名字，说「早上用」会误导。
SCENE_BLURB = {
    "dawn":  "Valley at first light — peach sky over a still lake.",
    "day":   "Valley at noon — clear sky, sunlit water.",
    "dusk":  "Valley at sunset — warm gold on the ridgeline.",
    "night": "Valley after dark — indigo sky, moonlit water.",
    "login": "Neutral dusk valley, matched to the login screen.",
}

# ── 圆角：只有两档，按「容器」和「元素」分 ──
# 曾经散着 10 / 9 / 7 / 7 四个值，同屏能看到三种圆角（面板、任务项、列表行），
# 读起来是散的。统一成一套两档的尺度：
RADIUS_LG = 10   # 容器级：面板、弹窗、对话框、工具提示。和 Darkly 的
                 # CornerRadius 保持一致（darklyrc [Common] CornerRadius=10），
                 # 这样面板圆角和应用窗口圆角是同一个值。
RADIUS_SM = 7    # 元素级：列表行、任务项。比容器小，形成层级。

RADIUS = RADIUS_LG   # nine_slice 的默认值
TILE   = 32      # 九宫格中心块边长

# ★ 面板厚度：布局模板与 tweak.py 必须写同一个值 ★
# 固定像素而不是 gridUnit 比例 —— tweak.py 写的就是固定 px，
# 换台机器 gridUnit 一变，比例算出来的初值就会和它对不上。
# 曾经的缺陷：布局模板写 round(gridUnit*2.6)=47，tweak.py 写 60，
# 两条入口给出不同的 dock 厚度（详见 layout_js() 里那段注释）。
# 这两个数字与 tweak.py 的 TOP_THICKNESS / BOTTOM_THICKNESS 是同一份真值。
TOP_THICKNESS    = 34   # 顶栏：Arch 徽标 + 时钟 + 托盘，要细
BOTTOM_THICKNESS = 60   # 底部 dock：只放应用图标，要能容纳 49px 图标
MARGIN = 9       # 内容边距
                 # ★ 必须 ≈ RADIUS ★
                 # 边距远小于圆角时，内容会顶进圆弧区域，边上留出难看的空隙。
                 # Breeze 是 圆角 6 / 边距 4（比值 0.67，因为弧线很浅）；
                 # 圆角一旦加大，边距必须同步跟上，否则弧线和内容打架。
                 # 早先 圆角12 / 边距6 就是这个毛病。

# 玻璃通透度 —— 越小越透明。
# 真正的毛玻璃靠「极低色彩覆盖 + KWin 背景模糊」，不是靠深色半透明板。
# 覆盖率太高会变成「有色玻璃」，模糊效果就看不出来了。
# 参考主题（ddh4r4m/Arch）实测值：面板 0.2057 / 弹窗 0.3505
#                                 工具提示 0.2010 / 对话框 0.2733
# 这里贴着它取，只把工具提示抬高一点 —— KWin 6.7 已经没有背景对比特效，
# 工具提示面积小、停留短，太透会读不清。
GLASS_PANEL   = 0.22   # 底部任务栏
GLASS_POPUP   = 0.35   # 系统托盘弹窗、日历、小组件
GLASS_TOOLTIP = 0.28   # 工具提示
GLASS_DIALOG  = 0.28   # KRunner / 通知

# ── 弹窗投影 ──
# 为什么需要：实测 Frost 的 18 个 desktoptheme SVG 里 shadow-* 元素**一个都没有**
# （Breeze 的 dialogs/background.svgz 有 20 片）。libPlasmaQuick 按名字读 12 片喂给
# KWindowShadow，缺片 = 空 tile = 不下发 org_kde_kwin_shadow = 无投影。
# 后果实测：Kickoff 边界对比中位 1.026:1 —— 弹窗此刻既无边框（见 #33 把
# horizontal-line 设成 0）、又无阴影、还半透明（透出 65–72% 背景），
# 三条分离手段一条不剩，读起来就是糊在壁纸上的一块色斑。
#
# SHADOW_MARGIN 取 RADIUS_LG 而不是 Breeze 的 10（数值恰好相同，但理由不同）：
# 让阴影外扩量与容器圆角同量，角部阴影弧与边框圆角弧近似同心，不会看出两套半径。
#
# SHADOW_ALPHA 不能照抄 Breeze 的 0.20 —— 两个原因：
#   1) Breeze 弹窗近乎不透明，靠自身底色就能与背景分离；Frost 透出 65–72%，
#      需要更强的边界信号。
#   2) 黑色阴影在深色壁纸上几乎无效，而 night 占全天 53%。
# 按四时段壁纸在典型弹窗落点的实测均值（dawn L=.100 / day .266 / dusk .083 /
# night .058）推导边界对比（合成在 sRGB 空间，new = bg*(1-a)）：
#     alpha 0.20 → night 1.234 / day 1.475     太弱
#     alpha 0.40 → night 1.499 / day 2.260     ← 取这个
#     alpha 0.55 → night 1.702 / day 3.150     day 已变成可见暗环
SHADOW_MARGIN = RADIUS_LG
SHADOW_ALPHA  = 0.40
# ★ 0.40 是**声明值**，任何像素都渲染不到它 —— 实际峰值 0.3686 ★
# 梯度里 0.40 那个 stop 落在 offset 0.5500，对应片内第 11px 的**边界**
# （y=169.0），而像素中心在半整数位（168.5），落在 offset 0.5750，
# 在 (0.55, 0.40)→(0.70, 0.20) 之间插值 = 0.3686。
# 实测剖面（rsvg-convert 1:1 88x232，shadow-top 片 y=160..179，
#           框体边缘 y=170，窗口在下方）：
#   y=170..179 → 0.0000（框体内严格 0，约束② 成立）
#   y=169 → 0.2000（1px 软起坡）   y=168 → 0.3686（峰值）
#   y=160 → 0.0078（片外沿）        全程单调，shadow-bottom 完全镜像
#
# ★ 不要为了「让 0.40 落地」去改几何 ★ 一次审计提议这么做，
# 理由是「night 边界对比 1.456 掉出 1.5 下沿」。那个判据是张冠李戴的：
# README 里的 1.5 说的是**任务指示条进度填充对面板**（两个 UI 表面之间
# 「可辨但不抢戏」的下沿），不是阴影对壁纸。
# 而且提到 0.40 也救不了 —— 实测四时段托盘弹窗落区（1920x1200 逐像素
# 在 **sRGB 空间**叠黑再取亮度，见下面那条关于合成模型的警告）：
#   scene  壁纸 L    @0.3686   @0.40
#   night  0.0396    1.337:1   1.366:1
#   dusk   0.0502    1.411:1   1.448:1
#   dawn   0.0636    1.490:1   1.537:1
#   day    0.1907    1.962:1   2.083:1
# 提 alpha 只换来 +0.03~+0.12，而 night 要达 1.5 得把 alpha 推到 0.5 以上。
#
# ★ 算这类数字时的合成模型必须是 sRGB 空间 ★
# 叠黑是 result_sRGB = base_sRGB x (1-alpha)，**不是** L' = L x (1-alpha)。
# 伽马让前者暗得多。我第一次用后者算，得出 night 1.194，偏低 0.14；
# 校准办法很简单：拿一个已知实测值反推 —— 图标字形 alpha=0.70 实测
# 5.60/6.21/6.47（night/day/dusk），线性模型给 2.67，sRGB 模型给
# 5.60/6.20/6.42，逐位吻合。**先用已知值校准模型，再拿它算新东西。**
# 根因是**用错了尺子**：WCAG 的 +0.05 眩光项让暗背景上的比值压向 1.0，
# 它是为「文字可读性」设计的，不适用于深度线索。
# 正确的尺子是 Weber 对比 ΔL/L —— 而它恰好**就等于 alpha**：0.369，
# 是低亮度可分辨阈（~0.05–0.10）的 3.7–7.4 倍，阴影清楚可见。
# 所以 0.3686 是够的，保持不动；这几行是为了下次别再被那个 1.5 带跑。

EDGE_ALPHA = 0.0
# 顶部 1px 高光线 —— 已关闭。
#
# 原意是「勾出玻璃厚度」，但实测是负效果：
#   面板上方壁纸 亮度 13.1 → 高光线 62.6 → 面板本体 18.0
#   高光线比面板本体亮 3.5 倍，和面板的对比度只有 1.77:1 ——
#   低到不像有意为之的描边，高到无法忽略，正好落在最难看的区间。
#
# 更根本的原因：**边缘高光是「亮色玻璃」的语言**（iOS/macOS 浅色毛玻璃靠它
# 表现厚度）。深色半透明面板上，一条亮线只会读成硬邦邦的接缝/边框。
# 深色玻璃表达厚度应该靠「边缘更暗」而不是「边缘更亮」。
#
# 留着这个变量而不是删掉代码：想做浅色变体时可以调回 0.1~0.2。

# SVG 样式表里 .ColorScheme-* 的**回退色**。
# 正常情况下 Plasma 渲染时会全部替换掉，只有在没被注入配色时才会用到 ——
# 但仍必须和主题保持一致：早先这里的 hl/focus 是 4dd0c0（早已废弃的青色），
# 和四个时段的强调色没有任何关系，一旦回退就露馅。
# 现在对齐到 DEFAULT_ACCENT（dusk 暖金），并补上 neutral ——
# tasks.svg 的 attention 态用 .ColorScheme-NeutralText，
# 先前样式表里根本没声明这个类，那一态等于没有回退色。
def _hx(rgb):
    """'32,36,42' → '20242a'。让回退色板和 P 同源，避免两处各写一遍。"""
    return "".join(f"{int(v):02x}" for v in rgb.split(","))


def _dark_palette():
    """SVG 样式表里 .ColorScheme-* 的回退色，全部从 P 和 DEFAULT_ACCENT 推导。

    早先是手写的一组字面量，和 P 四对值全对不上（bg 22262b vs P 的 20242a…），
    hl/focus 还写死成 f5b942、不跟着 DEFAULT_ACCENT 走。
    回退色只在「没被注入配色」时才会用到，平时看不见 ——
    正因为看不见，两处分头维护必然漂移。
    """
    acc = "%02x%02x%02x" % DEFAULT_ACCENT
    lighter = "%02x%02x%02x" % tuple(min(255, int(v * 1.18)) for v in DEFAULT_ACCENT)
    return dict(
        bg=_hx(P["window"]), fg=_hx(P["text"]), btn=_hx(P["button"]),
        view_bg=_hx(P["view"]), view_fg=_hx(P["text"]),
        hl=acc, focus=acc, hover=lighter,
        neutral=_hx(P["neutral"]),
    )

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
GAP = 8                # 区域之间的留白

# ─────────────────────────── SVG 构件 ───────────────────────────
# Plasma 渲染 SVG 时会用当前配色替换这些 class 的 color 值。
# 全套 11 个角色都声明，缺哪个 Plasma 就用不上对应的自动着色。
STYLE = """  <defs>
    <style type="text/css" id="current-color-scheme">
      .ColorScheme-Text             {{ color:#{fg};      stop-color:#{fg}; }}
      .ColorScheme-Background       {{ color:#{bg};      stop-color:#{bg}; }}
      .ColorScheme-Highlight        {{ color:#{hl};      stop-color:#{hl}; }}
      .ColorScheme-ViewText         {{ color:#{view_fg}; stop-color:#{view_fg}; }}
      .ColorScheme-ViewBackground   {{ color:#{view_bg}; stop-color:#{view_bg}; }}
      .ColorScheme-ViewHover        {{ color:#{hover};   stop-color:#{hover}; }}
      .ColorScheme-ViewFocus        {{ color:#{focus};   stop-color:#{focus}; }}
      .ColorScheme-ButtonText       {{ color:#{fg};      stop-color:#{fg}; }}
      .ColorScheme-ButtonBackground {{ color:#{btn};     stop-color:#{btn}; }}
      .ColorScheme-ButtonHover      {{ color:#{hover};   stop-color:#{hover}; }}
      .ColorScheme-ButtonFocus      {{ color:#{focus};   stop-color:#{focus}; }}
      .ColorScheme-NeutralText      {{ color:#{neutral}; stop-color:#{neutral}; }}
    </style>
  </defs>
"""

CORNER_NAME = {"tl": "topleft", "tr": "topright",
               "bl": "bottomleft", "br": "bottomright"}

def corner_geo(which, r):
    """(圆心, 切点1, 切点2)。圆心 = 块的内侧角；切点顺序保证绕向一致。"""
    return {
        "tl": ((r, r), (0, r), (r, 0)),
        "tr": ((0, r), (0, 0), (r, r)),
        "bl": ((r, 0), (r, r), (0, 0)),
        "br": ((0, 0), (r, 0), (0, r)),
    }[which]

def corner_path(which, r):
    (ox, oy), (x1, y1), (x2, y2) = corner_geo(which, r)
    # large-arc=0 + sweep=1 → 恒为 90° 短弧，凸向外角
    return f"M {x1},{y1} A {r},{r} 0 0 1 {x2},{y2} L {ox},{oy} Z"

def g_corner(eid, cx, cy, which, r, style, cls=None):
    c = f' class="{cls}"' if cls else ""
    return (f'    <g id="{eid}" transform="translate({cx},{cy})">\n'
            f'      <path d="{corner_path(which, r)}" style="{style}"{c}/>\n'
            f'    </g>\n')

def g_rect(eid, cx, cy, w, h, style, cls=None, extra=""):
    c = f' class="{cls}"' if cls else ""
    return (f'    <g id="{eid}" transform="translate({cx},{cy})">\n'
            f'      <rect x="0" y="0" width="{w}" height="{h}" style="{style}"{c}/>\n'
            f'{extra}'
            f'    </g>\n')

def plain_rect(eid, x, y, w, h, style):
    return f'    <rect id="{eid}" x="{x}" y="{y}" width="{w}" height="{h}" style="{style}"/>\n'


def _shadow_block(x0, y0, m, tile, peak, radius):
    """生成 shadow 八片 + 梯度定义，返回 (defs, rects)。

    ── 三个必须同时满足的约束（每一条都是踩出来的）──

    ① **片厚 = margin + 圆角半径**，不是 margin。
       KWindowShadow 按 hint margin 把片放到窗口外侧。片厚只有 margin 时，
       片的内边界正好贴窗口外接矩形 —— 而弹窗是圆角的，外接矩形角点那块是
       被切掉的透明区，那里既没框体也没阴影，圆弧外缘的阴影在四个角断掉，
       读起来就是「圆角和直角冲突」。
       Breeze 可证：边片厚 16px 而 hint margin 只有 10px，多出的 6px 正是它的
       框体圆角，向窗口内部伸进去覆盖那块缺口。

    ② **框体边缘以内必须 alpha=0**，不能 clamp 在峰值。
       这一条是 Breeze **不需要**而 Frost 必须要的 —— 它的弹窗近乎不透明，
       伸进去的阴影被框体挡住看不见；Frost 的弹窗只有 GLASS_POPUP=0.35 不透明，
       伸进去那段峰值阴影会**直接从半透明框体里透出来**，
       沿内边缘一圈暗带（用户实际看到的）。
       所以梯度要在 offset < head 处显式给 0，让阴影严格止于框体边缘。
       物理上半透明物体确实该透出身后的阴影，但那不是这里想要的观感。

    ③ **必须放在 masks 组之外**，否则 KWin 模糊会漏到弹窗矩形以外。

    ── 坐标推导（topleft，KWindowShadow 放在 win.x-m, win.y-m）──
       SVG x0        ↔ win.x - m        片外边界
       SVG x0 + m    ↔ win.x            框体边缘 = 阴影峰值
       SVG x0 + st   ↔ win.x + radius   片内边界，已在窗口内部
    圆角弧心在 (win.x+radius, win.y+radius) ↔ SVG (x0+st, y0+st)
       —— 正好是角片朝窗口中心那一侧的角点。四角同理。
    统一用 head = radius/st 表示「峰值所在的 offset」：
    直边的梯度从片内边界扫到片外边界（长度 st，框体边缘距内边界 radius）；
    角部的径向梯度以弧心为圆心、半径 st（框体弧面在 radius 处）。两者同一个 head。

    梯度曲线照 Breeze（peak → /2 → /4 → /8 → 0）：前段陡后段长，
    视觉上是「贴边一圈实、往外很快化开」。
    """
    STOPS = ((0.0, 1.0), (1/3, 0.5), (0.5, 0.25), (7/12, 0.125), (1.0, 0.0))
    st = m + radius
    head = radius / st                 # 峰值所在的 offset（= 框体边缘/弧面位置）
    defs, rects = "", ""

    # ★ 前缘必须有约 1px 的软起坡，不能 0→peak 硬跳 ★
    # 第一版写的是 head*0.998 处 0、head 处 peak —— 跨度只有梯度全长的 0.2%
    # （≈0.04px），实测 8 倍光栅化下是单步 +0.396 的硬跳变，阴影内边界完全没有
    # 抗锯齿。直边上这个硬跳被框体自己的硬边缘盖住，看不出来；
    # 但**角部框体是抗锯齿的圆弧、阴影内边界是硬圆**，两者各自独立光栅化 ——
    # 框体边缘半透明的那一像素里，0.396 的阴影直接透出来，
    # 形成一条沿圆角的暗线（用户报的「左下角边缘线不太自然」）。
    # 改成：框体边缘处严格为 0，1px 外才到峰值。峰值位置外移 1px 视觉上察觉不到，
    # 但硬边消失了。直边同样受益（原本也有这条硬边，只是被框体挡着）。
    RAMP = 1.0 / st                    # 1px，换算成 offset 单位

    def stops():
        """offset<head 一律 0（约束②）；head 处仍为 0，head+RAMP 处到峰值；
        之后按 Breeze 曲线衰减到 0。"""
        p0 = head                      # 框体边缘：0
        p1 = head + RAMP               # 1px 外：峰值
        out = (f'        <stop offset="0" style="stop-color:#000000;stop-opacity:0"/>\n'
               f'        <stop offset="{p0:.4f}" '
               f'style="stop-color:#000000;stop-opacity:0"/>\n')
        out += "".join(
            f'        <stop offset="{p1 + (1 - p1) * o:.4f}" '
            f'style="stop-color:#000000;stop-opacity:{peak * mul:.4f}"/>\n'
            for o, mul in STOPS)
        return out

    def lin(gid, gx1, gy1, gx2, gy2):
        """(gx1,gy1)=片**内**边界（窗口内侧），(gx2,gy2)=片外边界。
        峰值落在 offset=head，即距内边界 radius 处 = 框体边缘。"""
        nonlocal defs
        defs += (f'      <linearGradient id="{gid}" gradientUnits="userSpaceOnUse"\n'
                 f'          x1="{gx1}" y1="{gy1}" x2="{gx2}" y2="{gy2}">\n'
                 + stops() + "      </linearGradient>\n")

    def rad(gid, cx, cy):
        nonlocal defs
        defs += (f'      <radialGradient id="{gid}" gradientUnits="userSpaceOnUse"\n'
                 f'          cx="{cx}" cy="{cy}" r="{st}">\n'
                 + stops() + "      </radialGradient>\n")

    def rect(eid, gid, x, y, w, h):
        nonlocal rects
        rects += (f'    <g id="{eid}">\n'
                  f'      <rect x="{x}" y="{y}" width="{w}" height="{h}" '
                  f'fill="url(#{gid})"/>\n'
                  f'    </g>\n')

    xm, xr = x0 + st, x0 + st + tile
    ym, yb = y0 + st, y0 + st + tile

    # 四边：梯度从片内边界扫到片外边界，全长 st
    lin("fs-top",    xm, y0 + st,      xm, y0)          # 内→外（向上）
    lin("fs-bottom", xm, yb,           xm, yb + st)     # 内→外（向下）
    lin("fs-left",   x0 + st, ym,      x0, ym)          # 内→外（向左）
    lin("fs-right",  xr, ym,           xr + st, ym)     # 内→外（向右）
    rect("shadow-top",    "fs-top",    xm, y0, tile, st)
    rect("shadow-bottom", "fs-bottom", xm, yb, tile, st)
    rect("shadow-left",   "fs-left",   x0, ym, st,   tile)
    rect("shadow-right",  "fs-right",  xr, ym, st,   tile)

    # ★ 必须有 shadow-center，否则整个 shadow 前缀对 KSvg 等于不存在 ★
    # KSvg 的 FrameSvg::hasElementPrefix(prefix) 判据就是查 `<prefix>-center`
    # （libKF6Svg.so 里 hasElementPrefix 与字符串 "-center" 并存可证）。
    # 缺它的后果：ToolTip.qml 的 `prefix: "shadow"` 认为前缀不存在、回退到无前缀帧，
    # 工具提示比布局四周各大 9px（Breeze 是 10,10,10,10、Frost 拿到 9,9,9,9）。
    # ★ 更正一处我自己的错误结论 ★
    # 加完八片阴影后我曾宣布「工具提示的 9px 偏差顺带修好了」—— 那是错的。
    # 我当时只核对了 libPlasmaQuick 按名字读的 8 片 + 4 hint（窗口投影走这条路，
    # 确实好了），却没意识到 FrameSvgItem 的前缀机制是另一条路、判据是 -center。
    # 窗口投影和前缀帧是两套消费路径，验一条不等于验了另一条。
    # 内容照 Breeze 的惯例：tile 大小、opacity 0.001 —— 存在但不可见
    # （阴影的中心在窗口底下，本来就不该画东西）。
    rects += (f'    <g id="shadow-center">\n'
              f'      <rect x="{xm}" y="{ym}" width="{tile}" height="{tile}" '
              f'style="opacity:0.001;fill:#000000"/>\n'
              f'    </g>\n')

    # 四角：圆心 = 角片朝窗口中心那一侧的角点（即圆角弧心）
    rad("fs-tl", xm, ym);  rad("fs-tr", xr, ym)
    rad("fs-bl", xm, yb);  rad("fs-br", xr, yb)
    rect("shadow-topleft",     "fs-tl", x0, y0, st, st)
    rect("shadow-topright",    "fs-tr", xr, y0, st, st)
    rect("shadow-bottomleft",  "fs-bl", x0, yb, st, st)
    rect("shadow-bottomright", "fs-br", xr, yb, st, st)

    return defs, rects


def nine_slice(alpha, r=RADIUS, tile=TILE, margin=MARGIN,
               colors=None, with_edge=True, with_mask=True, with_shadow=True):
    """生成一张完整的九宫格毛玻璃 SVG。"""
    # 默认参数在**模块加载时**求值，而 P / DEFAULT_ACCENT 在本行之后才定义，
    # 所以不能写成 colors=_dark_palette() —— 那会 NameError。用哨兵延迟取值。
    colors = colors or _dark_palette()
    S = 2 * r + tile              # 一个区域的边长
    SHW = (SHADOW_MARGIN + r) * 2 + tile   # shadow 区边长（片厚 = margin + 圆角）
    W = max(S, SHW if with_shadow else 0) + GAP * 2
    H = GAP + S + GAP + S + GAP + 24     # 形状 + 遮罩 + 提示
    if with_shadow:
        H += GAP + SHW                   # + 投影区（与宽同量，正方）

    fill = f"opacity:{alpha};fill:currentColor"
    CLS  = "ColorScheme-Background"

    s  = '<?xml version="1.0" encoding="UTF-8"?>\n'
    s += f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
    s += STYLE.format(**colors)

    # ── 区域 1：形状九宫格 ─────────────────────────────
    # ★ 起点必须留出 GAP，不能从 (0,0) 开始 ★
    # 元素紧贴 SVG 画布边界时，Qt 光栅化的边界抗锯齿会让最外一行变成半透明，
    # 叠在较亮的背景上就是一条 1px 亮线 —— 弹窗顶部那条「框线」正是如此。
    # 实测证据：只有上边有线，下/左/右三边都干净，因为只有上边紧贴 y=0。
    # 其它生成器（tasks / listitem / multi_state）本来就从 GAP 起，只有这里漏了。
    x0 = GAP
    y0 = GAP
    s += '  <g id="shape">\n'
    s += g_corner("topleft",     x0,            y0,            "tl", r, fill, CLS)
    s += g_corner("topright",    x0 + r + tile, y0,            "tr", r, fill, CLS)
    s += g_corner("bottomleft",  x0,            y0 + r + tile, "bl", r, fill, CLS)
    s += g_corner("bottomright", x0 + r + tile, y0 + r + tile, "br", r, fill, CLS)

    # EDGE_ALPHA 为 0 时干脆不生成这个元素，避免在 SVG 里留下 opacity:0 的死节点
    edge = (f'      <rect x="0" y="0" width="{tile}" height="1" '
            f'style="opacity:{EDGE_ALPHA};fill:#ffffff"/>\n') \
           if (with_edge and EDGE_ALPHA > 0) else ""
    s += g_rect("top",    x0 + r,        y0,            tile, r,    fill, CLS, extra=edge)
    s += g_rect("bottom", x0 + r,        y0 + r + tile, tile, r,    fill, CLS)
    s += g_rect("left",   x0,            y0 + r,        r,    tile, fill, CLS)
    s += g_rect("right",  x0 + r + tile, y0 + r,        r,    tile, fill, CLS)
    s += g_rect("center", x0 + r,        y0 + r,        tile, tile, fill, CLS)
    s += '  </g>\n'

    # ── 区域 2：模糊遮罩（告诉 KWin 在什么形状内做背景模糊）──
    if with_mask:
        # 遮罩区同样整体偏移 GAP，和形状区保持一致，也避免贴画布边
        y1 = GAP + S + GAP
        mf = "fill:#000000"
        s += '  <g id="masks">\n'
        s += g_corner("mask-topleft",     x0,            y1,            "tl", r, mf)
        s += g_corner("mask-topright",    x0 + r + tile, y1,            "tr", r, mf)
        s += g_corner("mask-bottomleft",  x0,            y1 + r + tile, "bl", r, mf)
        s += g_corner("mask-bottomright", x0 + r + tile, y1 + r + tile, "br", r, mf)
        s += g_rect("mask-top",    x0 + r,        y1,            tile, r,    mf)
        s += g_rect("mask-bottom", x0 + r,        y1 + r + tile, tile, r,    mf)
        s += g_rect("mask-left",   x0,            y1 + r,        r,    tile, mf)
        s += g_rect("mask-right",  x0 + r + tile, y1 + r,        r,    tile, mf)
        s += g_rect("mask-center", x0 + r,        y1 + r,        tile, tile, mf)
        s += '  </g>\n'

    # ── 区域 3：边距 / 内缩提示（不可见，只向 Plasma 传尺寸）──
    y2 = GAP + S + GAP + S + GAP
    hint = "fill:#ff00ff"
    inset = "fill:#00ff00"
    s += '  <g id="hints">\n'
    s += plain_rect("hint-top-margin",    0,  y2,      4, margin, hint)
    s += plain_rect("hint-bottom-margin", 8,  y2,      4, margin, hint)
    s += plain_rect("hint-left-margin",   16, y2, margin, 4,      hint)
    s += plain_rect("hint-right-margin",  24, y2, margin, 4,      hint)
    # 内缩全为 0：面板背景不额外内缩（悬浮间距由面板自身控制）。
    # ★ 轴要和 margin 一致 ★ top/bottom 的量由 height 表达、left/right 由 width，
    # 就像上面四条 margin 那样。早先四个都写成 (4, 0)，left/right 的轴是反的 ——
    # 当前值为 0 所以功能上看不出来，但改成非 0 时会静默失效，
    # 而且 KSvg 读到尺寸为 0 的元素本来就可能直接丢弃，两处叠加极难排查。
    INSET = 0
    s += plain_rect("hint-top-inset",    32, y2, 4, INSET, inset)
    s += plain_rect("hint-bottom-inset", 40, y2, 4, INSET, inset)
    s += plain_rect("hint-left-inset",   48, y2, INSET, 4, inset)
    s += plain_rect("hint-right-inset",  56, y2, INSET, 4, inset)
    # 四个 shadow-hint-*-margin 单独一行放，避开上面那四条 hint 的占位
    # （上面用 y2..y2+9，这里用 y2+12..y2+22，都在 24px 高的提示区内）
    if with_shadow:
        s += plain_rect("shadow-hint-top-margin",    0,  y2 + 12, 4, SHADOW_MARGIN, hint)
        s += plain_rect("shadow-hint-bottom-margin", 8,  y2 + 12, 4, SHADOW_MARGIN, hint)
        s += plain_rect("shadow-hint-left-margin",   16, y2 + 12, SHADOW_MARGIN, 4,  hint)
        s += plain_rect("shadow-hint-right-margin",  24, y2 + 12, SHADOW_MARGIN, 4,  hint)
    s += '  </g>\n'

    # ── 区域 4：投影 ────────────────────────────────────
    # 独立一组，**不在 masks 里** —— 见 _shadow_block() 的说明。
    if with_shadow:
        y3 = GAP + S + GAP + S + GAP + 24 + GAP
        sdefs, srects = _shadow_block(GAP, y3, SHADOW_MARGIN, tile, SHADOW_ALPHA, r)
        s += '  <defs>\n' + sdefs + '  </defs>\n'
        s += '  <g id="shadows">\n' + srects + '  </g>\n'

    s += '</svg>\n'
    return s


# ─────────────────────── 配色方案 (.colors) ───────────────────────
# 冷灰蓝中性暗色。强调色是冷青（#4dd0c0）——
# 主题叫 Frost，霜色本来就该是冷青；而且实测对比度 7.49:1，
# 比之前偶然从壁纸取到的品红紫（2.90:1）高一倍多。
# 用户开着「跟随壁纸取色」时，新壁纸的冷青主调会取出同族的强调色。
P = dict(
    window="32,36,42",        # #20242a  窗口底
    window_alt="38,43,49",
    view="23,26,31",          # #171a1f  列表/输入框底（更深）
    view_alt="28,32,37",
    button="42,47,54",        # #2a2f36
    button_alt="52,58,66",
    text="232,234,237",       # #e8eaed
    text_inactive="154,163,173",
    accent="77,208,192",      # 仅作占位：color_scheme() 会用当前时段的强调色覆盖
    accent_dim="55,150,138",
    # negative/visited 原为 BreezeDark 上游默认，在本主题最亮的底色
    # button_alt(52,58,66) 上只有 2.70 / 2.46:1。提亮后最差 5.15 / 4.78:1。
    # 理由是自洽：README #84 已为终端立过「颜色承载信息不是装饰，≥4.5:1」
    # 的硬线，同一套主题里终端的红达标、UI 的红不达标说不过去。
    # neutral/positive 同样是上游默认，在 button_alt(52,58,66) 上
    # 只有 4.05 / 3.99:1 —— 构建门禁抓出来的，人工抽查时漏掉了。
    # 提亮后 5.23 / 5.13:1，色相保持不变（橙仍是橙、绿仍是绿）。
    negative="255,140,148", neutral="252,150,60", positive="64,196,120",
    link="126,200,236", visited="196,148,232",
    tooltip="30,34,40", header="38,43,49",
)

def colors_block(name, bg, bg_alt, fg=None):
    fg = fg or P["text"]
    return textwrap.dedent(f"""\
        [Colors:{name}]
        BackgroundAlternate={bg_alt}
        BackgroundNormal={bg}
        DecorationFocus={P['accent']}
        DecorationHover={P['accent']}
        ForegroundActive={P['accent']}
        ForegroundInactive={P['text_inactive']}
        ForegroundLink={P['link']}
        ForegroundNegative={P['negative']}
        ForegroundNeutral={P['neutral']}
        ForegroundNormal={fg}
        ForegroundPositive={P['positive']}
        ForegroundVisited={P['visited']}

        """)

def color_scheme(accent=None):
    """生成一套配色。accent 缺省时用 DEFAULT_ACCENT。

    注意 accent 不能真的缺省成 None —— 早先那样写会让基础 Frost 方案
    落到 P 里那个写死的旧青色 77,208,192，和它自己 [Colors:Selection]
    声明的强调色互相矛盾。运行时看不出来（daylight.py 会直接往 kdeglobals
    写正确值），但在系统设置里手动选这套配色，拿到的就是那个废弃的青色。
    """
    accent = accent or DEFAULT_ACCENT
    s  = textwrap.dedent(f"""\
        [ColorEffects:Disabled]
        Color=56,56,56
        ColorAmount=0
        ColorEffect=0
        ContrastAmount=0.65
        ContrastEffect=1
        IntensityAmount=0.1
        IntensityEffect=2

        [ColorEffects:Inactive]
        ChangeSelectionColor=true
        Color=112,111,110
        ColorAmount=0.025
        ColorEffect=2
        ContrastAmount=0.1
        ContrastEffect=2
        Enable=false
        IntensityAmount=0
        IntensityEffect=0

        """)
    a = ",".join(str(v) for v in accent)
    # 强调色相关的三个角色一起换，否则选中态和焦点框会对不上。
    # colors_block() 读的是模块级的 P，所以只能先改 P；但必须存一份原值，
    # 函数结束时复原 —— 否则生成第二套方案时 P 里还留着第一套的强调色，
    # 结果就变成「谁先生成谁说了算」的顺序依赖。
    _saved = dict(P)
    P.update(accent=a,
             accent_dim=",".join(str(int(v * 0.92)) for v in accent))
    s += colors_block("Button",        P["button"], P["button_alt"])
    s += colors_block("Complementary", P["window"], P["window_alt"])
    # 第二个参数是 BackgroundAlternate。原先传 P["window_alt"]，
    # 而它恰好和 P["header"] 同值（都是 38,43,49）—— 交替行完全看不出交替。
    # 改传比 header 略暗的 window 色，拉开一档。
    s += colors_block("Header",        P["header"], P["window"])
    # [Colors:Header][Inactive] —— 不写它，未聚焦窗口的标题栏区域和聚焦的一模一样。
    # Kirigami 应用（系统设置、Discover、Elisa）和 plasmoidheading 都读这一组；
    # 缺了它，两个窗口并排时**没有任何颜色线索**指示焦点在哪 ——
    # 唯一剩下的线索是 [WM] 的 active/inactive 背景，实测只差 1.09:1，等于没有。
    # 取值照 Breeze 的做法：活动态用较亮的 header，非活动态用较暗的 window。
    s += colors_block("Header][Inactive", P["window"], P["window_alt"],
                      fg=P["text_inactive"])
    s += colors_block("Tooltip",       P["tooltip"], P["window_alt"])
    s += colors_block("View",          P["view"],   P["view_alt"])
    s += colors_block("Window",        P["window"], P["window_alt"])
    s += textwrap.dedent(f"""\
        [Colors:Selection]
        BackgroundAlternate={P['accent_dim']}
        BackgroundNormal={P['accent']}
        DecorationFocus={P['accent']}
        DecorationHover={P['accent']}
        # ★ Selection 组的前景必须是深色，不能沿用 Breeze 的白 ★
        # Breeze 的选中底是中调蓝 61,174,233（白字 2.49:1，本就勉强）；
        # Frost 为了让强调色在深色面板上跳出来，四个强调色做得明显更浅
        # （相对亮度 0.423–0.549），白字于是塌到 1.75–2.22:1，差 AA 一倍多。
        # 底色换了、压在底色上的前景没跟着换 —— 这是本组八个键全不达标的根因。
        # 影响面：Dolphin 选中行、菜单高亮、文本框选中、KRunner 结果、
        # 系统设置侧栏当前项，以及 GTK 侧（kde-gtk-config 镜像本组）。
        #
        # ForegroundNormal 用 P['view']，与内容区底色同源，不引入新颜色。
        # Active / Inactive **不能**和 Normal 同值 —— 它们是 KColorScheme 的
        # 三个独立语义角色，塌成一个会让选中行内部本该变淡的次要文字失去信号。
        # Inactive 的标准取 3:1 而非 4.5:1：它的语义就是去强调。
        # 实测（四时段 × BackgroundNormal/BackgroundAlternate 共 8 组合）最差值：
        #   Normal 6.90 / Active 7.65 / Inactive 4.13 / Link 5.53 /
        #   Visited 5.80 / Negative 5.42 / Neutral 5.10 / Positive 5.34
        ForegroundActive=12,14,17
        ForegroundInactive=58,64,74
        ForegroundLink=20,42,88
        ForegroundNegative=92,14,26
        ForegroundNeutral=84,36,0
        ForegroundNormal={P['view']}
        ForegroundPositive=10,54,28
        # ★ 必须写死，不能引用 P['visited'] ★
        # P['visited'] 是给深色底用的浅紫(196,148,232)。若这里引用它，浅紫落在
        # 浅强调底上 —— day 时段实测掉到 1.28:1，几乎不可见。
        # 同块里 Negative 早就是写死的，这里对齐同一做法。
        ForegroundVisited=58,24,82

        # 强调色固定为主题色，不跟随壁纸 —— 见 README 第 36 条：
        # 壁纸取色 + 透明面板 = 强调色和面板同源同色，实测只有 1.42:1。
        [General]
        ColorScheme={NAME}
        Name={NAME}
        accentColorFromWallpaper=false
        # 这里**不写 AccentColor**。写了的话 Plasma 会忽略下面
        # [Colors:Selection] 声明的值，改用它自己从 AccentColor 派生的减淡版
        # （实测只剩 73% 亮度）。强调色由 [Colors:Selection] 直接声明即可。
        shadeSortColumn=true

        [KDE]
        contrast=0

        [WM]
        activeBackground={P['window_alt']}
        activeBlend={P['text']}
        activeForeground={P['text']}
        inactiveBackground={P['window']}
        inactiveBlend={P['text_inactive']}
        inactiveForeground={P['text_inactive']}
        """)
    P.clear(); P.update(_saved)     # 复原，见上面关于顺序依赖的说明
    return s


# ─────────────────── 全局主题包 (look-and-feel) ───────────────────
LNF_ID = "com.xhhcn.frost"

def lnf_defaults():
    """主题总开关。contrast=0 是让 Breeze 菜单/弹窗变毛玻璃的关键。"""
    return textwrap.dedent(f"""\
        [kdeglobals][General]
        ColorScheme={NAME}

        [kdeglobals][Icons]
        Theme=Frost

        [kdeglobals][KDE]
        widgetStyle=Darkly
        contrast=0
        frameContrast=0.15

        [plasmarc][Theme]
        name={NAME}

        [kwinrc][org.kde.kdecoration2]
        library=org.kde.darkly
        theme=Darkly

        [kcminputrc][Mouse]
        cursorTheme=breeze_cursors

        [ksplashrc][KSplash]
        Theme=com.xhhcn.frost
        Engine=KSplashQML

        # 这里**不写壁纸**。写死一张会和按时段切换打架：
        # 套用 look-and-feel 会把壁纸强制设成那一张，无视当前是什么时段。
        # 壁纸由 daylight.py 按太阳高度角决定（见 apply-frost.sh 末尾）。

        # ★ 这一段是死配置，留着只为可读性 ★
        # 实测 /usr/lib/libklookandfeel.so.6（LookAndFeelManager 的实现）
        # 只处理 kwinrc 下的 org.kde.kdecoration2 / WindowSwitcher /
        # DesktopSwitcher / Placement —— 字符串表里 "Plugins" 的 ASCII 与
        # UTF-16 双双 0 命中（对照：上述组名全部命中，证明扫描有效）。
        # 所以特效开关一律由 tweak.py 写 kwinrc + qdbus load/unload 完成；
        # 也正因如此这里**不**补 frost_minimizeEnabled —— 补了同样不起作用。
        [kwinrc][Plugins]
        blurEnabled=true
        # 不写 contrastEnabled：KWin 6.7 的已加载特效列表里只有 blur，
        # contrast（背景对比）特效已被移除，写了是死键。
        # 参考仓库 README 的 Glass effect 一节建议「取消勾选 Background contrast」——
        # 在 Plasma 6 上这条自动成立。玻璃通透度改由 kdeglobals 的
        # contrast=0 / frameContrast=0.15 控制（见 tweak.py）。

        [kwinrc][Effect-blur]
        BlurStrength=13
        NoiseStrength=4
        """)

def lnf_metadata():
    return json.dumps({
        "KPlugin": {
            "Authors": [{"Name": AUTHOR}],
            "Category": "",
            "Description": "Minimal frosted glass. Top bar + bottom task bar; wallpaper and accent follow the sun.",
            "Id": LNF_ID,
            "License": "GPL-2.0-or-later",
            "Name": NAME,
            "Version": VERSION,
        },
        "KPackageStructure": "Plasma/LookAndFeel",
    }, indent=4, ensure_ascii=False) + "\n"


# ─────────────────────────── 壁纸 ───────────────────────────
# 自己生成，不用别人的图片。纯 SVG 渐变 —— 几 KB，任意分辨率不糊，
# 平滑渐变正好让面板的模糊效果显出来（纯色壁纸下毛玻璃是看不见的）。
# 壁纸包名前缀是 FrostScene-<时段>，由 wallpaper_files() 直接拼字符串。
# 这里曾有个 WALL_ID = "FrostGlass" 常量，没有任何人读它，而且名字和实际
# 包名前缀不一致 —— 留着只会让人以为改它能改包名。已删，由新的源码自检看守。


# ─────────────────── 启动画面：登录 → 桌面的过渡 ───────────────────
SPLASH_QML = """\
import QtQuick
// ★ 不再 import Kirigami ★
// 唯一用到它的地方是进度条颜色（Kirigami.Theme.highlightColor），
// 而那个在 ksplashqml 里取不到配色、已换成由 daylight.py 写进来的具体值。
// 留着这个 import 只是多一条失败路径：splash 的 QML 一旦加载失败，
// 开机就是**没有 splash**（实测把探针写错一个字符就得到
// "Error loading QML file" + 屏幕什么都不显示）。
// 少一个 import 少一个白屏风险。QtQuick 是必需的，保留。

// Frost 启动画面 —— 由 build-theme.py 生成
//
// 为什么要自己写这一屏：
//   登录壁纸是系统级设置（/var/lib/plasmalogin，root 所有），
//   没法跟着时段自动切，只能钉死成一张中性暮色；
//   桌面壁纸却是跟着太阳走的。两头对不上。
//
//   解法不是把两头调成同色，而是**让构图承担连续性**：
//   登录图和四张时段图用的是同一套山脊、湖面、松树剪影，
//   逐像素对齐。于是这一屏只要在两张图之间交叉淡入，
//   山不动、水不动，只有天光在推移 —— 就是一段延时摄影，
//   而不是「换了三张壁纸」。
//
//   images/login.svg  = 用户刚刚看到的那一帧（起点，接住登录界面）
//   images/scene.svg  = 当前时段（终点，接上桌面），由 daylight.py 同步
Rectangle {
    id: root
    color: "#141c28"

    // Plasma 把 stage 从 1 推到 6。到 5 就淡完，
    // 让最后一刻稳定停在桌面的真实颜色上，交接那一帧不会还在变。
    property int stage
    readonly property real progress: Math.max(0, Math.min(1, (stage - 1) / 4))

    // 起点：登录界面那一帧，原样接住
    Image {
        anchors.fill: parent
        source: "images/login.svg"
        fillMode: Image.PreserveAspectCrop
        sourceSize.width: root.width
        sourceSize.height: root.height
        cache: false
    }

    // 终点：当前时段。淡入而不是滑入 —— 构图本来就重合，
    // 只有颜色在变，看起来就是光线变了。
    Image {
        anchors.fill: parent
        source: "images/scene.svg"
        fillMode: Image.PreserveAspectCrop
        sourceSize.width: root.width
        sourceSize.height: root.height
        cache: false
        opacity: root.progress
        // ★ duration 必须远小于相邻 stage 的间隔，否则永远追不上 ★
        // 实测本机 plasma-ksplash.service 的全生命周期
        // （journalctl "Consumed … over … wall clock time"，10 次登录）：
        //   411ms / 765 / 770 / 780 / 1.063s / 1.233 / 1.240 / 1.245 / 1.276 / 1.540s
        // 6 个 stage 挤在里面 → 相邻间隔约 130–260ms。而 stage 6
        // （plasmashell 报 desktop）到达后约 4ms 根对象就被销毁，没有缓冲期。
        // Behavior 在每次 stage 变化时都从当前值重新起算 600ms，
        // 于是它从来没有机会跑完。用真实 ksplashqml + busctl 驱动 stage、
        // 在 Component.onDestruction 读不透明度：
        //   duration 600 → 间隔 215ms 时只有 **0.524**，300ms 时 0.776
        //   duration 150 → 间隔 100ms 时 0.963，≥150ms 时 **1.000**
        // 也就是说源码注释里那句「到 5 就淡完，交接那一帧不会还在变」
        // 在 600ms 下**恰好是反的** —— 交接那一帧正停在半程。
        // 压到 150 之后那句话才成立。
        Behavior on opacity {
            NumberAnimation { duration: 150; easing.type: Easing.InOutQuad }
        }
    }

    // 底部细横条。刻意和任务栏的运行指示同一套形状语言
    // （细、圆头、强调色）—— 启动时见过的形状进桌面后还在，
    // 这是把 splash 和桌面缝在一起的第二条线索。
    Item {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Math.round(root.height * 0.085)
        width: Math.round(root.width * 0.11)
        height: 3

        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: "#ffffff"
            opacity: 0.16
        }
        Rectangle {
            height: parent.height
            radius: height / 2
            // 留一点起始长度，stage 1 时不至于完全看不见
            width: parent.width * (0.12 + 0.88 * root.progress)
            // ★ 不能用 Kirigami.Theme.highlightColor ★
            // ksplashqml 是纯 QGuiApplication（没有 QStyle / 调色板），
            // Kirigami 的 Theme 取不到 KColorScheme。实测（真实 ksplashqml，
            // 不是 qml6）：kdeglobals 里 ColorScheme=Frost-day（强调色
            // 104,203,223）时读出 #308cc6；把 HOME 指到一个连 kdeglobals
            // 都没有的空目录，读出的**还是** #308cc6 ——
            // 两种截然不同的输入给出同一个读数，就证明它没在读配色。
            // Component.onCompleted 那一刻更是 #000000（开机头一两帧是黑条，
            // 看起来像进度条反着走）。
            // 同一次运行里 Kirigami.Units.gridUnit=18 是对的，所以不是 import
            // 的问题 —— /usr/share 下三套官方 splash 也无一使用
            // Kirigami.Theme 的颜色，Breeze 直接把文字色写死成 #eff0f1。
            //
            // 但写死一个颜色就违背了这根条子的用意（「和任务栏指示同一套
            // 形状语言、把 splash 和桌面缝在一起」）—— 写死就缝不上。
            // 所以用占位符 __FROST_ACCENT__，由 daylight.py 的 sync_splash()
            // 在换时段时连同 scene.svg 一起替换成当前时段的强调色。
            // 出厂值先填 dusk（和其余构建期 fallback 一致）。
            color: "__FROST_ACCENT__"   // FROST_ACCENT_LINE
            opacity: 0.92
            // 和上面同一个理由：600ms 追不上 ~200ms 的 stage 间隔
            Behavior on width {
                NumberAnimation { duration: 150; easing.type: Easing.InOutQuad }
            }
        }
    }
}
"""


def splash_files():
    """启动画面。images/scene.svg 先放默认时段，
    daylight.py 会在切换时段时覆盖成当前场景。"""
    from wallpaper import scene
    # 进度条颜色的出厂值。占位符由 daylight.py 的 sync_splash() 在换时段时
    # 替换成当前时段的强调色 —— 见 SPLASH_QML 里那段关于
    # Kirigami.Theme 在 ksplashqml 里不可用的注释。
    qml = SPLASH_QML.replace("__FROST_ACCENT__",
                             "#%02x%02x%02x" % DEFAULT_ACCENT)
    return {
        "splash/Splash.qml": qml,
        # 起点图：和系统级登录壁纸是同一张，写死不变
        "splash/images/login.svg": scene("login"),
        # 终点图：占位默认值，daylight.py 会同步成当前时段
        "splash/images/scene.svg": scene("dusk"),
    }



# ─────────────── 登录界面壁纸（系统级，要 sudo 单独装）───────────────
def login_wallpaper(outdir):
    """把中性登录图导出成 PNG，供 /usr/share/wallpapers 使用。

    为什么这里非要 PNG：桌面壁纸用 SVG 是验证过能跑的，但登录界面
    由 plasmalogin 用户的独立进程渲染，我没法在不注销的前提下测它。
    系统自带的三套壁纸（Air/Horos/Next）清一色是 PNG —— 那是确定能用的
    格式。这一处赌不起「装完注销才发现是黑屏」，所以按最保守的来。

    光栅化器是**构建期**依赖，不进运行时占用。三个候选依次降级，
    都没有就退回 SVG 并明确警告，不静默产出一个可能打不开的包。
    """
    from wallpaper import scene
    import shutil, subprocess as sp
    pkg = os.path.join(outdir, "login-wallpaper", "FrostLogin")
    img = os.path.join(pkg, "contents", "images")
    os.makedirs(img, exist_ok=True)
    svg = scene("login")
    write(os.path.join(pkg, "metadata.json"), json.dumps({
        "KPlugin": {"Authors": [{"Name": AUTHOR}], "Id": "FrostLogin",
                    "License": "CC0-1.0", "Name": f"{NAME} · Login",
                        "Description": "Neutral dusk valley for the login screen.",
                        "Version": VERSION},
        "KPackageStructure": "Wallpaper/Images",
    }, indent=4, ensure_ascii=False) + "\n")

    # 只出一个尺寸。3840x2400 那张 372 KB，占整个分发包的三分之一，
    # 而登录界面本来就会把壁纸虚化 —— 多出来的分辨率看不出差别。
    # 4K 屏想要原生尺寸的，改这里重新构建即可。
    sizes = [(1920, 1200)]
    try:
        import cairosvg
        for w, h in sizes:
            cairosvg.svg2png(bytestring=svg.encode(),
                             write_to=os.path.join(img, f"{w}x{h}.png"),
                             output_width=w, output_height=h)
        return "cairosvg"
    except ImportError:
        pass

    tmp = os.path.join(img, "_src.svg")
    write(tmp, svg)
    for tool, argv in (("rsvg-convert", lambda w, h, o: ["rsvg-convert", "-w", str(w), "-h", str(h), "-o", o, tmp]),
                       ("magick",       lambda w, h, o: ["magick", "-background", "none", tmp, "-resize", f"{w}x{h}!", o])):
        if shutil.which(tool):
            ok = True
            for w, h in sizes:
                r = sp.run(argv(w, h, os.path.join(img, f"{w}x{h}.png")), capture_output=True)
                ok = ok and r.returncode == 0
            if ok:
                os.remove(tmp)
                return tool
    os.remove(tmp)
    write(os.path.join(img, "3840x2400.svg"), svg)
    print("  !! 找不到光栅化器（cairosvg / rsvg-convert / magick），"
          "登录壁纸退回 SVG —— 登录界面能否读 SVG 未经验证，装完请先确认再注销")
    return None



# ─────────────────── 系统设置里的预览图 ───────────────────
def preview_files(outdir):
    """生成 contents/previews/{preview.png,fullscreenpreview.jpg}。

    系统设置的「全局主题」页面用这两张图做缩略图和大图预览，没有就是一块空白。
    规格照官方主题：preview.png 600x337、fullscreenpreview.jpg 1920x1080。

    刻意**合成**而不是截屏：截屏会把当时屏幕上的窗口内容一起打包进主题里，
    既是隐私问题，也让预览图无法随构建重现。这里直接用主题自己的素材
    （场景壁纸 + 真实的面板 SVG + 强调色）拼出来，改了参数重新构建即同步更新。

    需要 cairosvg + PIL；缺了就跳过，不影响主题本身（只是系统设置里没缩略图）。
    """
    try:
        import cairosvg
        from PIL import Image, ImageDraw
    except Exception as e:
        # ★ 不能只 catch ImportError ★
        # cairosvg 装了但系统缺 libcairo.so 时，import 抛的是 OSError；
        # 而这里已经在 main() 里、out/ 早就被 rmtree 过了 ——
        # 未捕获异常会让构建崩在「旧产物已删、新产物没生成」的中间态。
        print(f"  (跳过预览图：{type(e).__name__}: {e})")
        return False
    import io
    from wallpaper import scene

    def compose(W, H):
        # 壁纸是 3840x2400（1.60），预览是 16:9（1.78）——
        # cairosvg 会保持比例并居中留白，直接按目标尺寸渲染会得到上下两条透明带。
        # 所以先按宽度渲染到足够高，再按目标比例居中裁切（等价于 PreserveAspectCrop）。
        rh = round(W * 2400 / 3840)
        png = cairosvg.svg2png(bytestring=scene("dusk").encode(),
                               output_width=W, output_height=rh)
        full = Image.open(io.BytesIO(png)).convert("RGBA")
        if rh > H:
            # 从偏上位置裁 —— 保住山脊和太阳，下方水面本来就大片同色
            top = round((rh - H) * 0.42)
            full = full.crop((0, top, W, top + H))
        else:
            full = full.resize((W, H))
        img = full
        acc = DEFAULT_ACCENT
        # 面板按屏幕比例缩放：真实是 1920x1200 上 34/47 px
        top_h = max(2, round(H * 34 / 1200))
        # 底栏 60px、图标 49px 是 tweak.py 里 BOTTOM_THICKNESS 定的实际值。
        # 早先这里写 47/30 —— 那是好几轮之前的旧值，预览图和实际发布的桌面对不上。
        bot_h = max(3, round(H * 60 / 1200))
        # 面板 = 配色的窗口色，GLASS_PANEL 透明度覆在壁纸上
        pw = int(round(GLASS_PANEL * 255))
        for y0, h in ((0, top_h), (H - bot_h, bot_h)):
            bar = Image.new("RGBA", (W, h), (34, 38, 43, pw))
            img.alpha_composite(bar, (0, y0))
        d = ImageDraw.Draw(img)
        # 底栏：五个应用图标位 + 运行指示条（用真实的强调色和不透明度阶梯）
        n, ic = 5, max(6, round(H * 49 / 1200))
        gap = round(ic * 1.55)
        total = n * ic + (n - 1) * (gap - ic)
        x = (W - total) // 2
        cy = H - bot_h // 2
        for i in range(n):
            d.rounded_rectangle([x, cy - ic // 2, x + ic, cy + ic // 2],
                                radius=max(1, ic // 5), fill=(232, 234, 237, 165))
            a = TASK_STATES["focus"][0] if i == 2 else TASK_STATES["normal"][0]
            if i in (1, 2, 3):
                # 指示条：真实主题里是 3px/1200，预览缩小后不足 1px 会消失，
                # 所以下限拉到 2px，否则预览里看不到这个最有辨识度的元素
                bh = max(2, round(H * 3 / 1200))
                bw = round(ic * BAR_LEN)
                by = H - max(2, round(bot_h * 0.14))
                d.rounded_rectangle([x + (ic - bw) // 2, by - bh,
                                     x + (ic + bw) // 2, by],
                                    radius=bh // 2, fill=acc + (int(a * 255),))
            x += gap
        # 顶栏：左侧徽标位、居中时钟、右侧托盘点
        m = max(3, round(W * 14 / 1920))
        ty = top_h // 2
        d.ellipse([m, ty - top_h // 4, m + top_h // 2, ty + top_h // 4], fill=(232, 234, 237, 200))
        cw = round(W * 0.045)
        d.rounded_rectangle([W // 2 - cw // 2, ty - max(1, top_h // 6),
                             W // 2 + cw // 2, ty + max(1, top_h // 6)],
                            radius=max(1, top_h // 8), fill=(232, 234, 237, 190))
        rx = W - m
        for _ in range(6):
            r = max(1, top_h // 6)
            d.ellipse([rx - r * 2, ty - r, rx, ty + r], fill=(232, 234, 237, 175))
            rx -= round(r * 4.6)
        return img.convert("RGB")

    pdir = os.path.join(outdir, "look-and-feel", LNF_ID, "contents", "previews")
    os.makedirs(pdir, exist_ok=True)
    compose(600, 337).save(os.path.join(pdir, "preview.png"), optimize=True)
    compose(1920, 1080).save(os.path.join(pdir, "fullscreenpreview.jpg"),
                             quality=88, optimize=True)
    return True



# ─────────────────── Konsole 终端配色 ───────────────────
# 终端是这套主题原本缺的一块：Plasma 面板、窗口、文件管理器都统一了，
# 一开终端却是另一套颜色。
#
# 取值原则和主题其余部分一致 —— 底色沿用 P["view"]（列表/输入框那一档，
# 比窗口底更深，符合「终端是内容区」的语义），前景沿用 P["text"]。
# 八个 ANSI 色**不直接抄主题的语义色**：语义色是给 UI 用的（负/中性/正），
# 饱和度偏低，放到终端里 ls 的输出会糊成一片。
# 这里另调一组，唯一硬性要求是**每个色在终端底色上都要 ≥4.5:1** ——
# 终端里这些颜色承载的是信息（文件类型、diff、日志级别），不是装饰。
KONSOLE_ANSI = {
    #        normal            intense（亮色版）
    0: ("58,64,72",       "130,142,156"),   # 黑/灰  # 3.78→5.23:1，ANSI 亮黑是次要前景槽(SGR 90)不是背景，门禁不豁免它
    # ★ normal 档要比 Intense 明显暗，不能只差一点 ★
    # 原来两档只差约 9 个 L*、色相彩度几乎不动，CIEDE2000 只有 5.76~8.74
    # （色 1-7 中位 6.29）。SGR 1（粗体）有字重兜底看不出来，
    # 但 **SGR 90–97（亮色前景、不带粗体）就是同一个颜色** ——
    # eza/delta/rg/powerlevel10k/tmux 状态栏全靠它做二级区分。
    # 最紧的是青：\e[36m #6eccce vs \e[96m #8ee2e4，ΔE 5.76。
    #
    # 修法是**压 normal 而不是提 Intense**：Intense 已经在 L* 71~85，
    # 再提就撞 brwhite（L* 95.4）了；normal 那边有对比度余量可以让出来。
    # 实测这笔交易（色 1-7，排除 ANSI 黑 —— 它对暗底本就低对比 1.67:1，
    # 不参与可读性判据）：
    #   ΔE 最小 5.76 → 11.92，中位 6.29 → 12.08（2.1 倍）
    #   normal 对 Background #171a1f 最差对比 5.60 → 4.92（门禁下限 4.5）
    # 对比度让掉 12% 换来可辨性翻倍，而且构建期门禁自己过 —— 不是靠放宽过的。
    #
    # 判据来源：把 Konsole 六套内置配色的 normal↔Intense 中位 ΔE 量了一遍
    # （8.24~44.34），本套 6.29 是最低的，而且是唯一「7 个彩色对全部挤在
    # 一个窄带里」的 —— 别家是个别对紧，这里是系统性压缩。
    1: ("216,99,108",     "255,140,148"),   # 红
    2: ("111,179,122",    "158,225,168"),   # 绿
    3: ("205,159,85",     "255,205,128"),   # 黄
    4: ("109,159,208",    "154,202,255"),   # 蓝
    5: ("178,134,211",    "216,178,255"),   # 洋红
    6: ("97,179,181",     "142,226,228"),   # 青
    7: ("187,191,196",    "240,242,245"),   # 白
}


def konsole_scheme():
    """生成 Frost.colorscheme。faint 档由 normal 压暗 22% 得到，
    不另外调一组 —— 三档手调很难保持一致，压暗是可复现的。"""
    bg  = P["view"]           # 23,26,31
    fg  = P["text"]
    def dim(rgb, f):
        return ",".join(str(int(int(v) * f)) for v in rgb.split(","))
    out = []
    def sec(name, color):
        out.append(f"[{name}]\nColor={color}\n")
    sec("Background", bg)
    sec("BackgroundFaint", dim(bg, 0.88))
    sec("BackgroundIntense", dim(bg, 0.72))
    for i, (normal, intense) in KONSOLE_ANSI.items():
        sec(f"Color{i}", normal)
        sec(f"Color{i}Faint", dim(normal, 0.78))
        sec(f"Color{i}Intense", intense)
    sec("Foreground", fg)
    sec("ForegroundFaint", dim(fg, 0.72))
    sec("ForegroundIntense", "255,255,255")
    # ★ 终端必须完全不透明 ★
    # 曾经写的是 Opacity=0.9 + Blur=true，静止时看不出问题（透出的那 10%
    # 被 KWin 糊成一片色块）。但 KWin 的 BlurEffect::shouldBlur() 对
    # **被缩放或平移的窗口直接拒绝模糊** —— 最小化(squash)一开始缩放，
    # 模糊立刻撤掉，那 10% 就变成清晰可读的背景文字透上来，
    # 整个窗口看着突然"变半透明"。淡入淡出都有，因为两者都是缩放变换。
    # 而且这也违反主题自己的原则：玻璃只给 chrome，内容区不透明。
    # 终端正文是内容区 —— 所以是 1.0，Blur 随之无意义，一并去掉。
    out.append("[General]\n"
               "ColorRandomization=false\n"
               f"Description={NAME}\n"
               "Opacity=1\n"
               "Wallpaper=\n")
    return "".join(out)


def konsole_profile():
    """生成 Frost.profile —— 让配色自动生效，并把内容边距对齐系统 token。

    ★ 为什么需要 profile，而不是只给一份 .colorscheme ★
    只装配色的话，用户必须自己去「设置 → 编辑当前方案 → 外观」里选 Frost
    （install-frost.sh 一直在打印这行手工步骤）。装一个 profile 并把它设成
    默认（tweak.py 写 konsolerc DefaultProfile），主题才算真的应用上了。

    ★ 键属于哪个组是实测确定的，不是猜的 ★
    profile 是 INI，组放错等于整份静默失效。二进制里能挖到组名表
    （Encoding Options / Interaction Options / Cursor Options /
      Terminal Features / Scrolling / Keyboard / Appearance / General），
    但挖不到「键→组」的映射。所以是写出来实测边距有没有从 0 变 9 来确认的。

    ★ 这里**刻意只写两个键**，逐项说明为什么其余的不写 ★
    权威键表共 69 个（从 libkonsoleprivate 的 Profile::Property 表导出）。
    只写真正有理由的：

      · ColorScheme=Frost      —— 唯一目的就是让配色自动生效
      · TerminalMargin=MARGIN  —— 复用系统的内容边距 token。实测 Konsole
        默认有效边距是 **0px**（KWin 报的 client 几何 + 截图逐像素量，
        文字首像素就落在客户区第一列），文字直接贴窗口边。
        诚实说明：这是排版/一致性改善，**不是缺陷修复** ——
        我一度以为「文字会被 Darkly 的 10px 圆角切到」，实测证否了：
        客户区下两角是方的（逐行量背景起始列，13 行内缩恒为 0），
        圆角只在标题栏那一侧。
    ★ TerminalCenter 试过，最后**没写** ★
    本意是与 TerminalMargin 配对（窗口宽不是字符宽整数倍时，把余量均分到两侧）。
    但我无法验证它到底有没有生效：想用截图量左右内缩，连续被四样东西污染 ——
    壁纸的暗像素被当成终端底色、客户区顶部其实是标签栏、铺不满的行末端被当成
    右边距、以及右侧的滚动条本身就是非背景像素。
    实测确实测到「请求 4 → 渲染 10、请求 9 → 渲染 18」这种非线性（说明有余量
    被折进内缩），但分不清那是 TerminalCenter 的功劳还是网格量化本来就有的。
    既然验证不了，就按本项目一贯的原则不写它 —— 只写能给出依据的键。

    ★ 明确不做的四件事（每条都有实测或原则依据）★
    1) **不做半透明+模糊。** 曾经写过 Opacity=0.9+Blur=true 并回退，理由在
       konsole_scheme() 里记着：KWin 对被缩放/平移的窗口拒绝模糊，而本主题的
       最小化动画同时用 Effect.Size 和 Effect.Translation（frost_minimize
       的 main.js 可查）—— 动画一开始模糊撤掉，透出的部分变成清晰的背景文字。
       另有独立理由：玻璃只给 chrome，终端正文是内容区。
       （我重新算过一轮「按对比度反推不透明度」：玻璃阶梯最不透的一档 0.35
         在 day 壁纸最亮处只给正文 2.41:1，而要让最暗的 ANSI 槽 SGR 90 保住
         4.5:1 需要 Opacity ≥ 0.94。但这套计算的前提是模糊始终在场 —— 前提错，
         结论作废。留档是为了下次别再算一遍。）
    2) **不跟随时段强调色。** 终端已经有一套颜色语言 —— ANSI，颜色在这里是
       输出的语义（错误红、路径蓝）。再叠一层「时刻」会是第三套语言，
       反而违反主题自己那条「颜色只承载两种语义」。而且 Konsole 是否热重载
       profile 从符号层面无法定论（有 QFileSystemWatcher 但看不出监视什么，
       没有 KDirWatch / reloadColorScheme），强调色停在旧值比不用更糟。
    3) **不写 Font。** kdeglobals [General] fixed 是空的，没有可跟随的 token；
       写死字体族（本机只有 Hack / Adwaita Mono / Liberation Mono）在别人
       机器上可能缺失。Konsole 自己的默认本来就跟随系统等宽字体。
    4) **不写 DimWhenInactive / ScrollBarPosition / CursorShape / BoldIntense。**
       前者会连正文一起压暗（内容区不该被压暗）；后三个是功能偏好不是主题事项，
       而且写的都会是默认值 —— 同「只写真正偏离默认的键」那条原则。
    """
    return (
        "[Appearance]\n"
        f"ColorScheme={NAME}\n"
        "\n"
        "[General]\n"
        f"Name={NAME}\n"
        "Parent=FALLBACK/\n"
        f"TerminalMargin={MARGIN}\n"
    )


def wallpaper_files():
    """生成四个时段的壁纸包。

    做成四个独立的 Wallpaper/Images 包（而不是一个包里放四张图）——
    Plasma 的 org.kde.image 一个包只认一张图，切换时段就是切换包。
    daylight.py 按太阳高度角决定用哪个。
    """
    from wallpaper import scene, PALETTES
    out = {}
    # ★ 跳过 login ★
    # 它只是 splash 的起点帧（已作为 contents/splash/images/login.svg 打进
    # look-and-feel 包里），daylight.py 的 pick() 永远不会返回 "login"。
    # 早先 for when in PALETTES 会把它一并生成成第 5 个桌面壁纸包 ——
    # 在「配置桌面 → 壁纸」里多出一个永远不会被自动选中的条目，纯属干扰。
    for when in (w for w in PALETTES if w != "login"):
        pkg = f"FrostScene-{when}"
        out[f"{pkg}/metadata.json"] = json.dumps({
            "KPlugin": {
                "Authors": [{"Name": AUTHOR}],
                "Id": pkg,
                "License": "CC0-1.0",
                "Name": (f"{NAME} · Login (neutral)" if when == "login"
                     else f"{NAME} · {when}"),
                # Description / Version 早先四张时段壁纸都缺 —— 系统设置的
                # 壁纸列表里就只有一个名字、没有副标题，和另外五个子包不一致。
                # 措辞用英文，同 metadata 的统一规矩。
                "Description": SCENE_BLURB[when],
                "Version": VERSION,
            },
            "KPackageStructure": "Wallpaper/Images",
        }, indent=4, ensure_ascii=False) + "\n"
        out[f"{pkg}/contents/images/3840x2400.svg"] = scene(when)
    return out


# ─────────────────── 布局：顶栏 + 底部任务栏 ───────────────────
def layout_js():
    return textwrap.dedent("""\
        // Frost 布局：顶部状态栏 + 底部全宽任务栏（参考图的排布）
        // 由 build-theme.py 生成

        // 有些属性是 Plasma 6 新增的，旧版会抛异常 —— 包一层不让整个脚本中断
        function trySet(obj, prop, value) {
            try { obj[prop] = value; } catch (e) { print("跳过 " + prop + ": " + e); }
        }

        // ═════════ 顶栏：Arch标 | 日期时间 | 托盘 + 电源 ═════════
        // 照参考图的排布。时钟和电源放这儿，底栏只留应用图标，
        // 两条各司其职，比全挤在底栏清爽。
        // ★ 幂等：先清掉本屏已有的横栏 ★
        // 这个脚本有两条入口，只有一条会自己清场：
        //   look-and-feel（plasma-apply-lookandfeel --resetLayout）→ 先丢旧 containment
        //   layout-templates（右键面板 → 添加面板）→ **纯追加**，什么都不清
        // 后者连点两次就叠出重复的顶栏/底栏（两条 offset 都是 0，直接压在一起）。
        // 四条边都占满时 ShellCorona::addPanel 会走到
        //   "Did not find a valid screen to place a new panel."
        // （该字符串在 plasmashell 6.7 的 **ASCII** 段里存在 —— qWarning 的
        //  const char* 是 ASCII，而 QStringLiteral 的键是 UTF-16，
        //  搜二进制两种编码都要试，只试一种会得到假阴性。）
        // 官方 emptyPanel 模板正是为此先遍历 panelIds/panelById 算 freeEdges。
        // 这里做等效的事，但语义不同：用户点的是「Frost 顶栏+Dock」这个**完整
        // 布局**，所以冲突的横栏该被替换而不是绕开 —— 绕开只会得到半套布局。
        // 打印被删的那条，不静默动用户的配置。
        // panelIds / panelById / remove 都确认存在于 plasmashell 6.7
        // （对照 notARealMethod → 0 命中）；remove() 没能在活 corona 上试过，
        // 所以包 try/catch —— 抛异常不该让整个布局脚本中断。
        for (var _i = 0; _i < panelIds.length; ++_i) {
            var _old = panelById(panelIds[_i])
            if (_old && (_old.location === "top" || _old.location === "bottom")) {
                print("Frost 布局：替换已有的 " + _old.location + " 面板")
                try { _old.remove() } catch (e) { print("  删除失败，可能会叠加: " + e) }
            }
        }

        var top = new Panel
        top.location = "top"
        // 顶栏 22px 配底栏 47px 是 2.1 倍差距 —— 两条同时在场的横栏差这么多
        // 会读成「一条正经栏 + 一条边角料」。
        //
        // ★ 这里的初值必须自己就是对的，不能指望 tweak.py 兜 ★
        // 活会话读到 gridUnit=18（evaluateScript print），于是：
        //   3.2 → round(57.6) = 58px，**比底栏 round(18*2.6)=47px 还厚** ——
        //   主次完全颠倒，设计要的是「细顶栏」。
        //   而且旧注释说「3.2 让比值降到 ~1.5」算不出任何真实数字：
        //   58/47=1.23，tweak.py 定死后是 60/34=1.76，旧值是 47/22=2.14。
        //
        // ★★ 改用固定像素，不再用 gridUnit 比例 ★★
        // 旧写法 top=round(gridUnit*1.9)、bar=round(gridUnit*2.6)，在
        // gridUnit=18 时得 34 / **47**。顶栏碰巧等于 tweak.py 的 34，
        // 底栏却比 tweak.py 的 BOTTOM_THICKNESS=60 少 13px ——
        // **两条入口对同一个设计值给出不同答案**，和当初 separateLaunchers
        // 那次「两条入口相反」是同一类缺陷。
        // 后果很具体：从「系统设置 → 全局主题」应用只跑布局脚本，
        // 得到 47px 的 dock；而登录钩子跑 --appearance-only，厚度那几行
        // 在守卫里不执行 —— 于是除非手工跑 apply-frost.sh，它永远是 47。
        // 旧注释里「与底栏 47px 的比值 1.38」正是把这个错值当成了设计值。
        // 跨文件常量门禁抓不到，因为这边写的是 gridUnit*2.6 而不是字面量。
        // 也不该用 gridUnit 比例：tweak.py 写的是固定 px，换台机器
        // gridUnit 一变，比例算出来的初值又会和 tweak.py 对不上。
        // 这两个数字必须与 tweak.py 的 TOP_THICKNESS / BOTTOM_THICKNESS 逐字相同。
        // 为什么不能只靠 tweak.py 定死：那几行在 tweak.py 里被
        // `if not APPEARANCE_ONLY:` 包着（tweak.py 的面板布局段 —— 不写行号，
        // 那一段被反复改过，写死的行号已经漂到别处去了），而登录钩子跑的是
        // `tweak.py --appearance-only` —— 所以从「系统设置 → 全局主题」
        // 应用之后，重新登录**也不会**把 58px 改回来，得手工跑 apply-frost.sh。
        // 底栏同理由 BOTTOM_THICKNESS 定 —— 早先这里的注释说「底栏改不动」，
        // 是错的，见 README #70/#73。
        top.height   = __FROST_TOP_THICKNESS__
        top.offset   = 0
        trySet(top, "floating", false)
        trySet(top, "lengthMode", "FillAvailable")

        // 左：Arch 徽标启动器
        // 注意图标名 —— Fluent 是仿 Windows 11 的图标集，它的 start-here* 是
        // Windows 徽标。要 Arch 标必须显式指定 distributor-logo-archlinux。
        var launcher = top.addWidget("org.kde.plasma.kickoff")
        launcher.currentConfigGroup = ["General"]
        launcher.writeConfig("icon", "distributor-logo-archlinux")
        launcher.writeConfig("compactMode", true)
        launcher.reloadConfig()

        top.addWidget("org.kde.plasma.panelspacer")

        // 中：时钟 —— 只显示时间
        //
        // 参考图那种「08 Jul 2021 | 9:56:55 PM」一行显示是 Plasma 5.22 的能力，
        // Plasma 6 已经没有了。实测结论：
        //   dateDisplayFormat="BesideTime"  → 无效值，日期完全不显示
        //   dateDisplayFormat="BelowTime"   → 日期另起一行，且面板要够高
        //   面板 30px + showDate=true       → 放不下，Plasma 直接丢掉日期
        //   （autoFontAndSize 开关都试过，结果一样）
        // 想要日期常驻，得把 top.height 提到 gridUnit*4.4 左右让两行放得下，
        // 但那样顶栏就厚了，反而不像参考图。这里选择保持细顶栏 + 只显示时间，
        // 日期点一下时钟就在日历里。
        var clock = top.addWidget("org.kde.plasma.digitalclock")
        clock.currentConfigGroup = ["General"]
        // ★ autoFontAndSize 必须是 true ★
        // 关掉它再指定 fontSize 是帮倒忙，实测：
        //   * Plasma 6.7 在细面板上**根本不读 fontSize**（8/10/11 渲染完全相同），
        //     也不读 boldText —— 字号只由面板高度决定。所以那行 fontSize 是死代码。
        //   * 更糟的是，关掉自动尺寸后 Plasma 选的字号不对齐整像素，
        //     12px 高的字每一根竖笔都摊在两列上、全是抗锯齿边缘，
        //     没有实心核心：峰值亮度只有 171（目标文字色是 233），
        //     90 分位对比 4.32:1 —— **低于正文 4.5:1 的阈值**。
        //   * 打开后字高不变（仍是 12px），但笔画从 1px 变成 2px、
        //     峰值到 234，对比度 4.32:1 → 14.77:1。
        // 也就是说：视觉尺寸一样，清晰度差 3.4 倍。
        clock.writeConfig("autoFontAndSize", true)
        clock.writeConfig("boldText", false)
        clock.writeConfig("showDate", false)
        clock.writeConfig("showSeconds", "Never")
        clock.reloadConfig()

        top.addWidget("org.kde.plasma.panelspacer")

        // 右：托盘 + 电源
        top.addWidget("org.kde.plasma.systemtray")

        var power = top.addWidget("org.kde.plasma.lock_logout")
        power.currentConfigGroup = ["General"]
        power.writeConfig("show_requestShutDown", true)
        power.writeConfig("show_lockScreen",      false)
        power.writeConfig("show_requestLogout",   false)
        // actionsOrder 里还有个容易漏掉的 requestLogoutScreen
        power.writeConfig("show_requestLogoutScreen", false)
        power.writeConfig("show_switchUser",      false)
        power.writeConfig("show_suspendToRam",    false)
        power.writeConfig("show_suspendToDisk",   false)
        power.writeConfig("show_requestReboot",   false)
        power.reloadConfig()

        // ═════════ 底栏：只放应用图标 ═════════
        var bar = new Panel
        bar.location = "bottom"
        bar.height   = __FROST_BOTTOM_THICKNESS__
        bar.offset   = 0
        trySet(bar, "floating", false)
        // 不设 alignment：下面 lengthMode 是 FillAvailable（撑满整屏宽），
        // alignment 此时没有作用面 —— 实测活着的面板同时是
        // lengthMode=fill 且 alignment=left，后者纯属摆设。
        // 图标居中靠的是两侧各一个 panelspacer（见下），不是 alignment。
        // （旁证：tweak.py 里唯一的 alignment 命中是 darklyrc 的 TitleAlignment，
        //   从不写面板 alignment，所以那个 left 只能来自这里。）
        // 万一以后改成 FitContent，这里再显式写 "center"。
        trySet(bar, "lengthMode", "FillAvailable")

        // 托盘和时钟都搬到顶栏后，底栏只剩几个图标。
        // 全宽栏配一小撮左对齐图标，1920px 只填 7%，读起来像「剩下的」。
        // 两侧各放一个弹性留白 → 图标居中，空白左右对称，才像有意为之。
        bar.addWidget("org.kde.plasma.panelspacer")

        var tasks = bar.addWidget("org.kde.plasma.icontasks")
        tasks.currentConfigGroup = ["General"]
        // ★ preferred:// 只是占位，装完由 tweak.py 解析成具体 .desktop ★
        // 布局脚本跑在 plasmashell 内部，没有 xdg-mime 可用，所以这里先写
        // 通用形式；tweak.py 会在安装/登录时把它换成本机的默认应用。
        // 为什么必须换掉：preferred:// 要查 mimeapps 才知道是哪个 .desktop，
        // **这一步是异步的**。解析完成前 Dolphin/Firefox 的窗口匹配不上启动器条目、
        // 和未固定应用一起排在后面；解析完成后 launchInPlace 把它们收进各自槽位，
        // 未固定应用被挤到末尾 —— 启动后约 10 秒发生一次重排。
        // 而任务栏**在重排后不会重新上报 iconGeometry**，KWin 手里那份就永久过期，
        // 最小化动画于是飞到相邻应用的图标上。
        // 实测（+3s/+14s/+25s 三次抓图 + 像素相关识别）证实了整条因果链，
        // 解析成具体路径后 +3s 起顺序就不再变、几何全部正确。
        // 详见 tweak.py 的 _resolve_preferred() 与 README 相应条目。
        tasks.writeConfig("launchers",
            "applications:systemsettings.desktop"
          + ",preferred://filemanager"
          + ",preferred://browser"
          + ",applications:org.kde.konsole.desktop")
        tasks.reloadConfig()
        // 排序三件套：让固定启动器的位置钉住，配合上面的解析一起消除重排
        // launchInPlace **不是配置键** —— applet 的 main.xml 里 32 个 entry
        // 没有它（实测解出 schema 逐个核对过）。它是 TasksModel 的 QML 属性：
        //     launchInPlace: tasks.iconsOnly && Plasmoid.configuration.sortingStrategy === 1
        // icontasks 下 iconsOnly 恒真，所以下面写 sortingStrategy=1
        // 就已经把它打开了，不需要也无法单独设。
        // ★ 必须 false —— 这一条是「最小化飞错图标」的真正开关 ★
        // Plasma 源码链（从 taskmanager.so 的 QRC 解出，zstd 压缩不是 zlib）：
        //   Task.qml:232-234  onIndexChanged 里
        //       if (!inPopup && !tasksRoot.vertical
        //               && !Plasmoid.configuration.separateLaunchers)
        //           tasksRoot.requestLayout();
        //   main.qml:565      requestLayout.connect(iconGeometryTimer.restart)
        //   main.qml:309      interval: 500
        //   main.qml:120      publishIconGeometries → requestPublishDelegateGeometry
        // 即：任务索引变化（重排）→ **仅当该键为 false** → 500ms 后把所有
        // 窗口任务的 iconGeometry 重新上报给 KWin。
        // 设成 true（= applet 的 KConfigXT 默认值）时该分支短路，
        // 重排后 KWin 手里的几何**永久过期** —— 这正是追了十几轮的
        // 「最小化飞到相邻 app 图标上」的根因（README #163）。
        // vinyl-theme 也写 false。tweak.py 同样写 false，两条入口必须一致。
        //
        // ★ 这里只写这一个键 —— 另外三个已按「上游都不设就别设」删掉 ★
        // 逐键对照（vinyl 的 layout.js 取自仓库原文，Breeze 取自本机
        //  /usr/share/plasma/layout-templates/org.kde.plasma.desktop.defaultPanel/）：
        //   | 键                     | schema 默认 | Breeze | vinyl | 这里 |
        //   | launchers              | 4 条含 preferred:// | 不设 | **设** | 设（已解析）|
        //   | separateLaunchers      | true   | 不设 | **显式 false** | **false** |
        //   | sortingStrategy        | 1      | 不设 | 不设 | 删 —— 我们写的就是 1，纯空操作 |
        //   | showOnlyCurrentDesktop | true   | 不设 | 不设 | 删 —— 真偏离，但上游都不设 |
        //   | indicateAudioStreams   | true   | 不设 | 不设 | 删 —— 我们写的就是 true，纯空操作 |
        //
        // 删 sortingStrategy 的安全性依据（不是凭「反正是默认值」）：
        // launchInPlace 是派生属性 `sortingStrategy === 1`，键不设时 KConfigXT
        // 返回默认值 1，`=== 1` 仍为真 —— 所以 launchInPlace 不变，无行为改变。
        // 也不会让 #163 复活：那个根因是 separateLaunchers，而它保留着。
        tasks.writeConfig("separateLaunchers", false)
        tasks.reloadConfig()

        // 右侧留白，与左侧对称，把图标夹在中间
        bar.addWidget("org.kde.plasma.panelspacer")
        """).replace("__FROST_TOP_THICKNESS__", str(TOP_THICKNESS)) \
            .replace("__FROST_BOTTOM_THICKNESS__", str(BOTTOM_THICKNESS))
    # 用 .replace 而不是 f-string：这段 JS 里满是 `{`，f-string 会当成字段。
    # 占位符命名成 __FROST_*__ 是为了落进 _check_js/_check_qml 的残留检查里 ——
    # 漏替换会在构建期硬失败，而不是产出一个写着占位符的 layout.js
    # （那种 layout.js 加载时报 ReferenceError，面板直接建不出来）。


# ─────────────────── 任务栏项 widgets/tasks.svg ───────────────────
# 任务栏那根「运行中」横杠不是 icontasks 的配置项，而是 Plasma 样式画的。
# 结构：6 种状态 × 9 宫格 × 4 个方位前缀
#   无前缀 = 底部面板   north- = 顶部面板   west-/east- = 左右竖栏
# 方位决定指示条画在哪条边上。

TASK_R    = RADIUS_SM   # 任务项圆角（同时决定边切片有多厚，指示条画在里面）
TASK_TILE = 24    # 中心块
BAR       = 3     # 指示条厚度
BAR_INSET = 3     # 指示条离任务项外沿的距离。
                  # 必须留 —— 贴边面板的任务项紧靠屏幕边缘，
                  # 指示条画在最外沿会被屏幕边裁掉一半。

# 每个状态：(底色 alpha, 指示条 alpha, 指示条用的配色类)
#
# 底色一律为 0 —— 任务项完全透明，只靠指示条表达状态。
# 参考主题（ddh4r4m/Arch）就是这么做的：normal-center 是 fill="none"，
# focus-center 是 opacity=".0032"，hover-center 的父级直接 opacity="0"。
# 图标背后加半透明色块会显得脏，也和「简约」相悖。
# 每个状态：(底色 alpha, 光晕 alpha, 横条 alpha, 配色类)
#
# 分两种表达：
#   光晕 —— 贴边的一层垂直渐变，从透明淡到有色，像图标下方透出来的光
#   横条 —— 清晰的实心细条
#
# 大部分状态只有光晕，**只有当前窗口才画横条**。这样一排图标能一眼分出主次；
# 之前所有状态都画同样的实心条，四个并排完全看不出哪个是活动窗口。
# 底色一律 0 —— 参考主题的 normal-center 是 fill="none"，
# hover/minimized/attention 的父级直接 opacity="0"，图标背后不垫任何色块。
# 所有状态的横条**几何完全相同**，只有透明度和颜色不同。
BAR_LEN = 0.60          # 横条长度占中心块的比例（attention 例外，见 _task_block）

# ── progress 的填充不透明度 ──
# progress 表达的是**范围**（还剩多少），而 minimized/normal/hover/focus 表达的是
# **状态**（是哪个）—— 两个不同维度，用同一根横条承载必然冲突。
# 原来 progress-bottom 和 hover-bottom 是**逐字节相同**的（等于根本没主题化），
# 而且横条只画在 bottom 切片里、左右各 TASK_R=7px 的圆角片不参与拉伸，导致
# **进度低于 23–32%（视任务项宽度）时完全不可见**。
# 改成填满九片：几何维度天然不同（面 vs 线），小宽度时圆角片自己就能显形，死区消失。
#
# alpha 由「可辨但不抢戏」倒推（强调色叠在面板底上，四时段实测）：
#   0.20 → 1.49–1.58:1   ← 取这个
#   0.35 → 2.07–2.29:1   过强，开始压过状态条
# 对照 normal 状态条对面板是 3.73–4.52:1 —— 保持 2.4–2.9 倍分离度，层级不含糊。
# 用 Highlight 而非 PositiveText(绿)：后者是四时段固定色，会引入第三种颜色语义。
PROGRESS_FILL = 0.20

TASK_STATES = {
    # ★ 几何必须全状态一致 ★  这是 Breeze 验证过的做法，
    # 它的 normal/hover/focus 路径完全相同（都是 m5-28h26v2h-26z），
    # 只有 opacity 不同（.15/.34/.45）。原因有两条，都是实测撞出来的：
    #
    # 1) **转场会跳。** Plasma 在状态间做交叉淡入淡出。同长横条变透明度是
    #    平滑混合；长度不同的两条淡入淡出会「跳」一下。而 normal↔hover 是
    #    鼠标每次划过都触发的最频繁转换 —— 把几何变化放这里最难看。
    #
    # 2) **状态是互斥的，hover 会覆盖 focus。** Plasma 用
    #    `taskPrefix(...).concat(taskPrefix("hover"))` 取**第一个存在**的前缀，
    #    没有 focus+hover 组合态。所以只要 focus 靠几何表达，
    #    鼠标一悬停在当前窗口上，它就会退回 hover 的几何 —— 横条突然变短。
    #
    # 透明度顺序：minimized < normal < hover < focus。
    # 这样悬停未聚焦项会**变亮**（明确反馈）；悬停已聚焦项只降 15%，
    # 几乎察觉不到 —— Breeze 也是同样的排序。
    #
    # attention 用颜色而非几何/亮度区分：新窗口会进这个状态，
    # 和 focus 撞在一起会让人以为有两个「当前窗口」。
    # ★ 这些数值是按「渲染后的实际对比」倒推的，不是拍脑袋定的 ★
    # 横条是半透明色叠在面板上，最终对比 = f(α, 强调色, 面板色)。
    # 四个时段的强调色和面板亮度都不同，其中 **day 最吃亏**
    # （壁纸亮 → 面板亮 → 和浅青强调色的落差最小，满档也只有 4.86:1）。
    # 所以阶梯按「最弱时段也要达标」来定：
    #
    #   状态        α      dawn   day   dusk  night   目标
    #   minimized  0.42    2.59  2.09  2.60  2.41    ≥2:1（可辨，明显最弱）
    #   normal     0.65    4.12  3.01  4.25  3.88    ≥3:1（WCAG 非文本下限）
    #   hover      0.80    5.47  3.72  5.65  5.20    明显强于 normal
    #   focus      1.00    7.64  4.86  7.99  7.32    满强调色
    #
    # 旧值（0.28/0.50/0.85）的问题：minimized 只有 1.65:1 等于看不见，
    # normal 在 day/night 达不到 3:1；而 hover→focus 只差 1.18×，
    # 悬停在当前窗口上时两态几乎无法区分。
    # 新阶梯的步长是 1.55× / 1.23× / 1.25×，单调且平缓 ——
    # hover 只比 normal 进一小步（它是反馈，不是状态变化），
    # focus 才是那一大步（它才是状态变化）。
    #
    # ★ 补一个更严的口径：最坏像素 ★
    # 上表的底色取的是**代表性面板亮度**。若改取「dock 区（壁纸最下 3%，
    # 已被 vigBot 暗角压过）里最亮的那个像素」，并按 GLASS_PANEL=0.22
    # 叠在 blur=16 的壁纸上合成，则：
    #   状态        dawn   day   dusk  night
    #   minimized   2.34  1.99  2.50  2.44
    #   normal      3.58  2.77  3.94  3.99
    #   hover       4.61  3.39  5.14  5.33
    #   focus       6.25  4.34  7.09  7.56
    # 也就是 **day/normal 在最坏像素下是 2.77，比 3:1 低约 8%**。
    #
    # ★ 为什么不把 normal 提上去 ★
    # 实测提到 0.71 能让 day/normal 到 3.01，但相邻档的 Weber 可辨度
    # （ΔL/L）normal→hover 会从 0.26 掉到 0.14（day），而 normal↔hover 是
    # 鼠标每次划过都触发的最频繁转换。用 8% 的对比度缺口换掉一半的
    # 悬停可辨度是坏交易，所以阶梯不动。
    # 真正的根因是 **day 壁纸偏亮**（同一根因还让弹窗正文有 34% 面积
    # 低于 4.5:1）—— 要修就修 day 场景的光照，一次解决两处，且不动阶梯。
    # 别再用「提高 α」来补这个缺口。
    #              透明度  配色类
    "minimized": (0.42, "ColorScheme-Highlight"),
    "normal":    (0.65, "ColorScheme-Highlight"),
    "hover":     (0.80, "ColorScheme-Highlight"),
    "focus":     (1.00, "ColorScheme-Highlight"),
    "attention": (1.00, "ColorScheme-NeutralText"),
    "progress":  (0.80, "ColorScheme-Highlight"),
}





# 方位前缀 → 指示条贴哪条边
TASK_EDGES = {"": "bottom", "north-": "top", "west-": "left", "east-": "right"}



def _task_block(prefix, state, ox, oy, bar_a, bar_cls, edge, bar_len=None,
                fill_alpha=None):
    """一个状态的完整 9 宫格。只在贴边的那一片里画横条。

    几何默认所有状态一致（长度 BAR_LEN、粗细 BAR），只有透明度和颜色变 ——
    这是刻意的，避免 normal↔hover↔focus 高频交叉时的几何抖动。

    ★ attention 是唯一的例外，用 bar_len 覆盖 ★
    它固定用 ColorScheme-NeutralText，而强调色随时段轮换 —— 颜色通道一个是
    常量一个是变量，必然在某些时段撞上。实测 dawn 时 NeutralText 与强调色
    只差 2.6° 色相（ΔE2000 15.7），而且它的最近邻不是 focus 而是 **hover**
    （ΔE2000 13.7，亮度等效强调色 alpha≈0.73，正落在 normal 0.65 与 hover 0.80
    之间）—— 「需要关注」读起来像「被鼠标划过」，这是语义事故。
    颜色维度已经用满了，只能靠**几何**把它拉开。
    README #35 原文写的就是「attention 不能和 focus 用同样的长度」，
    是后来那段未编号的"最终方案"统一成 0.60 才丢掉的 —— 这是恢复 #35 的原意。"""
    if bar_len is None:
        bar_len = BAR_LEN
    r, t = TASK_R, TASK_TILE
    p = f"{prefix}{state}"
    # 默认：图标背后不垫任何色块（见 #17，任务项底色一律 0.0）。
    # fill_alpha 是 progress 的唯一例外 —— 它要的是一块**面**而不是一根线。
    if fill_alpha is None:
        clear = "opacity:0;fill:currentColor"
        CLS = "ColorScheme-Text"
    else:
        clear = f"opacity:{fill_alpha};fill:currentColor"
        CLS = bar_cls
    bar  = f"opacity:{bar_a};fill:currentColor"
    BARC = bar_cls
    s = ""

    for which, (dx, dy) in {"tl": (0, 0), "tr": (r + t, 0),
                            "bl": (0, r + t), "br": (r + t, r + t)}.items():
        s += g_corner(f"{p}-{CORNER_NAME[which]}", ox + dx, oy + dy, which, r, clear, CLS)

    sides = {
        "top":    (f"{p}-top",    r,     0,     t, r),
        "bottom": (f"{p}-bottom", r,     r + t, t, r),
        "left":   (f"{p}-left",   0,     r,     r, t),
        "right":  (f"{p}-right",  r + t, r,     r, t),
    }
    for name, (eid, dx, dy, w, h) in sides.items():
        extra = ""
        if name == edge and fill_alpha is None:      # 填充模式不再画横条
            rad = BAR / 2                        # 圆头，硬方头在细条上显得生硬
            if name in ("bottom", "top"):
                bl = w * bar_len                 # 横条：长度沿 x
                bx = (w - bl) / 2
                by = (r - BAR - BAR_INSET) if name == "bottom" else BAR_INSET
                extra = (f'      <rect x="{bx:.1f}" y="{by}" width="{bl:.1f}" height="{BAR}" '
                         f'rx="{rad}" style="{bar}" class="{BARC}"/>\n')
            else:
                bl = h * bar_len                 # 竖条：长度沿 y
                by = (h - bl) / 2
                bx = BAR_INSET if name == "left" else (r - BAR - BAR_INSET)
                extra = (f'      <rect x="{bx}" y="{by:.1f}" width="{BAR}" height="{bl:.1f}" '
                         f'rx="{rad}" style="{bar}" class="{BARC}"/>\n')
        s += g_rect(eid, ox + dx, oy + dy, w, h, clear, CLS, extra=extra)

    s += g_rect(f"{p}-center", ox + r, oy + r, t, t, clear, CLS)
    return s


def tasks_svg(colors=None):
    colors = colors or _dark_palette()
    r, t = TASK_R, TASK_TILE
    S = 2 * r + t                     # 单个状态块的边长
    cols = len(TASK_STATES)           # 每行 6 个状态
    rows = len(TASK_EDGES)            # 每个方位一行
    W = cols * (S + GAP) + GAP
    H = rows * (S + GAP) + GAP + 24   # 末尾留给 hint

    s  = '<?xml version="1.0" encoding="UTF-8"?>\n'
    s += f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
    s += STYLE.format(**colors)

    for ri, (prefix, edge) in enumerate(TASK_EDGES.items()):
        oy = GAP + ri * (S + GAP)
        for ci, (state, (bar_a, bar_cls)) in enumerate(TASK_STATES.items()):
            ox = GAP + ci * (S + GAP)
            # attention 画满（1.00），其余保持 BAR_LEN=0.60。
            # 注意"画满"实际是「满切片」：两端各有 TASK_R=7px 的圆角片不参与拉伸，
            # 所以视觉上是 100% 减去两端 7px，与 60% 的差别依然一眼可辨。
            s += _task_block(prefix, state, ox, oy, bar_a, bar_cls, edge,
                             bar_len=1.00 if state == "attention" else None,
                             # progress 走填充模式：它是覆盖层，表达范围不表达状态
                             fill_alpha=PROGRESS_FILL if state == "progress" else None)

    # 内容边距：Plasma 用它决定图标离任务项边缘多远
    y2 = GAP + rows * (S + GAP)
    for i, e in enumerate(["normal-hint-top-margin", "normal-hint-bottom-margin",
                           "normal-hint-left-margin", "normal-hint-right-margin"]):
        s += plain_rect(e, GAP + i * 10, y2, 3, 3, "fill:#ff00ff")
    # ★ 必须有 hint-stretch-borders ★
    # 没有它时 FrameSvg 会**平铺**边切片而不是拉伸。横条占满整片时看不出来，
    # 一旦把横条做短（用长度区分状态），平铺就会把它重复成两段。
    # Breeze 有 6 个 widget 用这个提示（plasmoidheading / switch 等）。
    s += plain_rect("hint-stretch-borders", GAP + 50, y2, 3, 3, "fill:#00ff00")
    s += '</svg>\n'
    return s


# ──────────── 列表项 widgets/listitem.svg + 分隔线 widgets/line.svg ────────────
# 这两个决定了菜单/列表里每一行的选中高亮和分隔线 —— Kickoff 应用菜单、
# 系统托盘弹窗、各种下拉列表全都吃它们。不提供就会回退到 Breeze，
# 于是菜单里的选中块跟主题其它部分对不上。

LIST_R    = RADIUS_SM   # 列表行圆角
LIST_TILE = 24

# 状态 → (alpha, 配色类)
LIST_STATES = {
    "normal":  (0.00, "ColorScheme-Text"),        # 未选中 —— 完全透明
    "hover":   (0.16, "ColorScheme-Highlight"),   # 悬停
    "pressed": (0.34, "ColorScheme-Highlight"),   # 按下 / 选中
    "section": (0.06, "ColorScheme-Text"),        # 分组标题底
}

def _list_block(state, alpha, cls, ox, oy):
    r, t = LIST_R, LIST_TILE
    fill = f"opacity:{alpha};fill:currentColor"
    s = ""
    for which, (dx, dy) in {"tl": (0, 0), "tr": (r + t, 0),
                            "bl": (0, r + t), "br": (r + t, r + t)}.items():
        s += g_corner(f"{state}-{CORNER_NAME[which]}", ox + dx, oy + dy,
                      which, r, fill, cls)
    s += g_rect(f"{state}-top",    ox + r,     oy,         t, r, fill, cls)
    s += g_rect(f"{state}-bottom", ox + r,     oy + r + t, t, r, fill, cls)
    s += g_rect(f"{state}-left",   ox,         oy + r,     r, t, fill, cls)
    s += g_rect(f"{state}-right",  ox + r + t, oy + r,     r, t, fill, cls)
    s += g_rect(f"{state}-center", ox + r,     oy + r,     t, t, fill, cls)
    return s

def listitem_svg(colors=None):
    colors = colors or _dark_palette()
    r, t = LIST_R, LIST_TILE
    S = 2 * r + t
    W = len(LIST_STATES) * (S + GAP) + GAP
    H = S + GAP * 2 + 30

    s  = '<?xml version="1.0" encoding="UTF-8"?>\n'
    s += f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
    s += STYLE.format(**colors)

    for i, (state, (a, cls)) in enumerate(LIST_STATES.items()):
        s += _list_block(state, a, cls, GAP + i * (S + GAP), GAP)

    # 每个状态都要有自己的边距提示，否则 Plasma 用默认值，行高会不一致
    y2 = S + GAP * 2
    for i, state in enumerate(LIST_STATES):
        for j, side in enumerate(["top", "bottom", "left", "right"]):
            s += plain_rect(f"{state}-hint-{side}-margin",
                            GAP + (i * 4 + j) * 7, y2, 3, 3, "fill:#ff00ff")
    # 中心平铺提示：让中心块平铺而不是拉伸，避免圆角被抻变形
    s += plain_rect("hint-tile-center", W - 12, y2, 3, 3, "fill:#00ff00")
    # 分隔线
    s += (f'    <g id="separator" transform="translate({GAP},{y2 + 12})">\n'
          f'      <rect x="0" y="0" width="{LIST_TILE}" height="1" '
          f'style="opacity:0.16;fill:currentColor" class="ColorScheme-Text"/>\n'
          f'    </g>\n')
    s += '</svg>\n'
    return s


# widgets/line 的两个元素用途差别很大，必须分开给值：
#
#   horizontal-line —— **Kickoff 用它画弹窗的上边框**（不只是列表分组分隔线）。
#     这就是「菜单顶部那条框线」的真正来源 —— 排查了很久，因为
#     把 dialogs/background 整个改成全透明后线依然在，方向一直找偏。
#     定位方法：把 line.svg 染红，菜单上边线和侧栏竖线同时变红。
#     设为 0 —— 玻璃弹窗不需要一条硬边把自己和背景切开。
#
#   vertical-line —— 侧栏和内容区之间的竖分隔。**保留但要压低。**
#     实测：侧栏底和内容底的亮度差只有 1.5，两区靠底色完全分不出来，
#     所以这条线是唯一的分区依据，不能像横线那样直接删掉。
#     但 0.16 时亮度 72.4 / 底 43.9 = 1.65 倍尖峰，和刚去掉的横线一样刺眼。
#     压到 0.08 → 约 1.25 倍，够分区，不抢眼。
LINE_H_ALPHA = 0.00
LINE_V_ALPHA = 0.08

def line_svg(colors=None):
    """widgets/line —— 各处的分隔线。"""
    colors = colors or _dark_palette()
    s  = '<?xml version="1.0" encoding="UTF-8"?>\n'
    s += '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">\n'
    s += STYLE.format(**colors)
    s += (f'    <g id="horizontal-line" transform="translate(2,4)">\n'
          f'      <rect x="0" y="0" width="32" height="1" '
          f'style="opacity:{LINE_H_ALPHA};fill:currentColor" class="ColorScheme-Text"/>\n'
          f'    </g>\n')
    s += (f'    <g id="vertical-line" transform="translate(4,10)">\n'
          f'      <rect x="0" y="0" width="1" height="26" '
          f'style="opacity:{LINE_V_ALPHA};fill:currentColor" class="ColorScheme-Text"/>\n'
          f'    </g>\n')
    s += '</svg>\n'
    return s


# ─────────────── 通用控件 SVG（补齐回退到 Breeze 的那一批）───────────────
# Breeze 提供 43 个 widgets，只做 6 个的话其余全部回退，
# 结果就是「自己的玻璃面板 + Breeze 的其它一切」拼在一起，怎么调都不协调。
# 下面按可见度补最关键的 7 个。

WR = RADIUS_SM   # 通用控件圆角
WT = 24     # 中心块

def multi_state(elements, r=WR, tile=WT, colors=None,
                per_state_hints=True, tile_center=True, extra=""):
    """一张 SVG 里放多个 9 宫格状态。elements: [(名字, alpha, 配色类), ...]"""
    colors = colors or _dark_palette()
    S = 2 * r + tile
    W = max(len(elements), 1) * (S + GAP) + GAP
    H = S + GAP * 2 + 40

    s  = '<?xml version="1.0" encoding="UTF-8"?>\n'
    s += f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
    s += STYLE.format(**colors)

    for i, (name, alpha, cls) in enumerate(elements):
        ox, oy = GAP + i * (S + GAP), GAP
        fill = f"opacity:{alpha};fill:currentColor"
        for which, (dx, dy) in {"tl": (0, 0), "tr": (r + tile, 0),
                                "bl": (0, r + tile), "br": (r + tile, r + tile)}.items():
            s += g_corner(f"{name}-{CORNER_NAME[which]}", ox + dx, oy + dy, which, r, fill, cls)
        s += g_rect(f"{name}-top",    ox + r,        oy,            tile, r,    fill, cls)
        s += g_rect(f"{name}-bottom", ox + r,        oy + r + tile, tile, r,    fill, cls)
        s += g_rect(f"{name}-left",   ox,            oy + r,        r,    tile, fill, cls)
        s += g_rect(f"{name}-right",  ox + r + tile, oy + r,        r,    tile, fill, cls)
        s += g_rect(f"{name}-center", ox + r,        oy + r,        tile, tile, fill, cls)

    y2 = S + GAP * 2
    if per_state_hints:
        for i, (name, _, _) in enumerate(elements):
            for j, side in enumerate(["top", "bottom", "left", "right"]):
                s += plain_rect(f"{name}-hint-{side}-margin",
                                GAP + (i * 4 + j) * 7, y2, 3, 3, "fill:#ff00ff")
    if tile_center:
        s += plain_rect("hint-tile-center", W - 12, y2, 3, 3, "fill:#00ff00")
    s += extra
    s += '</svg>\n'
    return s


HL, TX, BTN, VBG = ("ColorScheme-Highlight", "ColorScheme-Text",
                    "ColorScheme-ButtonBackground", "ColorScheme-ViewBackground")

# 每个控件的状态定义。alpha 都压得比较低 —— 面板本身已经很透，
# 控件再厚重就会显脏，和玻璃质感冲突。



def calendar_svg(colors=None):
    """日历弹窗的内容底。
    ★ base 必须完全透明 ★ —— 外层 dialogs/background 已经画了半透明玻璃，
    这里再画一层底色就会两层叠加，在日历下方出现一条明显的色带。
    Breeze 的 base 是不透明的，所以不提供这个文件时就会看到那条带。
    只有两个元素，直接内联，不引额外的辅助函数。"""
    colors = colors or _dark_palette()
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="60" '
        'viewBox="0 0 120 60">\n'
        + STYLE.format(**colors) +
        # base 全透明：让外层玻璃透上来，不叠第二层底
        '    <g id="base">\n'
        f'      <rect x="{GAP}" y="{GAP}" width="80" height="30" rx="{RADIUS_SM}" '
        'style="opacity:0;fill:currentColor" class="ColorScheme-Background"/>\n'
        '    </g>\n'
        # event：日期下的小圆点，标记有日程的日子
        '    <g id="event">\n'
        f'      <circle cx="{GAP + 96}" cy="{GAP + 15}" r="4" '
        'style="opacity:0.9;fill:currentColor" class="ColorScheme-Highlight"/>\n'
        '    </g>\n'
        '</svg>\n')








# ─────────────────────────── 图标主题 ───────────────────────────
# 不可能手画 5000 个图标。策略是：
#   1) 自己生成最常见、最显眼的一类 —— 文件夹（Dolphin 里满屏都是）
#   2) 其余全部走 Inherits 继承链兜底
# 继承链按顺序查找，找不到的主题会被自动跳过，所以可以放心把没装的写在前面。
# Fluent 排最前 —— 参考图（ddh4r4m/Arch）用的就是这套；
# 装了 fluent-icon-theme 就自动接管，没装则退到 Papirus，再退到系统自带 breeze。
ICON_INHERITS = ("Fluent-dark,Fluent,"
                 "Papirus-Dark,Papirus,"
                 "breeze-dark,breeze,hicolor")

# 文件夹图标的回退色。只在「图标没有被 KIconLoader 注入配色」时才会用到 ——
# 正常情况下 .ColorScheme-Accent 会被换成当前强调色，所以这个值不决定观感。
# 取 DEFAULT_ACCENT（dusk 暖金）保持和主题基础配色一致。
FOLDER_FALLBACK = "#%02x%02x%02x" % DEFAULT_ACCENT

# 暗部靠叠黑，不靠第二个写死的颜色 —— 这是 Breeze 的做法。
# 早先这里是 FOLDER_ACCENT/FOLDER_SHADE 两个写死的紫色（#6e6ab4/#5450a0），
# 注释还写着「跟主题强调色一致」，但换强调色时根本不会跟 ——
# 结果是四个时段的强调色都在变，Dolphin 里的文件夹永远是那套已废弃的紫。
# 现在整只文件夹都是 currentColor，暗部只是压在上面的一层黑，
# 强调色一变，深浅关系自动保持。
FOLDER_SHADE_ALPHA = 0.22   # ≈ 原来 #5450a0 相对 #6e6ab4 的压暗量


def folder_svg(glyph=None):
    """扁平圆角文件夹。glyph 为可选的内嵌符号路径（区分文档/下载/图片等）。

    着色机制照搬 Breeze 的 places/48/folder.svg：
      * 形状全部 fill:currentColor + class="ColorScheme-Accent"
        → KIconLoader 会把 .ColorScheme-Accent 的 color 换成当前强调色
      * 暗部 = 在同一形状上叠一层不指定颜色的黑（fill-opacity）
      * 高光 = 叠一层白
    这样图标随时段自动改色，不需要重新生成文件。
    """
    g = ""
    if glyph:
        # ★ 字形用叠黑，不能用白 ★
        # 四个时段的强调色全是**亮色**（它们取自场景光源：晨桃/日青/暮金/夜靛），
        # 白色字形叠在亮底上实测只有 1.58~1.95:1，远低于非文本 UI 的 3:1 下限 ——
        # 表现为字形发糊、看不清是文档还是音乐。
        # 改成不指定 fill（即黑）配 0.70 不透明度：四档最差也有 5.58:1。
        # 这和文件夹暗部的做法是同一套（Breeze 的 places/48/folder.svg 也是叠黑），
        # 所以强调色一变，字形对比自动保持。
        # ★ translate 的 y 是 19 不是 17 ★
        # 17 让字形框中心落在 y=25，而正面 rect 是 y15..39、中心 y=27 ——
        # 10 个带字形的 places 图标**全族统一上偏 2px**。
        # 参照：Papirus 精确居中（29 vs 29）、breeze-dark 差 0.5px。
        # 改成 19 后六个字形中心 27.00/26.55/27.00/26.45/27.00/27.00，
        # 全部落在正面中心 ±0.55 内；最低点距下沿仍有 7px，不撞 rx=3.5 圆角。
        g = (f'  <g transform="translate(16,19)" '
             f'fill-opacity="0.70">\n    {glyph}\n  </g>\n')
    back = ('M6 12a3 3 0 0 1 3-3h9.2a3 3 0 0 1 2.1.9l2.8 2.8a3 3 0 0 0 2.1.9'
            'H39a3 3 0 0 1 3 3v3H6z')
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">
  <defs>
    <style type="text/css" id="current-color-scheme">.ColorScheme-Accent {{ color: {FOLDER_FALLBACK}; }}</style>
  </defs>
  <!-- 后层：文件夹背板（露出的上沿），随强调色 -->
  <path d="{back}" fill="currentColor" class="ColorScheme-Accent"/>
  <!-- 背板压暗：不指定 fill 即为黑，靠透明度做深浅，因此仍跟随强调色 -->
  <path d="{back}" fill-opacity="{FOLDER_SHADE_ALPHA}"/>
  <!-- 前层：主体 -->
  <rect x="6" y="15" width="36" height="24" rx="3.5" fill="currentColor" class="ColorScheme-Accent"/>
  <!-- 顶部高光，做出一点厚度 -->
  <rect x="6" y="15" width="36" height="1" rx="0.5" fill="#ffffff" fill-opacity="0.14"/>
{g}</svg>
"""

# 各类文件夹的内嵌符号（相对 16,17 原点，16x16 视野）
GLYPHS = {
    "folder-documents": '<path d="M3 0h7l3 3v13H3z" opacity=".9"/>',
    "folder-download":  '<path d="M8 1v8M4.5 6.5 8 10l3.5-3.5M3 13h10v2H3z"'
                        ' stroke="#000" stroke-width="1.8" fill="none"'
                        ' stroke-linecap="round" stroke-linejoin="round" opacity=".9"/>',
    # ★ 天空底板的 opacity 乘数 0.25 → 0.7 ★
    # 这是 folder-videos 那条「机身不能带 opacity 乘数」（见下面它的注释）
    # 的**同一个 bug，只是从没在这里修过**。
    # 0.25 x 组的 0.70 = 有效 α 仅 0.175 —— 比 videos 当年被判「认不出是
    # 摄像机」的 0.245 还低。实测四时段中位对比 1.45–1.47:1，48px 下
    # 达 3:1 的像素只有 34.2%，天空整块几乎看不见，图标退化成
    # 「一座山加一个点」，读不出是相框。
    # 不能像 videos 那样直接删掉乘数：图片图标**需要**天空比山浅，
    # 否则整块实心、山和太阳消失。所以要找一个同时满足两个条件的值。
    # 实测（sRGB 合成，四时段 night/dawn/day/dusk）：
    #   乘数  有效α   对底色对比            天空↔山内部对比
    #   0.25  0.175  1.45 1.47 1.46 1.47   3.87   ← 现状，不达标
    #   0.65  0.455  2.89 3.07 3.02 3.06   1.94   ← night 差一点
    #   0.70  0.490  3.17 3.40 3.34 3.39   1.76   ← 取这个
    #   0.80  0.560  3.84 4.20 4.10 4.19   1.46   ← 内部开始糊
    # 0.70 是四时段全部 ≥3:1 的最小值，同时把山留在 1.76 上清楚可读。
    "folder-pictures":  '<path d="M2 3h12v10H2z" opacity=".7"/>'
                        '<circle cx="5.5" cy="6" r="1.5"/>'
                        '<path d="M2 12l3.5-4 2.5 2.6L11 6l3 6z"/>',
    "folder-music":     '<path d="M6 12V3l7-1.4V10" fill="none" stroke="#000"'
                        ' stroke-width="1.8" stroke-linecap="round"/>'
                        '<circle cx="4.5" cy="12" r="2.2"/><circle cx="11.5" cy="10" r="2.2"/>',
    # 房子：屋顶 + 主体 + 门。原先 user-home 直接复用通用文件夹，
    # 于是 Places 侧栏里 Home 和普通文件夹长得一模一样。
    "user-home":        '<path d="M8 0.8 L15.2 7.2 L13 7.2 L13 15.2 L9.6 15.2'
                        ' L9.6 10.6 L6.4 10.6 L6.4 15.2 L3 15.2 L3 7.2 L0.8 7.2 Z"/>',
    # ★ 机身不能带 opacity 乘数 ★
    # 原来写的是 opacity=".35"，与字形组自身的 0.70 相乘 → 有效 α 仅 **0.245**，
    # 四时段实测 1.69/1.72/1.73/1.73:1。48px 下字形共 118px，达 3:1 的只有
    # 16px(14%)，可见质心 28.9 而图标中心是 24.0 —— 图标退化成贴在右缘的
    # 一个镜头梯形，认不出是摄像机。
    # README #61 只核验了裸 0.70 那一层，漏审了子元素自带的乘数。
    # 去掉乘数后吃组的 0.70（5.60–6.44:1）。不是"提到 0.60" —— 实测那样只有
    # 2.73–2.89，仍不达 3:1；下限得 0.675，那已经和 0.70 没区别了。
    "folder-videos":    '<path d="M2 3h9v10H2z"/><path d="M11 7l4-2.5v7L11 9z"/>',
    # 显示器：屏幕 + 颈 + 底座。
    # 为什么要自己画：user-desktop 在 Frost 里原本不存在，于是沿
    # Inherits=Fluent-dark,Fluent,Papirus-Dark,... 一路回落，实测命中
    # /usr/share/icons/Papirus-Dark/16x16/places/user-desktop.svg ——
    # 那份用了 5 个硬编码颜色（#ff9800 橙 / #f44336 红 / #4caf50 绿 /
    # #4285f4 Google 蓝 / #dfdfdf 灰），五个色相既不跟强调色也不随时段，
    # 直接违反「颜色只承载两种语义」这条原则。Places 侧栏里它就挨着
    # 自绘的 Home 和文件夹，是全列表唯一一个花的。
    #（一次审计说它落到「Fluent 的品牌蓝彩色插画」—— 归属说错了，
    #  Fluent 链上根本没有 user-desktop，是 Papirus-Dark 接住的。
    #  自己把继承链每一环都 find 一遍就看到了。）
    # 轮廓刻意做成「宽而扁 + 底座」，和 folder-documents 的「窄而高的纸」
    # 在剪影层面就能区分；纵向跨度 1.6..14.4 → 竖中心 8.0，与 user-home
    # （0.8..15.2，竖中心 8.0）对齐。锐角矩形跟 folder-videos 一致。
    "user-desktop":     '<path d="M1.2 1.6h13.6v9.6H1.2z"/>'
                        '<path d="M6.6 11.2h2.8v1.8H6.6z"/>'
                        '<path d="M3.6 13h8.8v1.4H3.6z"/>',
    "folder-downloads": None,   # 别名，见下
}

def tray_mono_icons():
    """托盘里的彩色应用图标 → 自绘单色版。

    ── 为什么需要这个 ──
    实测顶栏托盘里 12 个图标，9 个是 Fluent 的 22px 单色线稿（视觉尺寸中位
    73%、笔画 1–2px），另外 3 个是应用自己的彩色图标，混在里面很扎眼，
    也违反 Frost 的原则「颜色只承载语义」—— 品牌蓝不承载任何语义。

    ── 但只有一个能修 ──
    托盘项分两类，用 `qdbus6 <svc> /StatusNotifierItem …IconName` 一问便知：
      * 声明了 IconName 的（EasyEffects = com.github.wwmm.easyeffects）
        → 走图标主题查找，Frost 在继承链最前面，能覆盖 ✅
      * 直接推送像素图的（Telegram、claude-desktop、fcitx5）
        → 图标数据由应用经 DBus 送来，根本不查主题，**改不了** ❌
    所以这里只收第一类。想让第二类统一，只能去应用自己的设置里找
    「单色托盘图标」选项，或者把它们收进折叠区。

    ── 绘制惯例（照抄 Fluent 22/panel/ 的写法，实测得出）──
      * viewBox 0 0 22 22，有效内容约 16×16（73%，与 9 个合规图标的中位数一致）
      * `.ColorScheme-Text` + fill="currentColor" —— 填充路径，不是描边
      * 线宽 1px、圆头（rx=0.5）
    """
    def wrap(body):
        return (
            '<svg width="22" height="22" viewBox="0 0 22 22" '
            'xmlns="http://www.w3.org/2000/svg">\n'
            ' <defs>\n'
            '  <style id="current-color-scheme" type="text/css">'
            '.ColorScheme-Text { color:#dedede; }</style>\n'
            ' </defs>\n' + body + '</svg>\n')

    KNOB_W = 4.2                      # 滑块宽；见下方尺寸推导

    def fader(cx, knob_y):
        """一条推子：1px 圆头竖轨 + 一个滑块。"""
        return (
            f' <rect class="ColorScheme-Text" x="{cx-0.5}" y="3.5" width="1" '
            f'height="15" rx="0.5" fill="currentColor"/>\n'
            f' <rect class="ColorScheme-Text" x="{round(cx-KNOB_W/2,2)}" '
            f'y="{knob_y-1.3}" width="{KNOB_W}" height="2.6" rx="1.3" '
            f'fill="currentColor"/>\n')

    # 三条推子高低错落 —— 均衡器的视觉签名，一眼能认出是音频效果器。
    #
    # 尺寸是倒推出来的，不是随手定的：
    #   轨道 x=5.5/11/16.5，滑块宽 4.2 → 最宽处 3.4..18.6 = 15.2px
    #   轨道 y=3.5..18.5 = 15px
    #   → 视觉尺寸 max(15.2,15)/22 ≈ 69%，光栅化后实测落在 73%，
    #     正好是 9 个合规托盘图标的中位数（区间 64–82%）。
    #   第一版轨道放在 x=5/11/17、滑块 4.6，实测 82% —— 在区间上沿，
    #   同一排里显得偏大。收窄后墨量 13.9%→更贴近中位 11.9%。
    # 滑块间距校验：轨道1 滑块右缘 7.6，轨道2 滑块左缘 8.9，留 1.3px 空隙，
    # 22px 下仍能看出是三条独立推子。
    easyeffects = wrap(fader(5.5, 7.5) + fader(11, 13.5) + fader(16.5, 9.5))

    return {"status/22/com.github.wwmm.easyeffects.svg": easyeffects}


def kwin_effect_files():
    """最小化动画 = Breeze 的 squash 逐行照抄 + 一件事：动画期间提层。

    ── 为什么需要提层（这次的理由是对的）──
    实测窗口层级：Claude=5(最顶) / konsole=4 / dolphin=3 / systemsettings=2 /
    firefox=1，全部 keepAbove=false。最小化任何一个非顶层窗口时，
    它按**自己的堆叠位置**绘制 —— 于是从顶层窗口的下面穿过去，
    用户只看得见露在外面的部分。三次报告，措辞一致：
        「所有应用的最小化又从 claude app 下面过去了 我只能看到露出的部分」

    ★ 我曾用错误的理由加过它、又用错误的推论删过它 ★
    · 加的时候理由写成「窗口一旦 minimized，KWin 会把它从正常堆叠顺序里
      摘出去」。**那句话是假的**，实测证否（`workspace.stackingOrder` 里
      最小化的窗口留在原位、仍是最顶）。
    · 但删的时候我把「那句解释是假的」推成了「提层不需要」—— **不成立**。
      窗口留在原位恰恰意味着：它**在谁下面就画在谁下面**。
      「需不需要提层」取决于「离场的窗口该不该画在最上面」，
      与那句机制解释是两件事，我把它们混为一谈了。
    教训：**证否一个理由 ≠ 证否那个结论。** 换个理由重新检查，别顺手删。

    ── 与上游的关系，说清楚 ──
    | | Breeze | vinyl-theme | 这里 |
    |---|---|---|---|
    | 自带 kwin 特效 | 无 | 无 | 有（上游 squash 181 行的衍生）|
    (不写本文件自己的行数：早先写「180 行」已经漂过一次，改完头部注释又漂到
     196 —— 紧挨着可编辑文本的写死计数必然过期。差异请直接 diff 上游那份。)
    | 最小化动画 | squash | squash | squash 逐行照抄 |
    | 动画期间提层 | 无 | 无 | **有** |
    16 个自带 JS 特效里使用 `setElevatedWindow` 的确实是 **0** 个 ——
    这是一处**刻意偏离**。理由不是「上游漏了」，而是：
    macOS / Windows 的最小化动画都画在所有窗口之上，用户最早提的需求
    就是「类似 mac 或者 win 都是缩小到底部栏」；而 KWin 的 stock 行为
    让离场动画被挡住一半，观感上像窗口「钻进去」而不是「飞走」。
    `setElevatedWindow(EffectWindow*, bool)` 在 libkwin 里是导出的
    （`nm -D` 命中 `setElevatedWindowEPNS_12EffectWindowEb`），是正规接口。

    ── 提层不产生第二种动画 ──
    曲线、时长、三条通道全不变，只是保证那**一种**动画始终画在最上层。
    #163 的碰撞守卫才是产生两种动画的东西 —— 它没有回来，也不会回来。

    ── 与 squash 的差异，一条不多 ──
    | 项 | squash | 这里 |
    |---|---|---|
    | 缓动 | 顶层 InCubic（恢复 OutCubic）| 一样 |
    | 时长 | animationTime(250) | 一样 |
    | 动画 | Size + Translation + Opacity | 一样 |
    | 无任务栏条目 | 直接 return | 一样 |
    | 重入 | redirect 掉头，失败才 cancel | 一样 |
    | WindowForceBlurRole | 设 | 一样 |
    | **提层** | **无** | **setElevatedWindow(true/false)** |

    ── 继承 squash 的已知代价（不修，修了就又要分支）──
    · 上游 iconGeometry 在任务栏重排后会过期，偶尔飞向相邻图标（README #163）
    · 「可读性风险」峰值 0.1584（README #129 重算值）
    """
    NAME = "frost_minimize"
    meta = {
        "KPlugin": {
            "Id": NAME,
            "Name": "Frost Minimize",
            "Description": "Breeze squash, elevated during the animation so the "
                               "outgoing window is not hidden behind others.",
                "Version": VERSION,
            "Authors": [{"Name": AUTHOR}],
            "License": "GPL-2.0-or-later",
            "Category": "Appearance",
            "EnabledByDefault": True,
        },
        "KPackageStructure": "KWin/Effect",
        "X-Plasma-API": "javascript",
        "X-KWin-Exclusive-Category": "minimize",
    }

    main_js = r'''"use strict";

/*
    This file is part of the KDE project.

    SPDX-FileCopyrightText: 2018 Vlad Zahorodnii <vlad.zahorodnii@kde.org>
    SPDX-FileCopyrightText: 2026 xhhcn

    SPDX-License-Identifier: GPL-2.0-or-later

    ── 本文件的来历 ──
    逐行照抄自 KWin 自带的 squash 特效
    （/usr/share/kwin-wayland/effects/squash/contents/code/main.js）。
    实质修改只有一处：加入 elevate() 与五处调用，让离场动画画在最上层。
    另外去掉了上游在 animate() 之前重复的第二次
    setData(WindowForceBlurRole, true) —— 两个槽的槽首都已写过同值，纯冗余。
    其余差异只是重命名与排版。（diff 可复核，别把「唯一」写成绝对。）
    既然是 squash 的衍生作品，许可与署名必须跟随原作 ——
    此前这里声明成 MIT 且删掉了原作者署名，那是错的，已更正。
*/

/*  Frost Minimize —— Breeze 的 squash 逐行照抄，只多一件事：动画期间提层。
 *
 *  为什么：实测窗口层级 Claude=5(最顶) / konsole=4 / dolphin=3 /
 *  systemsettings=2 / firefox=1（全部 keepAbove=false）。最小化一个非顶层
 *  窗口时，它按自己的堆叠位置绘制 —— 从顶层窗口下面穿过去，只看得见
 *  露在外面的部分。macOS / Windows 的最小化动画都画在所有窗口之上。
 *
 *  除提层之外与 squash 逐项相同。完整对照见 build-theme.py 的
 *  kwin_effect_files() 文档字符串。
 */

const frostMinimize = {
    duration: animationTime(250),

    loadConfig: function () {
        frostMinimize.duration = animationTime(250);
    },

    /* ★ 必须 try/catch ★ 它在 animate() 之前。若 setElevatedWindow 在某个
       KWin 版本上不可用而抛异常，整个槽函数会中止 —— 结果是**一点动画都没有**，
       比被挡住一半糟得多。提层是加固，不是前提。 */
    elevate: function (window, on) {
        try {
            effects.setElevatedWindow(window, on);
        } catch (e) {
            // 不支持就算了，动画照常跑
        }
    },

    slotWindowMinimized: function (window) {
        if (effects.hasActiveFullScreenEffect) {
            return;
        }
        window.setData(Effect.WindowForceBlurRole, true);
        frostMinimize.elevate(window, true);

        // 没有任务栏条目就不做动画 —— squash 的行为，照抄
        var iconRect = window.iconGeometry;
        if (iconRect.width == 0 || iconRect.height == 0) {
            frostMinimize.elevate(window, false);
            return;
        }

        if (window.unminimizeAnimation) {
            if (redirect(window.unminimizeAnimation, Effect.Backward)) {
                return;
            }
            cancel(window.unminimizeAnimation);
            delete window.unminimizeAnimation;
        }
        if (window.minimizeAnimation) {
            if (redirect(window.minimizeAnimation, Effect.Forward)) {
                return;
            }
            cancel(window.minimizeAnimation);
        }

        var windowRect = window.geometry;
        window.minimizeAnimation = animate({
            window: window,
            curve: QEasingCurve.InCubic,
            duration: frostMinimize.duration,
            keepAlive: false,
            animations: [
                {
                    type: Effect.Size,
                    from: { value1: windowRect.width, value2: windowRect.height },
                    to:   { value1: iconRect.width,   value2: iconRect.height }
                },
                {
                    type: Effect.Translation,
                    from: { value1: 0.0, value2: 0.0 },
                    to: {
                        value1: iconRect.x - windowRect.x -
                            (windowRect.width - iconRect.width) / 2,
                        value2: iconRect.y - windowRect.y -
                            (windowRect.height - iconRect.height) / 2
                    }
                },
                {
                    type: Effect.Opacity,
                    from: 1.0,
                    to: 0.0
                }
            ]
        });
    },

    slotWindowUnminimized: function (window) {
        if (effects.hasActiveFullScreenEffect) {
            return;
        }
        window.setData(Effect.WindowForceBlurRole, true);
        frostMinimize.elevate(window, true);

        var iconRect = window.iconGeometry;
        if (iconRect.width == 0 || iconRect.height == 0) {
            frostMinimize.elevate(window, false);
            return;
        }

        if (window.minimizeAnimation) {
            if (redirect(window.minimizeAnimation, Effect.Backward)) {
                return;
            }
            cancel(window.minimizeAnimation);
            delete window.minimizeAnimation;
        }
        if (window.unminimizeAnimation) {
            if (redirect(window.unminimizeAnimation, Effect.Forward)) {
                return;
            }
            cancel(window.unminimizeAnimation);
        }

        var windowRect = window.geometry;
        window.unminimizeAnimation = animate({
            window: window,
            curve: QEasingCurve.OutCubic,
            duration: frostMinimize.duration,
            keepAlive: false,
            animations: [
                {
                    type: Effect.Size,
                    from: { value1: iconRect.width,   value2: iconRect.height },
                    to:   { value1: windowRect.width, value2: windowRect.height }
                },
                {
                    type: Effect.Translation,
                    from: {
                        value1: iconRect.x - windowRect.x -
                            (windowRect.width - iconRect.width) / 2,
                        value2: iconRect.y - windowRect.y -
                            (windowRect.height - iconRect.height) / 2
                    },
                    to: { value1: 0.0, value2: 0.0 }
                },
                {
                    type: Effect.Opacity,
                    from: 0.0,
                    to: 1.0
                }
            ]
        });
    },

    slotWindowAdded: function (window) {
        window.minimizedChanged.connect(() => {
            if (window.minimized) {
                frostMinimize.slotWindowMinimized(window);
            } else {
                frostMinimize.slotWindowUnminimized(window);
            }
        });
    },

    /* 动画结束：放回堆叠顺序、还原强制模糊。
       忘了取消提层，恢复出来的窗口会永远浮在最上层 —— 症状很隐蔽，
       只有它本该被别的窗口盖住时才看得出来。 */
    animationFinished: function (window) {
        frostMinimize.elevate(window, false);
        window.setData(Effect.WindowForceBlurRole, null);
    },

    init: function () {
        effect.configChanged.connect(frostMinimize.loadConfig);
        effect.animationEnded.connect(frostMinimize.animationFinished);
        effects.windowAdded.connect(frostMinimize.slotWindowAdded);
        for (const window of effects.stackingOrder) {
            frostMinimize.slotWindowAdded(window);
        }
    }
};

frostMinimize.init();
'''

    return {
        f"{NAME}/metadata.json": json.dumps(meta, indent=4, ensure_ascii=False) + "\n",
        f"{NAME}/contents/code/main.js": main_js,
    }


def icon_theme_files():
    """返回 {相对路径: 内容}。"""
    out = {}
    out["index.theme"] = textwrap.dedent(f"""\
        [Icon Theme]
        Name={NAME}
        Comment=Frost — hand-drawn folders, everything else inherited
        Inherits={ICON_INHERITS}
        # ★ 没有这一行，KIconLoader 根本不会给图标注入配色 ★
        # KIconTheme::followsColorScheme() 读的就是它。缺了它，SVG 里的
        # <style id="current-color-scheme"> 和 .ColorScheme-* 类形同虚设，
        # 永远渲染成写死的回退色 —— 表现为「文件夹颜色不跟主题变」。
        # breeze / breeze-dark / Papirus-Dark / Fluent-dark 四套全都声明了 true。
        FollowsColorScheme=true
        Directories=places/scalable,apps/scalable,categories/scalable,status/22

        # ★ MinSize=32，不是 16 ★
        # 本主题的文件夹是一张 48px 设计缩下去用的。声明 MinSize=16 会让它
        # 在**所有**尺寸抢赢继承链，包括 Dolphin 侧栏的 22px ——
        # 后果有两个，都实测过：
        #   1) 22px 下内嵌字形（文档/下载/音乐/图片）糊成一团，16px 更甚
        #   2) 视觉语言打架：我的文件夹是实心填色，而同一列表里的
        #      Desktop / Trash / Network 落到 Fluent 的 22/places/（单色线稿），
        #      实心色块和细线框并排，一眼就不对
        # Fluent 自己是按尺寸分层的：16/22/24 是单色线稿，scalable 才是彩色插画。
        # 跟着这个约定走：小尺寸（UI 外壳）交给 Fluent 线稿，
        # 32px 以上（内容区）才用我的强调色文件夹。侧栏和图标视图各自内部一致。
        [places/scalable]
        Size=48
        MinSize=32
        MaxSize=512
        Context=Places
        Type=Scalable

        # categories/scalable 默认是空的 —— 分类图标交给继承链（见 install-frost.sh）。
        # 但这一行必须留着：FROST_COLOR_CATEGORIES=1 时图标会装进这个目录，
        # 而**目录存在却没在 Directories= 里声明，里面的图标永远不会被使用**，
        # 开关会变成静默失效。反过来（声明了空目录）只是多一次空查找，无害。
        [categories/scalable]
        Size=48
        MinSize=16
        MaxSize=512
        Context=Categories
        Type=Scalable

        # ★ apps/scalable 必须留着，别再动它 ★
        # 它在 out/ 里是空的（build-theme.py 不往里写），所以看起来像
        # 「声明了一个不存在的目录」—— 我据此删过一次，**那是错的**。
        # 真正的写入方在**安装期**：install-frost.sh 里
        #     mkdir -p "$DEST/icons/Frost/apps/scalable"
        #     python3 … "$ARCH_LOGO" "$DEST/icons/Frost/apps/scalable"
        # 生成 start-here-archlinux.svg 与它的 -symbolic 变体、archlinux.svg、
        # distributor-logo-archlinux.svg —— 顶栏那个 Arch 徽标就是它们。
        # （注意：这段模板是 f-string，注释里不能出现裸的花括号。）
        # 删掉声明的后果正是下面 categories 那段注释警告的：
        # 目录存在却不在 Directories= 里 → 里面的图标永远不被使用 → 徽标消失。
        # 教训：判断「有没有东西往这个目录写」，不能只看构建产物 out/，
        # 安装脚本也是生成方。
        # 尺寸段用 Size=48/MinSize=16 是**故意**的：Arch 徽标是我们自己的
        # 品牌图标，本来就该在所有尺寸胜出。下面那段「只覆盖 20–26px」
        # 描述的是 [status/22]，不是这一段，别看串行。
        [apps/scalable]
        Size=48
        MinSize=16
        MaxSize=512
        Context=Applications
        Type=Scalable

        # ★ 只覆盖 20–26px，绝不覆盖大尺寸 ★
        # 这里放的是「本该是彩色应用图标、但出现在托盘里」的那些图标的单色版。
        # 托盘按 22–24px 取图标 → 命中这里；应用菜单/任务栏按 48px 取 → 落回
        # Fluent 的彩色版。同一个应用在菜单里是彩色、在托盘里是单色，各自内部一致。
        # 手法和 places/scalable 的 MinSize=32 是同一个：用尺寸桶做分工，
        # 而不是整体抢赢继承链。
        [status/22]
        Size=22
        MinSize=20
        MaxSize=26
        Context=Status
        Type=Scalable
        """)

    out.update(tray_mono_icons())

    # 通用文件夹 + 常见特化
    named = {
        "folder":            None,
        "folder-blue":       None,
        "inode-directory":   None,
        "user-home":         GLYPHS["user-home"],
        "folder-documents":  GLYPHS["folder-documents"],
        "folder-download":   GLYPHS["folder-download"],
        "folder-downloads":  GLYPHS["folder-download"],
        "folder-pictures":   GLYPHS["folder-pictures"],
        "folder-images":     GLYPHS["folder-pictures"],
        "folder-music":      GLYPHS["folder-music"],
        "folder-sound":      GLYPHS["folder-music"],
        "folder-videos":     GLYPHS["folder-videos"],
        "folder-video":      GLYPHS["folder-videos"],
        "user-desktop":      GLYPHS["user-desktop"],
    }
    # ★ 这里曾经有第二个 "user-home" 键，把 GLYPHS 的字形硬抄了一遍 ★
    # Python 后键覆盖前键，所以真正生效的是那份抄本 —— 改 GLYPHS 不生效，
    # 两份还会静默漂移。README #101 一度声称修好了，其实只删了别处的重复，
    # 这一处活到了现在（用 ast 遍历字典键才查出来）。
    # 现在唯一来源是 GLYPHS["user-home"]（上面第 4 行），去重后逐字节比对过
    # 生成的 user-home.svg：与旧输出完全一致，纯重构。
    # 教训：重复键在 Python 里不报错、grep 也看不出「哪个生效」——
    # 这类缺陷只能靠 ast 级别的检查发现，已并入构建期门禁。
    for name, glyph in named.items():
        svg = folder_svg(glyph=glyph)
        out[f"places/scalable/{name}.svg"] = svg
    return out


# ─────────────────────────── 输出 ───────────────────────────
def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


# ═══════════════════════════════════════════════════════════════════════
#  构建期对比度门禁
#
#  为什么需要它：本项目出现过三条根因完全相同的可访问性缺陷 ——
#    · [Colors:Selection] 的 8 个前景键从没被量过（白字压浅强调色，1.75:1）
#    · GLYPHS 子元素自带的 opacity 乘数从没被量过（folder-videos 有效 α 0.245）
#    · Konsole 只量了 Color1–7 的 normal 档（Color0Intense 3.78 漏网）
#  每一次单独量的时候都算对了，缺的是「量哪些」的完备性。
#  规则数量已经超过人能可靠抽查的规模，所以改成机器在每次构建时全量跑，
#  不达标直接让构建失败 —— 缺陷不可能再溜进发布。
# ═══════════════════════════════════════════════════════════════════════

def _rel_lum(rgb):
    def f(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2])

def _contrast(a, b):
    la, lb = sorted((_rel_lum(a), _rel_lum(b)))
    return (lb + 0.05) / (la + 0.05)

def _parse_rgb(v):
    try:
        parts = [int(x) for x in v.strip().split(",")]
        return tuple(parts[:3]) if len(parts) >= 3 else None
    except ValueError:
        return None

# 每个前景角色的下限。Inactive 取 3.0 —— 它的语义就是去强调，
# 逼到 4.5 反而抹掉信号；其余承载正文的角色一律 WCAG AA 4.5。
_FG_MIN = {
    "ForegroundNormal":   4.5, "ForegroundActive":   4.5,
    "ForegroundLink":     4.5, "ForegroundVisited":  4.5,
    "ForegroundNegative": 4.5, "ForegroundNeutral":  4.5,
    "ForegroundPositive": 4.5, "ForegroundInactive": 3.0,
}

def _check_colors(text, label, fails):
    """把一个 .colors 的每个色组 × 每个前景键，对 BackgroundNormal 和
    BackgroundAlternate **两个**背景都量一遍。
    只量 BackgroundNormal 正是当初漏掉 Selection 组的原因。"""
    group, bg, bg_alt, fgs = None, None, None, {}
    def flush():
        if not group or not group.startswith("Colors:"):
            return
        for key, fg in fgs.items():
            lo = _FG_MIN.get(key)
            if lo is None:
                continue
            for bname, b in (("BackgroundNormal", bg), ("BackgroundAlternate", bg_alt)):
                if b is None:
                    continue
                c = _contrast(fg, b)
                if c < lo:
                    fails.append(f"{label} [{group}] {key} on {bname}: "
                                 f"{c:.2f} < {lo}  (fg={fg} bg={b})")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            flush()
            group, bg, bg_alt, fgs = line[1:-1], None, None, {}
            continue
        if "=" not in line or line.startswith("#"):
            continue
        k, v = line.split("=", 1)
        rgb = _parse_rgb(v)
        if rgb is None:
            continue
        if k == "BackgroundNormal":      bg = rgb
        elif k == "BackgroundAlternate": bg_alt = rgb
        elif k.startswith("Foreground"): fgs[k] = rgb
    flush()

def _check_konsole(text, fails):
    """Konsole 全部 30 段。
    ★ 色 0 及其 faint 豁免 ★ —— 它们是 ANSI 背景角色（SGR 40 填充），
    把正文对比度规则套上去是范畴错误：在 bg 23,26,31 上达 4.5:1 的最暗
    中性灰是 130,130,130，任何「合规的黑」都已经是中灰，会破坏
    tmux/powerline/fzf/mc 的背景填充。Color0Intense 是次要**前景**槽
    （SGR 90，shell prompt / fzf 未选中项），不豁免。"""
    sec, colors, bg = None, {}, None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            sec = line[1:-1]; continue
        if line.startswith("Color=") and sec:
            rgb = _parse_rgb(line.split("=", 1)[1])
            if rgb:
                colors[sec] = rgb
                if sec == "Background":
                    bg = rgb
    if bg is None:
        return
    EXEMPT = {"Background", "BackgroundIntense", "BackgroundFaint",
              "Color0", "Color0Faint"}
    for sec, rgb in sorted(colors.items()):
        if sec in EXEMPT:
            continue
        # Faint 档（SGR 2）的语义就是「更暗」，和 ForegroundInactive 同理，
        # 逼到 4.5 会让它亮过 normal 档、把 SGR 2 的语义反转。取 3.0。
        lo = 3.0 if sec.endswith("Faint") else 4.5
        c = _contrast(rgb, bg)
        if c < lo:
            fails.append(f"Konsole [{sec}] on Background: {c:.2f} < {lo}  ({rgb} on {bg})")
        # 上界约束：faint 绝不能亮于对应的 normal 档
        if sec.endswith("Faint"):
            base = colors.get(sec[:-5])
            if base and _rel_lum(rgb) > _rel_lum(base):
                fails.append(f"Konsole [{sec}] 比 {sec[:-5]} 更亮，SGR 2 语义反转")

def verify_contrast():
    """全量跑一遍。有任何不达标就返回失败清单。"""
    fails = []
    for when, accent in [(None, None)] + [(w, SCENE_ACCENTS[w]) for w in SCENE_ACCENTS]:
        label = f"Frost{'' if when is None else '-' + when}.colors"
        _check_colors(color_scheme(accent), label, fails)
    _check_konsole(konsole_scheme(), fails)
    return fails


# ═══════════════════════════════════════════════════════════════════════
#  构建期输出校验门禁
#
#  为什么需要它：对比度门禁只管颜色，管不了「生成出来的文件在结构上是不是活的」。
#  实际踩过的：
#    · 改块注释时漏掉 `*/`，注释一路吞到下一个 `*/`，把整个 targetRect 函数
#      包进注释里。特效仍能加载，但每次最小化都
#      `TypeError: Property 'targetRect' ... is not a function` —— 完全没动画。
#      当时的检查全都通过了：括号在注释里照样配平，grep 也确实找得到
#      "targetRect" 这个词（只是它在注释里）。
#    · 替换代码时结束锚点撞上 JS 内部的一行，只替换了一部分，留下 131 行残体，
#      build-theme.py 直接 IndentationError。
#  两次都是「值对了/字符串在」不等于「代码生效」。所以校验必须作用在
#  **去掉注释之后**的代码上，并且做**交叉引用**：被调用的必须有定义。
# ═══════════════════════════════════════════════════════════════════════

def _strip_js_comments(text):
    """去掉 JS 的块注释与行注释，返回 (去注释后的代码, 块注释是否成对)。

    ★ 必须先识别字符串字面量 ★
    第一版没做这件事，于是把 `",preferred://filemanager"` 里的 `//` 当成行注释、
    从那里截断，剩下一个孤引号 —— 门禁在自己的布局脚本上报假阳性。
    真实的 JS 里 URL、正则、路径里都可能出现 `//` 和 `/*`。

    JS 的块注释**不嵌套**，所以块注释内再出现 `/*` 几乎肯定是漏了 `*/`；
    文件结束时仍在块注释里同样是错。两种都判为不成对。
    行号靠把注释替换成同数量的换行/空格来保留。
    """
    out, i, n = [], 0, len(text)
    state, quote, ok = "code", "", True
    while i < n:
        ch = text[i]
        if state == "code":
            if ch in "\"'`":
                state, quote = "str", ch
                out.append(ch); i += 1; continue
            if text.startswith("/*", i):
                state = "block"; i += 2; continue
            if text.startswith("//", i):
                j = text.find("\n", i)
                i = n if j < 0 else j
                continue
            out.append(ch); i += 1; continue
        if state == "str":
            if ch == "\\" and i + 1 < n:          # 转义，整对照抄
                out.append(text[i:i + 2]); i += 2; continue
            out.append(ch)
            if ch == quote or (ch == "\n" and quote != "`"):
                state = "code"                    # 反引号可跨行，其余到行尾就结束
            i += 1; continue
        # state == "block"
        if text.startswith("*/", i):
            state = "code"; i += 2; continue
        if text.startswith("/*", i):
            ok = False
        out.append("\n" if ch == "\n" else " ")
        i += 1
    if state == "block":
        ok = False
    return "".join(out), ok


def _check_js(text, label, fails):
    """校验生成的 JS 特效脚本 + 布局脚本。"""
    import re
    # ★ 占位符不能漏在产物里 ★
    # 早先只有 _check_qml 查这个，.js 完全没人查 —— 而 layout.js 里也有
    # __FROST_*__ 占位符（面板厚度）。漏替换的后果比 QML 更硬：
    # 布局脚本加载即 ReferenceError，面板整个建不出来。
    # 在**去注释之前**查：占位符出现在注释里也是问题（说明替换没跑）。
    for ph in sorted(set(re.findall(r"__FROST_\w+__", text))):
        fails.append(f"{label}: 占位符 {ph} 没被替换 —— 生成时的 .replace() 漏了")

    code, comments_ok = _strip_js_comments(text)
    if not comments_ok:
        fails.append(f"{label}: 块注释未闭合或嵌套 —— 后续代码会被整段吞掉")

    # 括号配平（在去注释**且**去字符串之后）
    bare = re.sub(r'"[^"\n]*"', '""', code)
    bare = re.sub(r"'[^'\n]*'", "''", bare)
    for o, c, nm in (("{", "}", "{}"), ("(", ")", "()"), ("[", "]", "[]")):
        if bare.count(o) != bare.count(c):
            fails.append(f"{label}: {nm} 不配平 {bare.count(o)}/{bare.count(c)}")

    # ★ 交叉引用：被调用/引用的成员必须有定义 ★
    # 这一条是专为「定义被注释吞掉」设计的 —— 那种情况下调用还在、定义没了。
    obj = re.search(r"const\s+(\w+)\s*=\s*\{", code)
    if obj:
        name = obj.group(1)
        defined = set(re.findall(r"^\s{4}(\w+)\s*:", code, re.M))
        used = set(re.findall(rf"\b{name}\.(\w+)", code)) - {name}
        missing = sorted(used - defined)
        if missing:
            fails.append(f"{label}: 引用了未定义的成员 {missing}（定义可能被注释吞掉）")
        # 入口调用
        if f"{name}.init()" not in code:
            fails.append(f"{label}: 缺少入口调用 {name}.init()")

    # ★ frost_minimize 专属：提层调用的**条数和极性**必须对得上 ★
    # 交叉引用那一条只能抓「引用了不存在的成员」，抓不到「该有的调用少了一处」。
    # 实测缺口：从「无 iconGeometry 早退」路径上删掉一处 elevate(window, false)，
    # 三道门禁全绿、退出码 0 —— 而那正是永久提层的成因（窗口卸下动画后
    # 仍被钉在最上层，压住所有别的窗口）。这一类是本项目回归风险最高的：
    # 特效被整体删除又加回来过四次，README #163 也是它。
    #
    # 判据（对照 out/ 实测）：
    #   elevate(window, true)  x2 —— 两个动画槽各在槽首提层
    #   elevate(window, false) x3 —— 两条早退路径各一次 + animationFinished 一次
    # 早退那两次是关键：没有它们，走不到 animationFinished 的窗口永远留在上层。
    #
    # 不能用 `code.count("elevate(") == 6` 做判据：那个 6 里有一行是文档注释里的
    # `elevate()`，而 _check_js 一开始就剥掉注释了（剥后只剩 5）。定义行是
    # `elevate: function` —— 不含 `elevate(`，根本不在计数里。按 6 写必然误报。
    if "frost_minimize" in label:
        on = len(re.findall(r"\.elevate\s*\(\s*\w+\s*,\s*true\s*\)", code))
        off = len(re.findall(r"\.elevate\s*\(\s*\w+\s*,\s*false\s*\)", code))
        if (on, off) != (2, 3):
            fails.append(
                f"{label}: 提层调用条数不对 —— elevate(_,true)={on}(应为 2) "
                f"elevate(_,false)={off}(应为 3)。"
                f"少了 true 是动画被别的窗口压住；少了 false 是窗口永久留在最上层")
        if "elevate:" not in code:
            fails.append(f"{label}: elevate 的定义不见了（调用还在，定义可能被注释吞掉）")

    # 未闭合的字符串（同一行内引号必须成双）
    for ln, line in enumerate(code.splitlines(), 1):
        if "`" in line:                    # 模板串可跨行，逐行判引号没有意义
            continue
        if line.count('"') % 2 or line.count("'") % 2:
            fails.append(f"{label}:{ln}: 引号不成对 —— {line.strip()[:60]}")
            break


def _check_svg(text, label, fails):
    """校验生成的 SVG：XML 合法 + url(#id) 引用可解析 + shadow 元素成套。"""
    import re
    import xml.etree.ElementTree as ET
    try:
        ET.fromstring(text)
    except ET.ParseError as e:
        fails.append(f"{label}: XML 不合法 —— {e}")
        return
    id_list = re.findall(r'id="([^"]+)"', text)
    ids = set(id_list)
    for ref in set(re.findall(r'url\(#([^)]+)\)', text)):
        if ref not in ids:
            fails.append(f"{label}: url(#{ref}) 引用了不存在的 id")

    # ★ 同一份 SVG 内的 id 必须唯一 ★
    # KSvg 是**按 id 取元素**渲染九宫格的（elementRect(id) / paint(id)）。
    # id 重复时 XML 仍然合法、ET.fromstring 照过，KSvg 静默取到其中一个 ——
    # 症状是九宫格错片（某一边用了另一处同名元素的几何），没有任何报错。
    # 现状是干净的（遍历 out/ 全部 SVG，0 个文件有重复 id），这道是防回归：
    # 这些 SVG 由 GLYPHS/模板拼接生成，同名前缀撞车是最容易发生的一类。
    if len(id_list) != len(ids):
        from collections import Counter
        dup = sorted(k for k, v in Counter(id_list).items() if v > 1)
        fails.append(f"{label}: id 重复 {dup} —— KSvg 按 id 取元素，会静默取到其中一个")

    # ★ <use> 的引用也要能解析 ★
    # 上面只查 url(#id)（fill/filter/clip 那一类）。<use href="#x"> 与
    # 老式 <use xlink:href="#x"> 走的是另一套语法，悬空时同样静默渲染成空白。
    # 当前 out/ 下 0 个 SVG 用 <use>，所以这是潜在缺口而非现存缺陷。
    for ref in set(re.findall(r'(?:xlink:)?href="#([^"]+)"', text)):
        if ref not in ids:
            fails.append(f"{label}: <use href=\"#{ref}\"> 引用了不存在的 id")
    # shadow 成套性：有任何一片就必须齐全
    if any(i.startswith("shadow-") for i in ids):
        need = {f"shadow-{k}" for k in
                ("topleft", "top", "topright", "left", "right",
                 "bottomleft", "bottom", "bottomright", "center")}
        need |= {f"shadow-hint-{s}-margin" for s in ("top", "bottom", "left", "right")}
        miss = sorted(need - ids)
        if miss:
            # center 单独说明：它是 KSvg 判定「前缀存在」的唯一判据
            fails.append(f"{label}: shadow 元素不成套，缺 {miss}"
                         + ("（缺 shadow-center 会让整个 shadow 前缀对 KSvg 等于不存在）"
                            if "shadow-center" in miss else ""))


def verify_source():
    """源码级自检：查 verify_output() 看不见的那一类缺陷。

    输出校验只看 out/ 里生成了什么，但有些缺陷**根本不改变输出**，或者
    改变了输出而两份来源看起来都对 —— 只能在语法树层面查：

      ① 字典重复键。Python 不报错、后键静默覆盖前键。
         实际发生过：named 字典里 "user-home" 出现两次，第二处把
         GLYPHS 的值抄了一遍。改 GLYPHS 不生效，两份还会漂移。
         grep 找得到两处，但看不出「哪个生效」—— 这是它躲过所有
         文本检查的原因。
      ② 死令牌。定义了却没人读的模块级常量，是重构没做完的痕迹，
         读代码的人会以为它还在起作用。
      ③ 模块可见性。`X.attr` 里的 X 在那个函数里必须能看见（含闭包父链）。
         专抓「import 少了一行」这类：ast.parse 过得去，跑到那一行才 NameError。
         本项目一天内犯过三次（ast / collections / re）。
      ④ 跨文件被抄成字面量的常量。同一个值在 daylight.py / tweak.py 里
         被抄成字面量，改一处另一处静默漂移。

    已知边界（刻意的取舍，不是遗漏）：① 只查字符串键，非字符串键的字典
    不看（当前源码里没有）；② 只扫模块顶层的 ast.Assign，不进 if/try 分支、
    不认带类型标注的 AnnAssign；③ 只查 `X.attr` 里根名 X 的可见性 ——
    裸名调用、挂在调用结果上的属性、以及已可见模块上的错误子属性名都抓不到。

    只查本文件和同目录的 daylight.py / tweak.py（缺文件不算失败：
    单独拷走 build-theme.py 跑的场景本来就已经因为 wallpaper.py 而失败，
    这里不额外提高耦合）。
    """
    import re
    fails = []
    here = os.path.dirname(os.path.abspath(__file__))
    for fn in ("build-theme.py", "daylight.py", "tweak.py"):
        path = os.path.join(here, fn)
        if not os.path.exists(path):
            continue
        src = open(path, encoding="utf-8").read()
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            fails.append(f"{fn}: 语法错误 第 {e.lineno} 行 —— {e.msg}")
            continue

        # ① 字典重复键
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = [k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            dup = sorted({k for k in keys if keys.count(k) > 1})
            if dup:
                fails.append(
                    f"{fn}:{node.lineno}: 字典重复键 {dup} —— "
                    f"后键静默覆盖前键，改另一处不生效")

        # ② 死令牌：模块级 全大写 常量，全文件再无读取
        assigned = {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id.isupper() and len(t.id) > 2:
                        assigned[t.id] = node.lineno
        loads = collections.Counter(
            n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load))
        for name, ln in sorted(assigned.items()):
            if loads[name] == 0:
                fails.append(
                    f"{fn}:{ln}: 死令牌 {name} —— 定义了但全文无人读取")

        # ③ 模块可见性：`X.attr` 里的 X 在该函数里必须能看见
        #
        # ★ 这是今天连犯三次的那一类，而且三次都是同一个机制 ★
        #   · 忘了 `import ast`            → NameError: name 'ast' is not defined
        #   · 忘了 `import collections`    → 同上
        #   · `re` 只在 _check_js() 里局部导入，却在 verify_source() 里用
        # 三次 `ast.parse` / `py_compile` 全部通过 —— 语法完全合法，
        # 只有**执行到那一行**才炸。而这些行在门禁里，平时不一定走到。
        #
        # 判据故意收得很窄：只查 `X.attr` 形式里的 X，且可见集 =
        #   模块级导入/赋值/def ∪ builtins ∪ 本函数导入/赋值/参数 ∪ 外层函数链
        # 这样闭包完全不会误报。★ 外层函数链是必须的 ★ ——
        # 实测没有它会误报 8 处：out.append / fails.append 这类「闭包里的
        # 列表对象」也是 X.attr 形式。加上父链后四个源文件全部 0 误报，
        # 而上面那三个真错逐个抓到（在 /tmp 副本上注入验证过）。
        #
        # 不装 pyflakes/ruff 的理由：本机四个都没装，而这条规则只需要
        # 二十行 AST —— 为一条规则引入一个构建期依赖不值得。
        import builtins as _bi
        FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)

        def _imports(node):
            out = set()
            for n in ast.walk(node):
                if isinstance(n, (ast.Import, ast.ImportFrom)):
                    for a in n.names:
                        out.add(a.asname or a.name.split(".")[0])
            return out

        def _stores(node):
            out = set()
            for n in ast.walk(node):
                if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                    out.add(n.id)
                elif isinstance(n, ast.arg):
                    out.add(n.arg)
                elif isinstance(n, ast.ExceptHandler) and n.name:
                    out.add(n.name)
                elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    out.add(n.name)
                elif isinstance(n, (ast.Global, ast.Nonlocal)):
                    out.update(n.names)
            return out

        mod_vis = set()
        for s in tree.body:
            if isinstance(s, (ast.Import, ast.ImportFrom)):
                mod_vis |= _imports(s)
            elif isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                mod_vis.add(s.name)
            elif isinstance(s, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                mod_vis |= {n.id for n in ast.walk(s)
                            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
            elif isinstance(s, (ast.If, ast.Try, ast.For, ast.While, ast.With)):
                mod_vis |= _imports(s) | _stores(s)

        parent = {}
        for n in ast.walk(tree):
            for c in ast.iter_child_nodes(n):
                parent[c] = n
        seen = set()
        for func in [n for n in ast.walk(tree) if isinstance(n, FUNC)]:
            vis = mod_vis | set(dir(_bi)) | _imports(func) | _stores(func)
            p = parent.get(func)
            while p is not None:                      # 外层函数链（闭包）
                if isinstance(p, FUNC):
                    vis |= _imports(p) | _stores(p)
                p = parent.get(p)
            for n in ast.walk(func):
                if not (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)):
                    continue
                if n.value.id in vis:
                    continue
                k = (fn, n.value.lineno, n.value.id)
                if k in seen:
                    continue
                seen.add(k)
                fails.append(
                    f"{fn}:{n.value.lineno}: {n.value.id}.… 在 {func.name}() 里不可见 —— "
                    f"运行到这行才会 NameError（ast.parse 抓不到）")

    # ④ 跨文件被抄成字面量的常量
    # tweak.py 和 daylight.py 不 import build-theme.py（前者是后处理脚本、
    # 后者是运行时组件，都要能独立跑），所以有两个值只能手抄。手抄就会漂移，
    # 而漂移的后果都是**静默的视觉不一致**：
    #   · darklyrc 的 CornerRadius 是 Qt 应用窗口的圆角，
    #     和 RADIUS_LG（面板/弹窗圆角）不一致 → 窗口和面板圆角不同档
    #   · SCENE_ACCENTS 决定「强调色 = 当前时刻」这条原则的四个取值，
    #     两边不一致 → 壁纸是一个时段的光，UI 强调色是另一个时段的
    # 缺文件不算失败（本文件已硬依赖同目录的 wallpaper.py，不再提高耦合度）。
    def _const(path, name):
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except (OSError, SyntaxError):
            return None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    getattr(t, "id", None) == name for t in node.targets):
                try:
                    return ast.literal_eval(node.value)
                except ValueError:
                    return None
        return None

    tweak_py = os.path.join(here, "tweak.py")
    if os.path.exists(tweak_py):
        # tweak.py 里是 kwrite(...) 调用的字面量，不是模块级常量 —— 抓调用实参
        src = open(tweak_py, encoding="utf-8").read()
        for key in ("CornerRadius", "OtherCornerRadius"):
            m = re.search(rf'kwrite\([^)]*?"{key}",\s*(\d+)\)', src)
            if m is None:
                fails.append(f"tweak.py: 找不到 darklyrc 的 {key} 赋值 —— "
                             f"跨文件门禁失去判据（改了写法就要改这里）")
            elif int(m.group(1)) != RADIUS_LG:
                fails.append(
                    f"tweak.py: darklyrc {key}={m.group(1)} ≠ RADIUS_LG={RADIUS_LG}"
                    f"（Qt 窗口圆角 ≠ 面板/弹窗圆角）")

    daylight_py = os.path.join(here, "daylight.py")
    if os.path.exists(daylight_py):
        other = _const(daylight_py, "SCENE_ACCENTS")
        if other is None:
            fails.append("daylight.py: 读不到 SCENE_ACCENTS —— 跨文件门禁失去判据")
        else:
            # 两边表示法不同：这里是 (r,g,b) 元组，daylight.py 是 "r,g,b" 字符串。
            # 归一化后比，而不是要求写法一致 —— 各自的用法决定了各自的表示。
            def norm(d):
                out = {}
                for k, v in d.items():
                    out[k] = tuple(int(x) for x in v.split(",")) \
                             if isinstance(v, str) else tuple(v)
                return out
            a, b = norm(SCENE_ACCENTS), norm(other)
            if a != b:
                diff = [f"{k}: {a.get(k)} vs {b.get(k)}"
                        for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
                fails.append("daylight.py: SCENE_ACCENTS 与 build-theme.py 不一致 —— "
                             + "；".join(diff))
    return fails


def verify_output():
    """遍历 out/ 下所有生成物做结构校验。返回失败清单。

    （签名早先是 verify_output(tree)，但函数体只用 os.walk(OUT)，`tree`
      从未被读取、调用点也一直传 None —— 重构残留，已去掉。）
    """
    fails = []
    for root, _, files in os.walk(OUT):
        for fn in files:
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, OUT)
            try:
                if fn.endswith(".js"):
                    _check_js(open(fp, encoding="utf-8").read(), rel, fails)
                elif fn.endswith(".svg"):
                    _check_svg(open(fp, encoding="utf-8").read(), rel, fails)
                elif fn.endswith(".json"):
                    json.load(open(fp, encoding="utf-8"))
                elif fn.endswith(".qml"):
                    _check_qml(open(fp, encoding="utf-8").read(), rel, fails)
            except UnicodeDecodeError:
                pass                    # 二进制（png 等）跳过
            except json.JSONDecodeError as e:
                fails.append(f"{rel}: JSON 不合法 —— {e}")
    return fails


def _check_qml(text, label, fails):
    """QML 静态检查。

    ★ 为什么 QML 必须单独看守 ★
    splash 的 QML **是登录时真正执行的代码**，加载失败的后果是
    「开机没有 splash」—— 屏幕上什么都不显示，而且没有任何可见报错，
    只有 `org.kde.plasma.ksplashqml: Failed loading QUrl(...)` 进 journal。
    实测把一个字符写错就足够触发（注入 `property int stage BROKEN@@` →
      "Error loading QML file.\\n31: Expected token `:'"）。
    而在本轮之前 verify_output() 只分派 .js / .svg / .json，**.qml 完全没人看**。

    这里做的是**便宜且必要**的静态检查，不试图替代真正的 QML 引擎：
      ① 括号/花括号配平（去注释、去字符串之后）
      ② 每个 `import` 的模块目录在本机存在 —— 缺一个 import 就是整体加载失败，
         而这是最容易在重构中留下死 import 的地方
      ③ 占位符不能漏在产物里（`__FROST_*__` 应当在生成时就被替换掉）
    真正的加载测试要跑 ksplashqml，那需要 dbus + 离屏平台，不适合放进构建；
    发布前的手工验法记在 README。
    """
    import re
    # 去掉行注释与块注释（QML 的注释语法同 C）
    code = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    code = re.sub(r"//[^\n]*", "", code)
    bare = re.sub(r'"[^"\n]*"', '""', code)
    bare = re.sub(r"'[^'\n]*'", "''", bare)
    for nm, (o, c) in (("{}", ("{", "}")), ("()", ("(", ")")), ("[]", ("[", "]"))):
        if bare.count(o) != bare.count(c):
            fails.append(f"{label}: {nm} 不配平 {bare.count(o)}/{bare.count(c)}")

    for mod in re.findall(r"^\s*import\s+([A-Za-z][\w.]*)", code, re.M):
        # QtQuick 等内置模块由 Qt 自带，只校验 org.kde.* 这类外部模块
        if not mod.startswith("org."):
            continue
        rel = mod.replace(".", "/")
        if not any(os.path.isdir(os.path.join(base, rel))
                   for base in ("/usr/lib/qt6/qml", "/usr/lib64/qt6/qml")):
            fails.append(f"{label}: import {mod} 在本机找不到对应目录 —— "
                         f"缺一个 import 就是整个 QML 加载失败（开机没有 splash）")

    for ph in re.findall(r"__FROST_\w+__", text):
        fails.append(f"{label}: 占位符 {ph} 没有被替换 —— 会原样进产物")

    # ④ 真正的语法解析，交给 qmllint
    # ★ 括号配平抓不到大多数 QML 语法错 ★
    # 实测：注入 `property int stage BROKEN@@` 括号仍然配平，上面三条全过 ——
    # 而 ksplashqml 会直接 "Error loading QML file. 31: Expected token `:'"
    # 然后**屏幕上什么都不显示**。所以必须有一个真解析器。
    # qmllint 在同一个位置报同一条（31:24 Expected token `:'）。
    # ★ 不能看它的退出码 ★ 语法错时 qmllint 实测也返回 **0**（它当 warning），
    # 必须看输出。只对 [syntax] 类失败 —— 其他类别（unqualified access 之类）
    # 是风格建议，不该挡构建，而且新版 Qt 可能加新类别。
    # 找不到 qmllint 就跳过：不让构建硬依赖一个可选工具
    # （它来自 qt6-declarative，Plasma 机器上通常有，但不保证）。
    for cand in ("/usr/lib/qt6/bin/qmllint", "/usr/lib64/qt6/bin/qmllint",
                 shutil.which("qmllint") or ""):
        if cand and os.path.exists(cand):
            import subprocess, tempfile
            with tempfile.NamedTemporaryFile("w", suffix=".qml",
                                             delete=False, encoding="utf-8") as tf:
                tf.write(text)
                tmp = tf.name
            try:
                r = subprocess.run([cand, tmp], capture_output=True, text=True)
                for line in (r.stdout + r.stderr).splitlines():
                    if "[syntax]" in line:
                        # 行号是临时文件里的，和产物一致（内容逐字相同）
                        # 只留 行:列 和消息，去掉临时文件路径
                        parts = line.split(":", 1)
                        msg = parts[-1].strip() if len(parts) > 1 else line.strip()
                        fails.append(f"{label}: QML 语法错 —— {msg}")
            finally:
                os.unlink(tmp)
            break

def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    theme = os.path.join(OUT, "desktoptheme", NAME)

    variants = {
        "widgets/panel-background.svg": GLASS_PANEL,
        "widgets/background.svg":       GLASS_POPUP,
        "widgets/tooltip.svg":          GLASS_TOOLTIP,
        "dialogs/background.svg":       GLASS_DIALOG,
    }
    for rel, alpha in variants.items():
        # ★ 面板不加投影 ★ README #79 论证过：窗口自己的 Darkly 阴影已提供分隔，
        # 而夜间面板本就比窗口暗，再叠暗影反而把两者拉近。#79 的论证只适用于面板 ——
        # 弹窗浮在任意内容之上，情况完全不同，所以它们要加。
        svg = nine_slice(alpha, with_shadow="panel-background" not in rel)
        write(os.path.join(theme, rel), svg)                 # 根：默认
        write(os.path.join(theme, "translucent", rel), svg)  # 有合成器时

    # 任务栏项（含「运行中」指示条）
    write(os.path.join(theme, "widgets", "tasks.svg"), tasks_svg())
    # 列表行高亮 + 分隔线（Kickoff 菜单、托盘弹窗、各种下拉都吃这两个）
    write(os.path.join(theme, "widgets", "listitem.svg"), listitem_svg())
    write(os.path.join(theme, "widgets", "line.svg"), line_svg())

    # ─────────────────────────────────────────────────────────────
    # 只写「验证过」或「修具体 bug」的 widget。
    #
    # 教训：曾经一口气补了 button / frame / viewitem / scrollbar / slider /
    # switch / tabbar / toolbar / checkmarks / radiobutton / pager /
    # translucentbackground / lineedit 共 13 个，透明度全是拍脑袋定的，
    # 没有逐个视觉验证。而这些恰好是**所有托盘弹窗的骨架**，
    # 结果把 Breeze 精心设计的版本换成了粗糙的猜测值，弹窗全变样。
    #
    # Breeze 的这些 widget 本身设计得好，而且同样吃 ColorScheme-* ——
    # 也就是说它们**本来就跟随 Frost 的配色**，不替换并不会「不统一」。
    # 主题的辨识度来自玻璃面板、任务栏指示条、列表高亮，不是来自复刻每一个控件。
    #
    # 上面那些生成函数保留着，将来想逐个做的时候，
    # 务必「做一个 → 截图验证 → 再做下一个」，不要批量上。
    # ─────────────────────────────────────────────────────────────

    # 下面三个都是同一类问题：**Breeze 的版本会在我的玻璃容器上再垫一层不透明底**，
    # 两层交界处形成硬边（用户看到的「框线」「横杠」）。
    # 判据很明确 —— 不是「我觉得能做得更好看」，而是「不提供就有可见缺陷」。

    # calendar：Breeze 的 base 不透明，垫在半透明 dialogs/background 上
    # 会让日历下方出现一条色带。base 必须全透明。
    write(os.path.join(theme, "widgets", "calendar.svg"), calendar_svg())

    # plasmoidheading：Breeze 的 header/footer 是 opacity=0.75 的实色带，
    # 压在 0.35 的玻璃弹窗上，交界处就是菜单顶部那条「框线」。
    # 全透明 —— 页眉页脚直接融进玻璃，没有任何边。
    write(os.path.join(theme, "widgets", "plasmoidheading.svg"),
          multi_state([("header", 0.00, TX), ("footer", 0.00, TX)]))

    # tabbar：**面板外壳用它画「组件展开中」的指示**
    #   north-active-tab → 顶栏组件   south-active-tab → 底栏组件
    # Breeze 画的是一根横杠。顶栏放的是时钟/托盘/电源这类**状态**组件，
    # 弹窗开着本身就是反馈，再加横杠是冗余且突兀。
    # 四个方位统一改成柔和的圆角底色块，不画任何条。
    #
    # 四个方位全透明 —— 不画任何底块。
    #
    # north- 对应顶栏组件（时钟/托盘/电源），弹窗本身就是最直接的反馈，
    #   再画色块是冗余，而且在半透明面板上看着像一块脏阴影。
    # south- 对应 Kickoff 底部的 Applications / Places 标签页。
    #   Kickoff 自己会用文字颜色区分当前页，不依赖这个底块。
    #
    # 实测归属（染色验证）：Kickoff 里「Favorites」「Discover」那两个高亮块
    # **不是这里画的，是 Kirigami 自绘的**，走配色方案的 Colors:Selection，
    # Plasma 主题 SVG 管不到 —— 想改只能动配色，且会影响全系统的选中态。
    write(os.path.join(theme, "widgets", "tabbar.svg"),
          multi_state([("base", 0.00, TX),
                       ("north-active-tab", 0.00, HL),
                       ("south-active-tab", 0.00, HL),
                       ("east-active-tab",  0.00, HL),
                       ("west-active-tab",  0.00, HL)],
                      per_state_hints=False))

    # 不透明分支。**目录名必须是 solid/** —— Plasma 6 的 Panel.qml 里写死了
    #   translucent 状态 → "widgets/panel-background"
    #   opaque     状态 → "solid/widgets/panel-background"
    # opaque/ 是 Plasma 5 时代的遗留名，Plasma 6 已经不读它了。
    # 缺 solid/ 的后果：面板一进不透明状态就回退到 Breeze 的背景，
    # 看起来就像「主题根本没生效」—— 排查了很久才发现。
    #
    # **只写 solid/，不写 opaque/。**
    # 全盘搜过：Plasma 6 只在两处引用 solid/ 前缀
    #   "solid/widgets/panel-background"  和  "solid/widgets/tooltip"
    # 整个系统**没有一处**引用 opaque/ —— 它是纯粹的死重量（4 个文件 28K）。
    for rel in ["widgets/panel-background.svg", "widgets/background.svg",
                "widgets/tooltip.svg", "dialogs/background.svg"]:
        write(os.path.join(theme, "solid", rel),
              nine_slice(1.0, with_edge=False, with_mask=False,
                         with_shadow="panel-background" not in rel))

    write(os.path.join(theme, "metadata.json"), json.dumps({
        "KPlugin": {
            "Authors": [{"Name": AUTHOR}],
            "Category": "Plasma Theme",
            "Description": "Minimal frosted glass — translucent panels and popups.",
            "EnabledByDefault": True,
            "Id": NAME,
            "License": "GPL-2.0-or-later",
            "Name": NAME,
            "Version": VERSION,
        },
        # 必须是 "6.0"。系统自带的 breeze-dark 写的是 "5.0"，但那是旧版兼容路径；
        # 用户目录下的主题声明 5.0 会被 Plasma 6 静默忽略 —— 配置里显示已选中，
        # 实际却回退到 default，~/.cache/plasma_theme_<Id>.kcache 根本不生成。
        # 判断主题有没有真正加载，就看那个 kcache 文件在不在。
        "X-Plasma-API": "6.0",
    }, indent=4, ensure_ascii=False) + "\n")

    write(os.path.join(theme, "plasmarc"), textwrap.dedent("""\
        [AdaptiveTransparency]
        enabled=true
        """))

    # ---- 配色方案 ----
    # 默认配色 + 四个时段各一份（daylight.py 按时段切换）
    write(os.path.join(OUT, "color-schemes", f"{NAME}.colors"),
          color_scheme(DEFAULT_ACCENT))
    for when, acc in SCENE_ACCENTS.items():
        write(os.path.join(OUT, "color-schemes", f"{NAME}-{when}.colors"),
              color_scheme(acc).replace(f"ColorScheme={NAME}", f"ColorScheme={NAME}-{when}")
                               .replace(f"Name={NAME}", f"Name={NAME} · {when}"))

    # ---- 图标主题 ----
    for rel, content in icon_theme_files().items():
        write(os.path.join(OUT, "icons", NAME, rel), content)

    # KWin 特效（Frost 自己的最小化动画）。装到 ~/.local/share/kwin/effects/，
    # 不属于任何 KPackage 资产类别，所以单独一层目录，install 时按原样复制。
    for rel, content in kwin_effect_files().items():
        write(os.path.join(OUT, "kwin-effects", rel), content)

    # ---- 壁纸：四个时段各一个包 ----
    write(os.path.join(OUT, "konsole", f"{NAME}.colorscheme"), konsole_scheme())
    write(os.path.join(OUT, "konsole", f"{NAME}.profile"), konsole_profile())

    if preview_files(OUT):
        print("  系统设置预览图已生成（600x337 + 1920x1080）")

    via = login_wallpaper(OUT)
    if via:
        print(f"  登录壁纸 PNG 已生成（{via}）")

    # 占位文件：让 categories/scalable 目录真实存在，
    # 这样 FROST_COLOR_CATEGORIES=1 往里放图标时不需要额外 mkdir，
    # 也避免「声明了目录但目录不存在」的半吊子状态。
    write(os.path.join(OUT, "icons", NAME, "categories", "scalable", ".keep"), "")

    for rel, content in splash_files().items():
        write(os.path.join(OUT, "look-and-feel", LNF_ID, "contents", rel), content)

    for rel, content in wallpaper_files().items():
        write(os.path.join(OUT, "wallpapers", rel), content)

    # ---- 全局主题包 ----
    lnf = os.path.join(OUT, "look-and-feel", LNF_ID)
    write(os.path.join(lnf, "metadata.json"), lnf_metadata())
    write(os.path.join(lnf, "contents", "defaults"), lnf_defaults())
    write(os.path.join(lnf, "contents", "layouts",
                       "org.kde.plasma.desktop-layout.js"), layout_js())

    # ---- 独立布局模板（可在「桌面布局」里单独套用）----
    tpl = os.path.join(OUT, "layout-templates", f"{LNF_ID}.topbarDock")
    write(os.path.join(tpl, "contents", "layout.js"), layout_js())
    write(os.path.join(tpl, "metadata.json"), json.dumps({
        "KPlugin": {
            "Authors": [{"Name": AUTHOR}],
            "Id": f"{LNF_ID}.topbarDock",
            "License": "GPL-2.0-or-later",
            # ★ 用户可见的名字必须是英文 ★
            # 这是明确约束（「一个中文主题很突兀」）。这个 Name 显示在
            # 系统设置 → 桌面布局的模板列表里，早先写的是
            # "Frost — 顶栏 + 底部 Dock"，中文直接露在界面上。
            # 规矩：注释随便中文，**metadata 里给用户看的字符串一律英文**。
            "Name": f"{NAME} — Top Bar + Bottom Dock",
            "Description": "Thin top bar with clock and system tray, "
                           "centred icon dock at the bottom.",
            "Version": VERSION,
        },
        "KPackageStructure": "Plasma/LayoutTemplate",
        # ★ 缺 Categories 就等于没装 ★
        # 实测 Plasma 6.7：plasmashell 用
        #   KPackage::PackageLoader::findPackages("Plasma/LayoutTemplate", …, 谓词)
        # 枚举布局模板，谓词里查 X-Plasma-ContainmentCategories 是否 contains "panel"。
        # 键不存在 → value(key, QStringList()) 返回空表 → contains 为 false →
        # 包被整个过滤掉，「添加面板」菜单里**永远看不到**它。
        # 官方三个模板（appmenubar / defaultPanel / emptyPanel）全都带这个键。
        # 而 X-Plasma-Shell 在 6.7 的 plasmashell 二进制里**一个字节都没有**：
        #   strings -a    /usr/bin/plasmashell | grep -c '^X-Plasma-Shell$'      → 0
        #   strings -a -el /usr/bin/plasmashell | grep -c '^X-Plasma-Shell$'     → 0
        #   对照 X-Plasma-ContainmentCategories → UTF16=1，X-Plasma-Bogus → 0/0
        # （QStringLiteral 存成 UTF-16，所以必须 -el，否则全是假阴性。）
        # 所以它是死键 —— 但仍写成和官方一致的 "plasmashell"，
        # 原来的 "org.kde.plasma.desktop" 是 Plasma 5 时代的写法。
        # kpackagetool6 --list 能列出这个包**不代表 UI 里看得见** ——
        # KPackage 层不做这个过滤，「装上了」和「菜单里有」是两件事。
        "X-Plasma-ContainmentCategories": ["panel"],
        "X-Plasma-Shell": "plasmashell",
    }, indent=4, ensure_ascii=False) + "\n")

    print(f"生成完毕 → {OUT}")
    for root, _, files in os.walk(OUT):
        for f in sorted(files):
            p = os.path.join(root, f)
            print(f"  {os.path.relpath(p, OUT):52s} {os.path.getsize(p):>6d} B")

    # ── 构建期门禁：不达标就让构建失败 ──
    sfails = verify_source()
    if sfails:
        print()
        print("!! 源码自检未通过，构建中止：", file=sys.stderr)
        for f in sfails:
            print(f"   {f}", file=sys.stderr)
        raise SystemExit(1)
    print("  源码自检：全部通过（字典重复键 + 死令牌 + 模块可见性 + 跨文件常量，AST 级）")

    ofails = verify_output()
    if ofails:
        print()
        print("!! 输出结构校验未通过，构建中止：", file=sys.stderr)
        for f in ofails:
            print(f"   {f}", file=sys.stderr)
        raise SystemExit(1)
    # 文案必须逐项对应真正跑过的检查 —— 少列（QML 早先漏了）会让人以为没人看，
    # 多列则是虚假的安全感。两种都发生过，所以这行跟着 _check_* 一起改。
    print("  输出结构校验：全部通过（JS 注释边界/交叉引用/提层调用条数 + "
          "SVG XML/url 引用/use 引用/id 唯一/shadow 成套 + QML 配平/import/qmllint + JSON）")

    fails = verify_contrast()
    if fails:
        print()
        print("!! 对比度门禁未通过，构建中止：", file=sys.stderr)
        for f in fails:
            print(f"   {f}", file=sys.stderr)
        raise SystemExit(1)
    print("  对比度门禁：全部通过（5 套配色 × 各色组 × 8 前景键 × 2 背景 + Konsole 30 段）")


if __name__ == "__main__":
    main()
