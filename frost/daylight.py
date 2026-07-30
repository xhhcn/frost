#!/usr/bin/env python3
"""
按太阳高度角切换壁纸时段。

设计要点：
  * **不联网、不要 API key、不装插件。**
    经纬度从系统自带的 /usr/share/zoneinfo/zone.tab 读（时区→坐标），
    太阳位置用 NOAA 的标准算法现算，纯数学、只用标准库。
  * 四张场景 SVG 各约 6 KB，切换只是改一个配置键，开销可忽略。
  * 由 systemd user timer 每 20 分钟跑一次；同一时段不重复设置，避免闪烁。

用法：
    python3 daylight.py            # 按当前时间设置壁纸
    python3 daylight.py --which    # 只打印该用哪个时段，不改动
    python3 daylight.py --install  # 装 systemd 定时器
"""
# ★ 顶部只导入热路径真正需要的模块 ★
# 这个脚本每 20 分钟跑一次，但一天 72 次里有 71 次是「时段没变，直接退出」。
# 那条路径只需要 math / os / datetime。subprocess 和 re 只有在**真要切换**时
# 才用得上，却是最贵的两个 import（subprocess 单独就比基线多约 15 ms）。
# 实测：全部顶部导入 74.6 ms → 延迟导入 25.7 ms（省 65%）。
# 参考：裸解释器启动 23.7 ms —— 也就是说已经贴着 Python 的地板了，
# 再往下只能换语言，而那笔账不划算（见 README「为什么不用 Go / C 重写」）。
import math, os, sys
from datetime import datetime, timezone

# 各时段强调色 = 该场景光源色（太阳/月亮）。和 build-theme.py 的
# SCENE_ACCENTS 保持一致 —— 那边生成配色方案，这边负责运行时切换。
# 为什么 day/night 不用「月亮本体色」这类最直觉的取法：
# 早先 night 取月亮色 #dfe8f5（明度 85%），比 day 还亮 —— 夜里的光比白天亮，
# 感知上是反的；更要命的是两者 CIE ΔE 只有 15.5，早上开机那一跳
# （night→day，最常发生的一次）几乎看不出配色变了。
# 现在改成从各自**天空**取色、对向拉开：day 偏青 190°、night 偏靛 224°，
# ΔE 提到 32.5（一眼可辨门槛 25），且 day 饱和还从 77% 降到 65%，更克制。
# 四档两两 ΔE 全部 >25，面板对比全部 >7:1。
SCENE_ACCENTS = {
    "dawn":  "255,179,122",   # 柔桃，呼应日出
    "day":   "104,203,223",   # 天青，取自正午天空
    "dusk":  "245,185,66",    # 暖金，呼应落日
    "night": "152,173,230",   # 夜靛，取自夜空而非月亮本体
}

# ★ 数据目录必须认 XDG_DATA_HOME，不能写死 ~/.local/share ★
# install.sh 用的是 ${XDG_DATA_HOME:-$HOME/.local/share}，而这里原本 8 处
# 全是写死的 os.path.expanduser("~/.local/share/...")。两边不一致的后果实测过：
# XDG_DATA_HOME 指到别处时，资产装进去了、install.sh 退出码 0、还打印「装好了」，
# 但本文件在 ~/.local/share/wallpapers 下找不到壁纸包，
# stderr 只有一行「!! 找不到 .../FrostScene-day」混在一屏说明里 ——
# 壁纸/配色/splash/锁屏四条同步全部失效。
#
# ★ 修的方向是让这里跟上 install.sh，不是反过来 ★
# 一次审计建议把 install.sh 钉到 $HOME/.local/share。那是**反的** ——
# 实测 `XDG_DATA_HOME=/tmp/xdgprobe plasma-apply-colorscheme --list-schemes`
# 看到的 Frost 方案数是 **0**，默认时是 **5**；qtpaths6 --paths
# GenericDataLocation 也显示设置后首项换成 /tmp/xdgprobe、~/.local/share
# 不再是搜索根。也就是说 XDG_DATA_HOME 一被设置，Plasma 就**只**看那里。
# 按那个建议改，assets 会落在 Plasma 根本看不见的地方 —— 比现在的 bug 更糟。
DATA_HOME = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
CACHE_HOME = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")

WALL_DIR  = os.path.join(DATA_HOME, "wallpapers")
SPLASH_IMG = os.path.join(
    DATA_HOME, "plasma/look-and-feel/com.xhhcn.frost/contents/splash/images/scene.svg")
STATE    = os.path.join(CACHE_HOME, "frost-daylight-state")


def coords():
    """从时区推经纬度。zone.tab 是 tzdata 自带的本地文件。

    时区不用 `timedatectl` 读 —— 那要 fork 一个子进程再走一次 DBus 问 systemd，
    实测 7.8 ms，占本脚本自身逻辑（约 36 ms）的两成，而它取的是一个
    几乎永不变化的值。`/etc/localtime` 是指向 zoneinfo 的符号链接，
    readlink 只要 0.075 ms，快 104 倍，且不依赖 systemd 在跑。
    保留 timedatectl 作为兜底：极少数发行版把 /etc/localtime 做成了副本而非链接。
    """
    tz = ""
    try:
        link = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in link:
            tz = link.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    if not tz:
        import subprocess      # 只有 /etc/localtime 不是符号链接时才走到这里
        tz = subprocess.run(["timedatectl", "show", "-p", "Timezone", "--value"],
                            capture_output=True, text=True).stdout.strip()
    try:
        for line in open("/usr/share/zoneinfo/zone.tab"):
            if line.startswith("#"):
                continue
            f = line.split("\t")
            if len(f) > 2 and f[2].strip() == tz:
                # zone.tab 的坐标是**定宽**的：±DDMM±DDDMM
                # （少数条目是 ±DDMMSS±DDDMMSS，多出来的秒位忽略即可）。
                # 用切片而不是正则 —— 这是热路径，而 import re 比基线多约 5 ms，
                # 为一个定宽格式付这个代价不值。
                c = f[1]
                try:
                    if len(c) >= 11 and c[5] in "+-":          # ±DDMM±DDDMM
                        la, lam, lo, lom = c[0:3], c[3:5], c[5:9], c[9:11]
                    elif len(c) >= 15:                          # ±DDMMSS±DDDMMSS
                        la, lam, lo, lom = c[0:3], c[3:5], c[7:11], c[11:13]
                    else:
                        continue
                    sla = 1 if la[0] == "+" else -1
                    slo = 1 if lo[0] == "+" else -1
                    return (int(la) + sla * int(lam) / 60,
                            int(lo) + slo * int(lom) / 60)
                except (ValueError, IndexError):
                    continue
    except OSError:
        pass
    return 0.0, 0.0          # 取不到就当赤道，仍能给出合理的昼夜


def sun_elevation(lat, lon, when=None):
    """太阳高度角（度）。NOAA 简化算法，误差 <0.5°，对切壁纸绰绰有余。"""
    t = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
    # 儒略日
    a = (14 - t.month) // 12
    y = t.year + 4800 - a
    m = t.month + 12 * a - 3
    jdn = (t.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045)
    jd = jdn + (t.hour - 12) / 24 + t.minute / 1440 + t.second / 86400
    n = jd - 2451545.0
    L = (280.460 + 0.9856474 * n) % 360          # 平黄经
    g = math.radians((357.528 + 0.9856003 * n) % 360)   # 平近点角
    lam = math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.0000004 * n)
    dec = math.asin(math.sin(eps) * math.sin(lam))       # 赤纬
    gmst = (18.697374558 + 24.06570982441908 * n) % 24
    lst = math.radians((gmst * 15 + lon) % 360)
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    ha = lst - ra                                        # 时角
    la = math.radians(lat)
    el = math.asin(math.sin(la) * math.sin(dec) +
                   math.cos(la) * math.cos(dec) * math.cos(ha))
    return math.degrees(el), math.degrees(ha)


def pick(elev, hour_angle):
    """把太阳高度角映射到时段。
    时角为负 = 正午之前（太阳在升）→ 晨；为正 = 午后（在落）→ 昏。"""
    rising = math.sin(math.radians(hour_angle)) < 0
    if elev > 12:
        return "day"
    if elev > -7:
        return "dawn" if rising else "dusk"
    return "night"



def sync_gtk_color_names():
    """给 GTK4/libadwaita 补上它认识的色名。值不动，只解决「名字对不上」。

    ★ 实测：GTK4 应用收不到 Frost 的任何面色 ★
    配色到 GTK 侧靠 kded 的 gtkconfig 模块（kde-gtk-config），它往
    ~/.config/gtk-{3,4}.0/colors.css 写 @define-color。问题是那些名字
    **全带 `_breeze` 后缀** —— 实测 gtk-4.0/colors.css 84 条，不带后缀的 0 条。
    而 `_breeze` 在 GTK4 那边根本不存在：
      strings -a       libadwaita-1.so.0 | grep -c _breeze  → 0
      strings -a -e l  libadwaita-1.so.0 | grep -c _breeze  → 0   (UTF-16LE 也查了)
      libgtk-4.so.1 同样 0/0
    对照（证明扫描有效、是真阴性而不是命令失灵）：libadwaita 真正读的名字
      window_bg_color 8 次 / view_bg_color 7 次 / accent_bg_color 6 次
      / headerbar_bg_color 3 次
    另一条路也堵死：~/.config/gtk-4.0/settings.ini 里**没有** gtk-theme-name，
    所以 Breeze 那份会用 `_breeze` 名字的 GTK4 样式表也不加载。
    于是 GTK4 应用退回 libadwaita 写死的暗面（window #222226 / view #1d1d20 /
    headerbar #2e2e32 / dialog+popover #36363a），与 Frost 实测 ΔE2000
    2.32~7.01 —— 弹窗、对话框、工具提示最明显（ΔL* 约 +9，亮一档）。

    强调色**不用补**：它走 XDG portal（plasma_accentcolor_service），
    实测 org.freedesktop.appearance/accent-color 就等于 Selection.BackgroundNormal。
    所以缺口精确在**面色**，不是强调色，也不是「GTK4 完全没主题」。

    别名指向 @xxx_breeze 而不是具体色值 —— 值仍由 kde-gtk-config 维护，
    时段一变自动跟着走，所以本函数不需要 which 参数。
    放在 apply() 的早退之前，和 sync_gtk_folder_accent 同一个理由：
    gtkconfig 每次换配色都会重写 gtk.css（本机原文就是一行 `@import 'colors.css';`），
    追加的块会被抹掉，必须能自愈。靠 MARK 保证幂等。

    验证过的事（用 GTK 自己的 CssProvider，在假 HOME 上）：
      解析错误 NONE；window_bg_color → @theme_bg_color_breeze → rgb(32,36,42)
      = Frost 的 Colors:Window BackgroundNormal。整条链通。
    """
    MARK = "/* frost-gtk-names */"
    GTK4 = """
@define-color window_bg_color     @theme_bg_color_breeze;
@define-color window_fg_color     @theme_fg_color_breeze;
@define-color view_bg_color       @theme_base_color_breeze;
@define-color view_fg_color       @theme_text_color_breeze;
@define-color headerbar_bg_color  @theme_header_background_breeze;
@define-color headerbar_fg_color  @theme_header_foreground_breeze;
@define-color sidebar_bg_color    @theme_header_background_breeze;
@define-color sidebar_fg_color    @theme_header_foreground_breeze;
@define-color popover_bg_color    @theme_bg_color_breeze;
@define-color popover_fg_color    @theme_fg_color_breeze;
@define-color dialog_bg_color     @theme_bg_color_breeze;
@define-color dialog_fg_color     @theme_fg_color_breeze;
@define-color accent_bg_color     @theme_selected_bg_color_breeze;
@define-color accent_fg_color     @theme_selected_fg_color_breeze;
@define-color error_color         @error_color_breeze;
@define-color warning_color       @warning_color_breeze;
@define-color success_color       @success_color_breeze;
"""
    # GTK3 侧的两处：
    # ① 失焦窗口的选中行**极性翻转**。Qt 侧 [ColorEffects:Inactive] Enable=false，
    #    失焦选中 = 聚焦选中（深字 #171a1f 压浅强调 #68cbdf）。但 kde-gtk-config
    #    的 theme_unfocused_selected_fg 取的是 Window.ForegroundNormal（#e8eaed）、
    #    bg 取强调色压暗（#284850），变成浅字压深底 —— ΔE2000 48.19、ΔL* −48.1。
    #    BreezeDark 不会翻，因为它 Selection.ForegroundNormal 和
    #    Window.ForegroundNormal 是同一个 #fcfcfc；Frost 特意把 Selection 前景
    #    改成深色（可读性修复），这个改动没被带进 GTK 的 backdrop 态。
    # ② Breeze-Dark 的 GTK3 样式表里 107 个字面色值只有**一处**不在
    #    @define-color 行里、因此压不掉：notebook 标签页 flat 按钮 hover/active
    #    写死 #da4453（Breeze 红），压在 Frost 窗口底上只有 3.66:1，
    #    而 Frost 自己的 #ff8c94 是 7.00:1。
    GTK3 = """
@define-color theme_unfocused_selected_bg_color_breeze     @theme_selected_bg_color_breeze;
@define-color theme_unfocused_selected_bg_color_alt_breeze  @theme_selected_bg_color_breeze;
@define-color theme_unfocused_selected_fg_color_breeze     @theme_selected_fg_color_breeze;
notebook > header button.flat:active,
notebook > header button.flat:hover { color: @error_color_breeze; }
"""
    for sub, block in (("gtk-4.0", GTK4), ("gtk-3.0", GTK3)):
        p = os.path.expanduser(f"~/.config/{sub}/gtk.css")
        if not os.path.isfile(p):
            continue        # 没装 kde-gtk-config，这文件不该由我们凭空创建
        try:
            txt = open(p, encoding="utf-8").read()
            if MARK in txt:
                continue    # 幂等
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(txt.rstrip("\n") + "\n" + MARK + block)
        except OSError:
            pass            # 锦上添花，不能让 apply() 崩掉


def sync_gtk_folder_accent(which):
    """把已安装的 13 个 places 图标里冻结的强调色改成当前时段的。

    ★ 为什么 KDE 侧不需要这个、GTK 侧需要 ★
    这些 SVG 里写的是 `.ColorScheme-Accent { color: #xxxxxx; }` + fill="currentColor"。
    KDE 侧由 KIconLoader 注入真实配色（index.theme 的 FollowsColorScheme=true），
    所以那个写死的值只是 fallback、不决定观感。
    但 **GTK 用 librsvg 直出 SVG，没有任何注入** —— 三处 GTK 配置
    （gtk-3.0/settings.ini、gtk-4.0/settings.ini、~/.gtkrc-2.0）都指向 Frost，
    于是 GTK 侧的文件夹永远是构建时那个 fallback（dusk 暖金），
    夜里与 KDE 侧实测色相差 176°。
    GTK 还完全不遵守 index.theme 的 MinSize=32：GTK3/GTK4 在 16/22/24/32/48/64
    每个尺寸都解析到这个 folder.svg，所以连 16px 的侧栏也是实心金色块。

    ★ 为什么不能改用一个"中性 fallback"了事 ★
    算过：四个强调色的色相是 25.7/39.9/190.1/223.8°，几乎横跨整个色环
    （最大空隙 161.9° → 最小包含弧 198.1°）。**没有任何单一色相能同时靠近四个**，
    数学最优在 304.75°(洋红)、最坏误差仍 99°，而洋红文件夹本身就违反
    「颜色只承载语义」。所以只能真同步。

    实现要点：
      · 只改 <style> 里那一处 `color: #......`，不碰路径 —— 幂等，重复跑不累积。
      · 放在 apply() 的早退**之前**：时段可能没变，但重装过主题的话文件里
        又是构建时的 fallback 了，这样能自愈（和 sync_splash 同一个理由）。
      · 内容没变就不写盘。13 个小文件、20 分钟一次，开销可忽略。
      · touch 目录让 GTK 重新扫描图标主题。已在运行的 GTK 进程有自己的图标
        缓存，要重启才刷新 —— 这是已知限制，但总比永远错好。
      · 任何一步失败都静默跳过：这是锦上添花，不能让整个 apply() 崩掉。
    """
    accent = SCENE_ACCENTS.get(which)
    if not accent:
        return
    # ★ daylight.py 的 SCENE_ACCENTS 存的是 "r,g,b" **字符串** ★
    # （build-theme.py 里才是 tuple —— 两个文件各有一份，格式不同。
    #   直接 "%02x" % accent 会 TypeError，而 py_compile 抓不到，只有实跑才暴露。
    #   同类教训见 README #118：NAME 常量也是只存在于 build-theme.py。）
    try:
        want = "#%02x%02x%02x" % tuple(int(v) for v in str(accent).split(","))
    except (ValueError, TypeError):
        return
    d = os.path.join(DATA_HOME, "icons/Frost/places/scalable")
    if not os.path.isdir(d):
        return
    import re
    changed = 0
    try:
        names = [f for f in os.listdir(d) if f.endswith(".svg")]
    except OSError:
        return
    for fn in names:
        fp = os.path.join(d, fn)
        try:
            with open(fp, encoding="utf-8") as f:
                txt = f.read()
        except OSError:
            continue
        # 只认 .ColorScheme-Accent 那一条声明里的色值，别的一律不碰
        new = re.sub(r"(\.ColorScheme-Accent\s*\{\s*color:\s*)#[0-9a-fA-F]{6}",
                     r"\g<1>" + want, txt)
        if new == txt:
            continue
        try:
            with open(fp, "w", encoding="utf-8") as f:
                f.write(new)
            changed += 1
        except OSError:
            pass
    if changed:
        try:
            os.utime(os.path.dirname(d.rstrip("/")), None)   # touch icons/Frost
        except OSError:
            pass


def sync_splash(which):
    """把启动画面的底图换成当前时段。

    登录壁纸钉死在中性暮色（系统级设置，改不了），桌面壁纸却跟着太阳走。
    中间这一屏取当前时段的图、从暗渐亮，就把两头接上了：
    登录那一帧的暗度 → splash 起始暗度 → 桌面的真实亮度，
    构图全程不变，读起来是天光渐亮而不是换图。

    直接复制文件而不是让 QML 去读路径 —— splash 在 plasmashell 之前跑，
    环境最简单，用包内相对路径最稳。几 KB 的 SVG，复制开销可忽略。
    """
    src = os.path.join(WALL_DIR, f"FrostScene-{which}",
                       "contents", "images", "3840x2400.svg")
    if not os.path.exists(src) or not os.path.isdir(os.path.dirname(SPLASH_IMG)):
        return
    try:
        with open(src, "rb") as f:
            data = f.read()
        # 内容没变就不写，省一次磁盘写入
        if not (os.path.exists(SPLASH_IMG)
                and open(SPLASH_IMG, "rb").read() == data):
            with open(SPLASH_IMG, "wb") as f:
                f.write(data)
    except OSError:
        pass
    _sync_splash_accent(which)


def _sync_splash_accent(which):
    """把 Splash.qml 里进度条的颜色改成当前时段的强调色。

    ★ 为什么这个色不能交给 Kirigami ★
    ksplashqml 是纯 QGuiApplication（没有 QStyle / 调色板），
    `Kirigami.Theme.highlightColor` 取不到 KColorScheme。实测（真实
    ksplashqml，不是 qml6）：kdeglobals 里 ColorScheme=Frost-day
    （强调色 104,203,223）时读出 #308cc6；把 HOME 指到一个连 kdeglobals
    都没有的空目录，读出的**还是** #308cc6 —— 两种截然不同的输入给出
    同一个读数，证明它根本没在读配色。/usr/share 下三套官方 splash
    也无一使用 Kirigami.Theme 的颜色（Breeze 把文字色写死成 #eff0f1）。

    所以颜色只能由外部写进 QML。写死一个值能修，但那根条子的用意是
    「和任务栏运行指示同一套形状语言 —— 启动时见过的形状进桌面后还在」，
    写死就缝不上。于是在这里跟着时段改，和上面同步 scene.svg 是一件事。

    只替换 `color: "#rrggbb"` 那一处，用固定前缀定位，不碰别的 —— 幂等。
    内容没变就不写盘。任何一步失败都静默跳过：这是锦上添花，
    不能让整个 apply() 崩掉。
    """
    accent = SCENE_ACCENTS.get(which)
    if not accent:
        return
    try:
        want = "#%02x%02x%02x" % tuple(int(v) for v in str(accent).split(","))
    except (ValueError, TypeError):
        return
    qml = os.path.join(os.path.dirname(SPLASH_IMG), "..", "Splash.qml")
    qml = os.path.normpath(qml)
    if not os.path.isfile(qml):
        return
    # ★ 必须用显式标记定位，不能靠缩进+前缀猜 ★
    # 第一版匹配的是 '            color: "#'，结果**同时命中了进度条底槽**
    # （那条本该是 #ffffff、叠 0.16 当轨道）—— 底槽被刷成强调色，
    # 轨道和进度条同色，进度完全看不出来。
    # 生成端在那一行末尾留了 `// FROST_ACCENT_LINE`，只认它。
    MARK = "// FROST_ACCENT_LINE"
    try:
        with open(qml, encoding="utf-8") as f:
            lines = f.readlines()
        changed = False
        for i, ln in enumerate(lines):
            if MARK not in ln:
                continue
            new = f'            color: "{want}"   {MARK}\n'
            if ln != new:
                lines[i] = new
                changed = True
        if changed:
            with open(qml, "w", encoding="utf-8") as f:
                f.writelines(lines)
    except OSError:
        pass



def set_lockscreen(which):
    """让锁屏壁纸跟着时段走。

    锁屏和登录屏是两回事，这点很容易混：
      * 登录屏（plasmalogin）以 root 运行、在用户会话之前，用户改不了 —— 只能钉死一张中性图
      * 锁屏（kscreenlocker）跑在用户会话里，读 ~/.config/kscreenlockerrc —— **完全可控**
    先前这里什么都没写，kscreenlockerrc 甚至不存在，于是锁屏用 Breeze 默认壁纸 ——
    结果桌面、锁屏、登录屏三张图互不相同。现在锁屏和桌面用同一张、随时段一起变。

    ★ 先读文件比对，值没变就一个进程都不 fork ★
    这个函数在「时段未变」的早退之前被调用（因为重装主题后配置可能是陈旧的），
    而它原本无条件跑两次 kwriteconfig6 —— 一天 72 次就是 144 次无谓的进程创建。
    自己读一行文本几乎不要钱，只有真需要改时才付 fork 的代价。
    """
    wall = os.path.join(WALL_DIR, f"FrostScene-{which}")
    if not os.path.isdir(wall):
        return
    want = f"file://{wall}"
    rc = os.path.expanduser("~/.config/kscreenlockerrc")
    try:
        cur = open(rc).read()
        if f"Image={want}" in cur and "WallpaperPlugin=org.kde.image" in cur:
            return                      # 已经是对的，不用动
    except OSError:
        pass
    import subprocess
    subprocess.run(["kwriteconfig6", "--file", "kscreenlockerrc",
                    "--group", "Greeter", "--key", "WallpaperPlugin", "org.kde.image"],
                   capture_output=True)
    subprocess.run(["kwriteconfig6", "--file", "kscreenlockerrc",
                    "--group", "Greeter", "--group", "Wallpaper",
                    "--group", "org.kde.image", "--group", "General",
                    "--key", "Image", want],
                   capture_output=True)



def sync_base_scheme(which):
    """把基础方案 Frost.colors 同步成当前时段那一套。

    为什么需要：look-and-feel 的 defaults 里写的是 ColorScheme=Frost（基础方案），
    而基础方案用 DEFAULT_ACCENT（dusk 暖金）。于是在「系统设置 → 全局主题」里
    点应用，界面立刻变成暖金 —— 不管当时是白天还是夜里，
    要等下次注销重登（钩子跑 preseed）才会对。用户实际撞到过。

    解法是让基础方案本身**始终等于当前时段**。这样无论谁去应用 Frost
    （系统设置、plasma-apply-lookandfeel、还是第一次安装），拿到的都是对的颜色。

    只改 Name/ColorScheme 两行，其余整份复制 —— 基础方案要保留自己的身份，
    否则系统设置里会出现两个同名条目。
    """
    src = os.path.join(
        DATA_HOME, f"color-schemes/Frost-{which}.colors")
    dst = os.path.join(DATA_HOME, "color-schemes/Frost.colors")
    if not os.path.exists(src):
        return
    try:
        out = []
        for line in open(src, encoding="utf-8"):
            if line.startswith("Name="):
                out.append("Name=Frost\n")
            elif line.startswith("ColorScheme="):
                out.append("ColorScheme=Frost\n")
            else:
                out.append(line)
        new = "".join(out)
        if os.path.exists(dst) and open(dst, encoding="utf-8").read() == new:
            return                       # 内容没变就不写盘
        tmp = dst + ".frost-tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new)
        os.replace(tmp, dst)
    except OSError:
        pass



def _frost_is_active():
    """当前全局主题还是不是 Frost。

    用户可能在「系统设置 → 全局主题」里切走，但没跑 RESTORE.sh ——
    这种情况下 Frost 的定时器和登录钩子必须闭嘴，否则：
      * 定时器 20 分钟内就用 plasma-apply-* 把配色和壁纸抢回来（实时生效，
        用户当着面看到界面变色）
      * set_lockscreen() 还会无条件改写 ~/.config/kscreenlockerrc
      * 下次登录 preseed 又把颜色组灌回 kdeglobals
    早先只有登录钩子的第②步（tweak）有这个判断，第①步（preseed）和
    定时器调用的 apply() 都没有 —— 等于换走主题也拦不住。

    读一行文本即可，不 fork，符合热路径预算。
    """
    kg = os.path.expanduser("~/.config/kdeglobals")
    try:
        sec = False
        for line in open(kg, encoding="utf-8"):
            st = line.strip()
            if st.startswith("["):
                sec = (st == "[KDE]")
                continue
            if sec and st.startswith("LookAndFeelPackage="):
                return st.split("=", 1)[1].strip() == "com.xhhcn.frost"
    except OSError:
        pass
    return True     # 读不到就当仍是 Frost —— 宁可多做一次，也别在首次安装时罢工


def _colors_match(which):
    """kdeglobals 里实际生效的颜色，和这个时段该有的那套是否**逐键**一致。

    只比状态文件是不够的：状态文件说 night、ColorScheme= 也写着 Frost-night，
    但 kdeglobals 的 [Colors:*] 完全可能还是上一个时段的值 ——
    ColorScheme= 只是个标签，不携带颜色。真出现不一致时，只看状态文件的早退
    会让它**永远修不好**：每 20 分钟跑一次、每次判定「时段没变」直接退出。
    用户实际撞到过：重登后整个界面停在 dusk 的暖金，而当时是 night。

    ★ 必须逐键比，不能只比强调色 ★
    早先这里只比 [Colors:Selection] BackgroundNormal 一个键。后果是：
    **凡是不改强调色的配色更新，运行中的会话一律检测不到**，要等下次换时段
    才生效。实际撞到过 —— 把 Selection 组八个前景从白改成深色（可读性修复）
    并把 BackgroundAlternate 系数从 0.72 改到 0.92 之后，重装 + 重跑
    daylight.py 都被判成「无需变化」，桌面上一个像素都没变。
    这和对比度门禁是同一类教训：比对/自查的覆盖面不全会造成假通过。
    所以改成把方案文件里所有 [Colors:*] 的键都和 kdeglobals 对一遍。
    两个文件各约 5 KB，纯读不 fork，开销可忽略。
    """
    # 名字写死成 "Frost"，和本文件其它三处（215/216/422 行）一致 ——
    # daylight.py 里没有 NAME 常量，那是 build-theme.py 的。
    scheme = os.path.join(
        DATA_HOME, f"color-schemes/Frost-{which}.colors")
    kg = os.path.expanduser("~/.config/kdeglobals")

    def parse(path, only_colors=True):
        out, sec = {}, None
        try:
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    sec = line[1:-1]
                    continue
                if not sec or "=" not in line or line.startswith("#"):
                    continue
                if only_colors and not sec.startswith("Colors:"):
                    continue
                k, v = line.split("=", 1)
                out[(sec, k.strip())] = v.strip()
        except OSError:
            return None
        return out

    want = parse(scheme)
    have = parse(kg)
    if not want or have is None:
        return False        # 读不到就当不匹配，宁可多应用一次
    unapplied = _load_unapplied()
    for key, v in want.items():
        if key in unapplied:
            continue
        if have.get(key) != v:
            return False
    return True


# 「Plasma 不会写的键」缓存路径。和 STATE 放一起。
UNAPPLIED = os.path.join(CACHE_HOME, "frost-daylight-unapplied")


def _load_unapplied():
    """读回上一次成功应用后**仍然不一致**的键集合。

    ★ 为什么需要这个：逐键比对会被「Plasma 自己派生的键」永久卡住 ★
    实测：96 个键里恰好 1 个永远对不上 ——
      [Colors:Header][Inactive] ForegroundNormal
        方案文件 154,163,173 / kdeglobals 232,234,237 / BreezeDark 252,252,252
      三个值互不相同 → kdeglobals 里那个值**不是从任何方案文件抄来的**，
      是 Plasma 按活动色自己派生的。plasma-apply-colorscheme 再跑一万次
      也不会把它变成 154,163,173。
    后果很实在：_colors_match() 永远返回 False → apply() 的早退永不生效 →
    **每 20 分钟**（定时器周期）都跑一遍完整路径：
      2 次 plasma-apply-colorscheme + 1 次 plasma-apply-wallpaperimage。
    白耗电 —— 用户明确在意续航，这是保留这个缓存的**唯一**理由。
    这是我自己引入的：逐键比对（为了修「只比一个键导致假通过」）修过了头。

    ★ 更正：早先这里还写「会闪一下 day 的青色」，那条已被证否 ★
    两处都错：① 基础方案 Frost.colors 的构建期强调色是 DEFAULT_ACCENT =
    SCENE_ACCENTS["dusk"] = 245,185,66，不是 day 的 104,203,223；
    ② 更关键的是 sync_base_scheme() 会把已安装的基础方案**同步成当前时段**，
    而它就在本函数下游的早退之前调用 —— 实测已安装的 Frost.colors 与
    Frost-night.colors 逐键相同（96/96），所以「弹到基础方案」根本看不出颜色变化。
    按方法论：证否理由 ≠ 证否结论。省电那条理由仍然成立，缓存要留。

    不写死键名的原因：哪些键会被派生取决于 Plasma 版本，写死一个名字
    下个版本就可能失效或误伤。改成**自校准** ——
    一次成功应用之后仍然不一致的键，按定义就是「应用不了的键」，
    记下来在后续比对里跳过。集合为空时行为和原来完全一致。
    12 个嵌套子组键里有 11 个是能正常写入的，所以「排除所有嵌套子组」
    这种粗暴做法会白丢 11 个键的覆盖 —— 实测过才知道不能那么做。
    """
    try:
        return {tuple(line.rstrip("\n").split("\t", 1))
                for line in open(UNAPPLIED, encoding="utf-8") if "\t" in line}
    except OSError:
        return set()


def _save_unapplied(which):
    """成功应用之后调用：把仍然不一致的键记下来。

    只在 apply() 真的走完应用路径后调用 —— 那时 kdeglobals 刚被
    plasma-apply-colorscheme 写过，还对不上的就是它写不了的。
    """
    scheme = os.path.join(
        DATA_HOME, f"color-schemes/Frost-{which}.colors")
    kg = os.path.expanduser("~/.config/kdeglobals")

    def parse(path):
        out, sec = {}, None
        try:
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    sec = line[1:-1]
                    continue
                if not sec or "=" not in line or line.startswith("#"):
                    continue
                if not sec.startswith("Colors:"):
                    continue
                k, v = line.split("=", 1)
                out[(sec, k.strip())] = v.strip()
        except OSError:
            return None
        return out

    want, have = parse(scheme), parse(kg)
    if not want or have is None:
        return
    stuck = sorted(k for k, v in want.items() if have.get(k) != v)
    # 一次应用后还差**很多**键，说明不是「派生键」而是应用真的失败了
    # （比如 plasma-apply-colorscheme 静默没生效）。那种情况不该把它们
    # 记成「应用不了」—— 否则下次比对会把真正的失配也一起跳过，
    # 等于把自愈关掉。
    #
    # ★ 8 这个数不是拍的，实测过所有可达状态 ★
    # 方案共 96 个 Colors:* 键。逐对比较全部时段（含基础方案）：
    #   正常态（当前时段已生效）        →  1 键（那个真的派生键）→ 正确缓存
    #   应用完全没生效（停在别的时段）  → 25 键 → 被上限正确拦下
    #   写到一半被截断（磁盘满的形态）  → 48 键 → 被上限正确拦下
    #   基础方案 ↔ 当前时段            →  0 键（sync_base_scheme 让它们相同）
    #                                     → stuck 为空，什么都不拉黑，无害
    # 也就是说 1..8 这个区间**没有任何可达的失败状态**：最小的真实失败是
    # 25 键，上限 8 有 17 键余量。有人提过「≤8 键的瞬时失败会被误学成永久
    # 跳过」，那需要 plasma-apply-colorscheme 恰好写错 96 个键里的 ≤8 个
    # 却仍返回 0 —— 没有这种机制（它整份写，要么成要么不成）。
    # 所以不需要加计数器/TTL。真要改这个数，先重跑上面那组逐对测量。
    if len(stuck) > 8:
        return
    # 原子替换，和 sync_base_scheme / _copy_scheme_into_kdeglobals 一致。
    # 直接 open(...,"w") 会先把文件截断：并发读者（另一个 daylight.py 进程）
    # 在截断之后、写入之前读到的是空集合。实测把写入过程人为拉长到秒级，
    # 期间 _load_unapplied() 返回 set() —— 已缓存的键凭空消失。
    # 真实窗口只有微秒级、systemd oneshot 也不会自我重叠，所以后果轻微
    # （最多多跑一次完整应用路径，自愈），但两行就能消掉，没有理由不做。
    try:
        os.makedirs(os.path.dirname(UNAPPLIED), exist_ok=True)
        tmp = UNAPPLIED + ".frost-tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            for sec, k in stuck:
                fh.write(f"{sec}\t{k}\n")
        os.replace(tmp, UNAPPLIED)
    except OSError:
        pass


def apply(which, force=False):
    """切换时段：壁纸 + 配色一起换。

    配色也跟着换是刻意的 —— 强调色取自该场景的光源色（太阳/月亮），
    黄昏的暖橙风景配暖金 UI、夜里的冷月配冰蓝，
    视觉上是同一束光同时照着风景和界面。只换壁纸不换 UI 会色相打架。

    用 plasma-apply-colorscheme 而不是直接写 kdeglobals：
    它对当前会话是**实时生效**的，不需要重启 plasmashell。
    （早先这里写着「必须先写 AccentColor 才会同步 Colors:Selection」——
      那条结论后来被推翻了：写 AccentColor 反而让 Plasma 忽略配色文件
      声明的值、改用它自己减淡 27% 的派生色。详见 README 第 57 条。）
    """
    if not force and not _frost_is_active():
        return False        # 用户已经换走全局主题，不要抢回

    # 放在早退**之前**：时段可能没变，但 splash 底图未必是对的
    # （比如刚重装过主题，包里是构建时的默认图）。
    # sync_splash 内部会比对内容，一致就不写盘，白跑一次几乎零开销。
    sync_splash(which)
    set_lockscreen(which)
    sync_base_scheme(which)
    # GTK 侧不走 KIconLoader，文件夹图标里的 fallback 色要手工同步。
    # 同样放在早退之前 —— 重装主题会把它写回构建时的 dusk，需要能自愈。
    sync_gtk_folder_accent(which)
    sync_gtk_color_names()

    prev = open(STATE).read().strip() if os.path.exists(STATE) else ""
    # ★ 早退前再看一眼壁纸 ★
    # 时段没变 ≠ 每块屏都对。会话中途新建的容器（新建活动、插上外接屏）
    # 拿的是 Breeze 默认壁纸，而这里一早退就要等到下一次时段真变化 ——
    # 最长几个小时里那块屏一直是默认壁纸。
    # 和上面 sync_splash / sync_gtk_folder_accent 同一个套路：
    # 便宜的检查放在早退之前，贵的动作只在不匹配时做。
    if prev == which and not force and _colors_match(which) \
            and not _wallpaper_mismatch(which):
        return False

    # ↓ 只有真要切换才会执行到这里，subprocess 也只在这里才需要。
    #   它是最贵的 import（比基线多约 15 ms），放在函数顶部等于每次都付。
    import subprocess

    ok = True

    # ── 壁纸先、配色后。这个顺序**实测无关紧要**，别再改它 ──
    # 我一度以为顺序是有害的，推理链是这样的（每一环都能在源码里查到）：
    #   ImageStackView.qml:147  replaceEnter 的 NumberAnimation
    #     duration = round(Kirigami.Units.veryLongDuration * 2.5) = 400*2.5 = 1000ms
    #     enabled: !view.doesSkipAnimation
    #   ImageStackView.qml:87   doesSkipAnimation = currentItem 未定义
    #                              || sourceSize 不同 || skipAnimation
    #   ImageStackView.qml:70   loadImageImmediately() { loadImage(true) }  ← 跳过动画
    #   MediaProxy              onColorSchemeChanged: view.loadImageImmediately()
    # 推论：壁纸先启动 1000ms 淡化，约 82ms 后配色落地（而且因为要「弹一下」
    # 会变两次），每次都触发 loadImage(true)，把淡化掐断跳到终帧。
    #
    # ★ 实测把这个推论否掉了 ★ A/B 抓帧（spectacle -b -n -f -d 500，
    # 切换途中取一帧，把像素投影到 night→day 线段上求参数 t）：
    #     旧顺序（壁纸先）均值 t = +0.426
    #     新顺序（配色先）均值 t = +0.444
    #   5 个采样点分别 0.42/0.43/0.43/0.43/0.42 与 0.45/0.44/0.45/0.45/0.43。
    # 两者都在 44% 混合处 —— **顺序没有产生任何区别**，淡化根本没被掐断。
    # 所以那条推理链里至少有一环不成立（很可能 onColorSchemeChanged 只在
    # 壁纸真正依赖配色时才触发；本主题的场景 SVG 里 ColorScheme-* 数量是 0）。
    # 我按假前提改过一次顺序又改回来了：**建立在假前提上、还配了长篇论证的
    # 改动，比不改更糟** —— 下一个人会把那段论证当事实继续引用。
    #
    # 但这次测量有个**有用的副产品**：壁纸确实有一段 1000ms 的自带交叉淡化
    # （t≈0.44 就是证据，五点一致正是全局不透明度淡化的特征）。
    # 这直接决定了「给强调色轮换加 blendchanges」该插在哪：
    # blendchanges 会冻住当前帧再淡入新状态，**绝不能插在
    # plasma-apply-wallpaperimage 之后** —— 那会把壁纸自己的淡化冻在中途。
    wall = os.path.join(WALL_DIR, f"FrostScene-{which}")
    if os.path.isdir(wall):
        r = subprocess.run(["plasma-apply-wallpaperimage", wall],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"!! 壁纸失败: {r.stderr.strip()[:100]}", file=sys.stderr); ok = False
    else:
        print(f"!! 找不到 {wall}", file=sys.stderr); ok = False

    # ★ 绝对不要写 AccentColor ★
    # 这里曾经写它，理由记成「AccentColor 优先级高于配色方案，不写就不生效」——
    # 那是误诊。当时「配色名变了但颜色没变」的真正原因是
    # plasma-apply-colorscheme 只比对方案名、同名就跳过（下面已用弹一下解决）。
    #
    # 实际写它的后果是反的：kdeglobals 里一旦有 AccentColor，
    # Plasma 就**忽略配色文件里声明的 Colors:Selection**，改用它自己派生的减淡版。
    # 实测 dusk：声明 245,185,66 → 实际渲染 178,137,55，只剩 73%。
    # 任务栏指示条走 ColorScheme-Highlight → Colors:Selection，于是
    # 整条指示条以 73% 亮度渲染，对面板对比从 7.99:1 掉到 4.38:1，
    # normal 状态（0.50 不透明度）更是变成一摊泥褐色。
    # 不写它，四档全部拿到配色文件里声明的满亮度原值（已逐档实测）。

    scheme = f"Frost-{which}"
    # ★ 同名方案要先弹一下 ★
    # plasma-apply-colorscheme 只比对**方案名**：名字没变就当无事发生，
    # 直接返回、不重读文件。重建主题后（内容改了、名字没改）就表现为
    # 「AccentColor 更新了，但 Colors:Selection 还是旧色」——
    # 任务栏横条颜色纹丝不动。先切到基础方案再切回去，强制它真读一次。
    cur_scheme = subprocess.run(
        ["kreadconfig6", "--file", "kdeglobals", "--group", "General",
         "--key", "ColorScheme"], capture_output=True, text=True).stdout.strip()
    if cur_scheme == scheme:
        subprocess.run(["plasma-apply-colorscheme", "Frost"], capture_output=True)

    r = subprocess.run(["plasma-apply-colorscheme", scheme],
                       capture_output=True, text=True)
    if r.returncode != 0 and "already" not in (r.stdout + r.stderr).lower():
        print(f"!! 配色失败: {(r.stderr or r.stdout).strip()[:100]}", file=sys.stderr); ok = False

    if ok:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        # 原子替换，理由同 _save_unapplied：截断窗口里并发读者会读到空串，
        # 那会被当成「没有上一次状态」从而多跑一次完整应用。
        _tmp = STATE + ".frost-tmp"
        with open(_tmp, "w", encoding="utf-8") as _fh:
            _fh.write(which)
        os.replace(_tmp, STATE)
        # 刚应用完，此刻仍对不上的键就是 Plasma 写不了的（自己派生的）。
        # 记下来，下次 _colors_match() 跳过它们 —— 否则早退永不生效。
        _save_unapplied(which)
    return ok


APPLETSRC = "~/.config/plasma-org.kde.plasma.desktop-appletsrc"


def _desktop_containments(txt):
    """从 appletsrc 里挑出**桌面**容器的 id（不含面板）。

    ★ 判据是 formfactor，不是「壁纸段是否已存在」★
    原先 preseed() 用的是
        r"\\[Containments\\]\\[(\\d+)\\]\\[Wallpaper\\]\\[org\\.kde\\.image\\]\\[General\\]"
    —— 它只能匹配**已经有**壁纸段的容器。可是 Plasma 是懒创建：
    全新的容器（新建活动、刚插上的外接屏）还没有这一段，
    于是正则一个都匹配不到，那块屏/那个活动就顶着 Breeze 默认壁纸，
    而且要等到下一次时段真的变化才有机会被纠正（最长几个小时）。
    单屏且活动没变过时这个 bug 完全看不出来 —— 实测当前配置 3 个容器里
    只有 1 个桌面容器，它恰好有壁纸段，所以老正则「碰巧是对的」。

    也不能用 wallpaperplugin 当判据：实测**面板也有**
    `wallpaperplugin=org.kde.image`（容器 482/502 都有），它不区分类型。

    formfactor 才是：Planar=0（桌面）/ Horizontal=2 / Vertical=3（面板）。
    另外显式排掉 plugin 里带 panel 的 —— 往面板写 Image 无害（面板不读它）
    但是配置噪音。formfactor 缺失时按桌面处理：宁可多写一个被忽略的键，
    也不要漏掉一块真的屏。

    ★ 逐行扫，不用正则 ★
    _wallpaper_mismatch() 会在 apply() 的**每次**调用里跑（定时器 20 分钟
    一次 + 登录钩子），而 `import re` 实测 +7.1 ms（裸解释器 13.0 → 20.1）。
    本文件里 re 一直是**局部**导入的，就是为了不让冷路径付这笔钱。
    这点解析用 str.startswith / split 完全够，顺带比正则还快。
    """
    ids, cur, info = [], None, {}
    for line in txt.splitlines():
        if line.startswith("["):
            cur = None
            # 只认恰好两层的 [Containments][<id>]，子组（[...][Wallpaper][...]）跳过
            if line.startswith("[Containments][") and line.endswith("]"):
                parts = line[1:-1].split("][")
                if len(parts) == 2 and parts[1].isdigit():
                    cur = parts[1]
                    info.setdefault(cur, {})
        elif cur and "=" in line:
            k, _, v = line.partition("=")
            if k in ("plugin", "formfactor"):
                info[cur][k] = v.strip()
    for cid, d in info.items():
        if "panel" in d.get("plugin", ""):
            continue
        if d.get("formfactor", "0") != "0":
            continue
        ids.append(cid)
    return ids


def _wallpaper_mismatch(which):
    """有没有哪个桌面容器的壁纸没指向当前时段。

    给 apply() 的早退**之前**用：会话中途新建的容器（新活动 / 插上外接屏）
    拿的是 Breeze 默认壁纸，而 apply() 看到「时段没变」就早退，
    于是它能顶着默认壁纸待上几个小时。
    读一个几 KB 的 ini 再逐行扫一遍，比起每 20 分钟一次的定时器可以忽略；
    只有真不匹配时才会去调 plasma-apply-wallpaperimage（那个才贵）。
    同样不用正则，理由见 _desktop_containments 的 docstring。
    """
    try:
        txt = open(os.path.expanduser(APPLETSRC)).read()
    except OSError:
        return False
    want = f"{WALL_DIR}/FrostScene-{which}"
    targets = set(_desktop_containments(txt))
    if not targets:
        return False
    # 一遍扫出每个桌面容器当前的 Image=
    seen, cur = {}, None
    for line in txt.splitlines():
        if line.startswith("["):
            cur = None
            if line.startswith("[Containments][") and line.endswith(
                    "][Wallpaper][org.kde.image][General]"):
                cid = line[len("[Containments]["):].split("]", 1)[0]
                if cid in targets:
                    cur = cid
        elif cur and line.startswith("Image="):
            seen[cur] = line[6:].strip()
            cur = None
    # 没出现在 seen 里 = 连壁纸段都还没有（全新容器），必然算不匹配
    return any(want not in seen.get(cid, "") for cid in targets)


def preseed(which):
    """在 Plasma **启动之前**把配色和壁纸写进配置文件。

    为什么需要它：定时器最早也要等会话起来才能跑，那时 Plasma 已经
    用上一次关机时的配色渲染完了 —— 晚上关机是 night，早上登录先显示 night，
    几十秒后定时器才改成 day，于是**任务栏横条会当着面变色**。

    这里不能用 plasma-apply-* —— 它们要通过 DBus 找 plasmashell，
    而此刻 plasmashell 还没起来。

    ★ 关键：只写 ColorScheme= 这个名字是不够的 ★
    kdeglobals 里的 [Colors:*] 各组才是**实际生效**的颜色，
    ColorScheme= 只是一个标签，写它不会把 .colors 文件里的值搬过来。
    早先这里能工作纯属巧合：当时同时写了 AccentColor，逼 Plasma 重新派生了
    Colors:Selection。后来 AccentColor 被去掉（它会让 Plasma 忽略配色文件
    声明的值、改用减淡 27% 的派生色，见 README 第 57 条），
    preseed 就失去了唯一真正改颜色的手段 ——
    表现为「ColorScheme=Frost-night 但界面还是 dusk 的暖金」。
    现在直接把 .colors 里的所有颜色组逐键复制进 kdeglobals。

    ★ 返回值 ★
    None = 跳过（用户已换走全局主题）／True = 全部成功／False = 有写入失败。
    早先这个函数没有返回值，而 __main__ 无条件打印「预置为 X」——
    连「因为不是 Frost 而整个跳过」都会打印成功，那是最容易发生的一种。
    """
    if not _frost_is_active():
        return None         # 用户已经换走全局主题，登录时也不要预置

    import subprocess
    bad = []

    def kw(args, what):
        """跑一次 kwriteconfig6，失败就记下来。

        ★ 为什么要看返回码 ★ 这几处早先都是裸 capture_output=True、
        从不看 returncode。kdeglobals 只读或磁盘满时它们静默失败，
        而函数照样「成功」返回 —— 症状是「配色对了、壁纸没跟着变」
        （颜色那部分走 _copy_scheme_into_kdeglobals 的原子写，不受影响），
        没有任何线索指向 preseed。
        """
        r = subprocess.run(["kwriteconfig6", "--file"] + args,
                           capture_output=True)
        if r.returncode != 0:
            bad.append(what)
        return r.returncode == 0

    scheme = os.path.join(
        DATA_HOME, f"color-schemes/Frost-{which}.colors")
    if os.path.exists(scheme):
        _copy_scheme_into_kdeglobals(scheme)
    kw(["kdeglobals", "--group", "General",
        "--key", "ColorScheme", f"Frost-{which}"], "kdeglobals ColorScheme")
    # 清掉可能残留的 AccentColor —— 留着它会压过上面刚写进去的颜色
    kw(["kdeglobals", "--group", "General",
        "--key", "AccentColor", "--delete"], "kdeglobals AccentColor 清除")

    # 桌面壁纸：写进容器的 Wallpaper 配置组
    wall = f"file://{WALL_DIR}/FrostScene-{which}"
    try:
        txt = open(os.path.expanduser(APPLETSRC)).read()
    except OSError:
        txt = ""
    for cid in _desktop_containments(txt):
        # kwriteconfig6 会按需创建不存在的组 —— 所以这里对「还没有壁纸段
        # 的全新容器」同样有效，那正是老正则漏掉的情况。
        kw(["plasma-org.kde.plasma.desktop-appletsrc",
            "--group", "Containments", "--group", cid,
            "--group", "Wallpaper", "--group", "org.kde.image",
            "--group", "General", "--key", "Image", wall],
           f"容器 {cid} 壁纸")
        # 新容器的 wallpaperplugin 未必是 org.kde.image；不是的话上面那个
        # Image 键写了也不会被读。补一下，让键落在真正生效的插件下。
        kw(["plasma-org.kde.plasma.desktop-appletsrc",
            "--group", "Containments", "--group", cid,
            "--key", "wallpaperplugin", "org.kde.image"],
           f"容器 {cid} wallpaperplugin")

    sync_splash(which)
    set_lockscreen(which)
    sync_base_scheme(which)

    if bad:
        print("!! preseed 有写入失败：" + "、".join(bad)
              + "\n   症状通常是「配色对了、壁纸没跟着变」"
              "（颜色走原子写，不受影响）。检查 ~/.config 权限与磁盘余量。",
              file=sys.stderr)
        return False
    return True

    # ★ 不写状态文件 ★
    # 早先这里无条件写，后果是：preseed 只改了配置文件、**没有**通知
    # 正在运行的 plasmashell（那时它还没起来），但状态文件已经写成新值。
    # 于是登录后第一次定时器触发时 apply() 看到「时段没变」就早退，
    # 少了一次用 plasma-apply-* 实时生效的机会。
    # 留给 apply() 去写 —— 它成功应用之后写才是对的。
    # （_colors_match() 那道自愈也依赖这一点：颜色不匹配时必须能重跑。）


def _copy_scheme_into_kdeglobals(path):
    """把一份 .colors 里的颜色组写进 kdeglobals。

    这是 plasma-apply-colorscheme 在 DBus 之外做的那部分工作 ——
    plasmashell 还没起来时只能自己来。

    ★ 用基于行的定点替换，不用 configparser 往返 ★
    早先的实现是 configparser 读 kdeglobals → 改 → 整个写回，有两个问题：
      1. `dst.read()` 的异常被 except:pass 吞掉后**照样往下写** ——
         kdeglobals 只要有一行 configparser 啃不动，整个文件就被清空。
         这是会丢用户配置的。
      2. 即使解析成功，往返也会丢掉注释、重排键序、规范化空白 ——
         对一个用户随时可能手改的文件，这种无谓改动很讨厌。
    现在只替换要动的那几个组，其余每一行原样保留。
    """
    import re as _re
    try:
        src_txt = open(path, encoding="utf-8").read()
    except OSError:
        return False

    # 从 .colors 里取出要搬的组：[Colors:*] / [WM] / [ColorEffects:*]
    want = {}
    cur = None
    for line in src_txt.splitlines():
        st = line.strip()
        if st.startswith("["):
            cur = st if (st.startswith("[Colors:") or st == "[WM]"
                         or st.startswith("[ColorEffects:")) else None
            if cur:
                want[cur] = []
            continue
        if cur and "=" in st:
            want[cur].append(st)
    if not want:
        return False

    kg = os.path.expanduser("~/.config/kdeglobals")
    try:
        old = open(kg, encoding="utf-8").read()
    except FileNotFoundError:
        old = ""
    except OSError:
        return False            # ★ 读不了就别写 ★

    # 逐行重建：命中目标组就整组换掉，其余原样保留
    out, seen, skip = [], set(), False
    for line in old.splitlines(keepends=True):
        st = line.strip()
        if st.startswith("["):
            if st in want:
                skip = True
                seen.add(st)
                out.append(st + "\n")
                out.extend(k + "\n" for k in want[st])
                continue
            skip = False
        if not skip:
            out.append(line)
    # .colors 里有、kdeglobals 里还没有的组，追加到末尾
    for sec, keys in want.items():
        if sec not in seen:
            if out and not out[-1].endswith("\n"):
                out.append("\n")
            out.append("\n" + sec + "\n")
            out.extend(k + "\n" for k in keys)

    new_txt = "".join(out)
    # 兜底自检：新内容不该比原文短太多（组是替换不是删除，只可能变长或持平）
    if old and len(new_txt) < len(old) * 0.6:
        return False

    tmp = kg + ".frost-tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new_txt)
        os.replace(tmp, kg)     # 原子替换，避免写一半被读到
    except OSError:
        try: os.unlink(tmp)
        except OSError: pass
        return False
    return True


# ★ ExecStart 必须用运行时的真实路径 ★
# 早先写死成 %h/Documents/theme/frost/daylight.py —— 那是作者机器的位置。
# 打包分发后 install.sh 把脚本装到 ~/.local/share/frost/，
# 目标机器上根本没有那个路径，定时器每 20 分钟以 status=203/EXEC 失败。
# 而 oneshot 失败只进 journal，没有任何可见提示；偏偏登录钩子用的是
# os.path.abspath(__file__)（正确），所以登录那一刻配色壁纸完全正常 ——
# 症状是「装好了、登录时颜色对，但一整天再也不换时段」，极难联想到路径。
# 顺带显式走解释器，不依赖 .py 的可执行位。
UNIT_SERVICE = """[Unit]
Description=Frost 壁纸按时段切换

[Service]
Type=oneshot
# ★ 把安装时解析到的数据目录钉进 unit ★
# systemd user unit **不可靠地**继承 shell 里设的环境变量
# （只有走 ~/.config/environment.d/ 或 systemctl --user import-environment 的才会）。
# 不钉的话：用户在 shell 里设了 XDG_DATA_HOME，install.sh 按它装，
# 而定时器跑起来时环境里没有它 → daylight.py 回落到 ~/.local/share →
# 找不到壁纸包，每 20 分钟往 journal 里写一行「找不到」，界面一整天不变。
# 安装时是什么就写什么，运行时不再依赖环境。
Environment=XDG_DATA_HOME={data_home}
Environment=XDG_CACHE_HOME={cache_home}
ExecStart={python} {script}
"""

UNIT_TIMER = """[Unit]
Description=每 20 分钟检查一次是否该换时段

[Timer]
# ★ 必须用 OnCalendar，不能用 OnStartupSec + OnUnitActiveSec ★
# 早先那套单调定时器实测会永久卡死：
#   SubState=elapsed, Trigger: n/a, TimersMonotonic 两项 next_elapse 全是 0
# 触发一次之后就再也不武装，壁纸和配色从此停在那一刻的时段。
# 而且 Persistent= 按 systemd 文档**只对 OnCalendar 生效**，
# 配单调定时器时它什么也不做 —— 等于挂了个不起作用的保险。
#
# OnCalendar=*:0/20 是墙钟时间每 20 分钟（:00 :20 :40），
# 配 Persistent=true 时，休眠/关机跨过的时段会在恢复后立刻补跑一次 ——
# 这正好覆盖「合上盖子到傍晚才打开」这种情况。
OnCalendar=*:0/20
Persistent=true
# 允许 systemd 攒批唤醒，省电；30s 的精度对切时段绰绰有余
AccuracySec=30s

[Install]
WantedBy=timers.target
"""


def install_timer():
    import subprocess
    d = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "frost-daylight.service"), "w").write(
        UNIT_SERVICE.format(python=sys.executable or "/usr/bin/python3",
                            script=os.path.abspath(__file__),
                            data_home=DATA_HOME, cache_home=CACHE_HOME))
    open(os.path.join(d, "frost-daylight.timer"), "w").write(UNIT_TIMER)
    # ★ 三条都要看返回码 ★
    # 下面那道 is-enabled 兜底只能证明「曾经启用过」—— 它证不了
    # daemon-reload 成功（新 unit 文件是否真被加载）、也证不了 restart 成功
    # （新的 OnCalendar / Environment 是否真的生效）。
    # 失败模式：用户换了路径重装，这次 systemd 总线恰好抖一下，三条全静默失败，
    # is-enabled 却返回上一次安装留下的 0 → 打印「已启用」，
    # 而定时器还在跑**旧的** unit（旧 ExecStart 路径），
    # 某天路径彻底变了才在 journal 里看到 status=203/EXEC —— 正是下面
    # restart 那段注释担心的东西，但当初只给 enable 打了补丁。
    steps = []
    for act in ("daemon-reload",), ("enable", "frost-daylight.timer"), \
               ("restart", "frost-daylight.timer"):
        # ★ 必须 restart，不能只 enable --now ★
        # 定时器已经在跑时，enable --now 是空操作：systemd 保留旧的运行状态。
        # 改过 .timer 文件后如果不重启，新的 OnCalendar 不会生效，
        # 而旧的单调定时器一旦进入 elapsed 就永远不再武装 ——
        # 表现为「装完显示已启用，但壁纸再也不切了」。
        r = subprocess.run(["systemctl", "--user", *act], capture_output=True)
        if r.returncode != 0:
            steps.append(act[0])
    # Plasma 启动前的钩子：这个目录下的 .sh 会在会话真正拉起前被 source，
    # 此时写配置文件，Plasma 一起来就是正确的时段配色，没有闪变。
    envd = os.path.expanduser("~/.config/plasma-workspace/env")
    os.makedirs(envd, exist_ok=True)
    hook = os.path.join(envd, "frost-daylight.sh")
    here = os.path.dirname(os.path.abspath(__file__))
    open(hook, "w").write(
        "#!/bin/sh\n"
        "# Frost 启动前钩子。这个目录下的 .sh 会在会话真正拉起之前被 source。\n"
        "\n"
        # 钩子也要导出 —— preseed 走钩子不走 unit，同样不能靠环境碰运气。
        f'XDG_DATA_HOME="${{XDG_DATA_HOME:-{DATA_HOME}}}"; export XDG_DATA_HOME\n'
        f'XDG_CACHE_HOME="${{XDG_CACHE_HOME:-{CACHE_HOME}}}"; export XDG_CACHE_HOME\n'
        "\n"
        "# ① 把配色和壁纸预置成当前时段，避免登录后当着面变色\n"
        "#    只丢 stdout，**保留 stderr** —— env/ 脚本的 stderr 进会话 journal。\n"
        "#    早先写的是 >/dev/null 2>&1，两个流都丢掉，于是 preseed 里的失败\n"
        "#    诊断在登录这条路径上永远看不到（而登录正是它唯一跑的地方）。\n"
        "#    `|| true` 保留：预置失败不该拦住登录。\n"
        f"python3 {os.path.abspath(__file__)} --preseed >/dev/null || true\n"
        "\n"
        "# ② 补齐「系统设置 → 全局主题」切换时拿不到的那些设置。\n"
        "#    plasma-apply-lookandfeel 只应用一份白名单，tweak.py 写的 24 项\n"
        "#    一个都不在里面 —— 其中 panelOpacity=2 是玻璃效果的命门，\n"
        "#    缺了面板直接变不透明。所以在系统设置里切完主题，重新登录即可自动补齐。\n"
        "#    用 --appearance-only：只补外观，不碰面板几何和托盘排布，\n"
        "#    免得每次登录把用户手工调过的布局冲掉。\n"
        "#    这个时机也正好 —— plasmashell 还没起来，写 plasmashellrc 不会被覆写。\n"
        'if [ "$(kreadconfig6 --file kdeglobals --group KDE --key LookAndFeelPackage 2>/dev/null)" = "com.xhhcn.frost" ]; then\n'
        "    # 同上：丢 stdout（它正常就很啰嗦），保留 stderr 进 journal。\n"
        f"    python3 {here}/tweak.py --appearance-only >/dev/null || true\n"
        "fi\n")
    os.chmod(hook, 0o755)
    print(f"已安装启动前钩子: {hook}")
    # ★ 不能凭空宣布「已启用」★
    # 上面三个 systemctl 都是裸 subprocess.run，没有 check、也没看返回码，
    # 而这行 print 无条件执行。实测把 systemctl 换成恒返回 1 的桩：
    # 三行 "Failed to connect to bus" 之后照样打印「已启用」，退出码 0。
    # 从 TTY / SSH / 容器里装（systemd user 总线不可用）就会撞上 ——
    # 用户以为按时段切换开着，实际壁纸一整天不动，而这正是本主题最显眼的功能。
    # oneshot 失败只进 journal，没有任何可见提示，极难联想。
    enabled = subprocess.run(["systemctl", "--user", "is-enabled",
                              "frost-daylight.timer"],
                             capture_output=True).returncode == 0
    if steps:
        # 有任何一步失败就别声称成功 —— 即使 is-enabled 是 0（那只说明
        # 上一次装成功过，跑的可能还是旧 unit）。
        print("!! systemctl 这几步失败了：" + "、".join(steps)
              + "\n   定时器可能仍在跑**旧的** unit（旧路径/旧环境变量）。"
              "\n   修好 systemctl --user 后重跑：\n"
              f"   python3 {os.path.abspath(__file__)} --install",
              file=sys.stderr)
    elif enabled:
        print("已启用 frost-daylight.timer（每 20 分钟检查一次）")
    else:
        print("!! frost-daylight.timer 未能启用（systemctl --user 不可用？）\n"
              "   壁纸和配色不会随时段切换。修好后重跑：\n"
              f"   python3 {os.path.abspath(__file__)} --install",
              file=sys.stderr)
    print("停用：systemctl --user disable --now frost-daylight.timer")


if __name__ == "__main__":
    lat, lon = coords()
    el, ha = sun_elevation(lat, lon)
    which = pick(el, ha)
    if "--which" in sys.argv:
        print(f"坐标 {lat:.2f},{lon:.2f}  太阳高度角 {el:+.1f}°  → {which}")
    elif "--preseed" in sys.argv:
        # 三种结果三种输出 —— 早先无条件打印「预置为 X」，连「不是 Frost
        # 所以整个跳过」都报成功，而那是最常见的一种（用户切走主题后每次登录）。
        r = preseed(which)
        if r is None:
            print("当前全局主题不是 Frost，跳过预置")
        elif r:
            print(f"预置为 {which}（未走 DBus，供 Plasma 启动前使用）")
        else:
            sys.exit(1)          # 失败详情已由 preseed 写到 stderr
    elif "--install" in sys.argv:
        install_timer()
        apply(which, force=True)
    else:
        changed = apply(which)
        # ★ 三种结果必须分得开 ★
        # apply() 有两条返回 False 的路径，语义完全不同：
        #   1) _frost_is_active() 为假 —— 用户切走了全局主题，我们**故意**不抢回
        #   2) 时段没变且配色/壁纸都对得上 —— 真正的无需变化
        # 早先两条都打印「（无需变化）」，于是 journal 里读不出区别。
        # 实际踩到过：7/30 16:20 时段从 day 变成 dusk，日志却写「无需变化」——
        # 排查时会以为切换逻辑坏了，而真相是那会儿正在反复注销测试、
        # 主题被切成了 Breeze，跳过是**正确行为**。
        # 隔离环境对照实测：同样的 dusk→night，主题是 Breeze 时 0 次
        # plasma-apply、是 Frost 时 2 次 —— 行为本来就对，错的只是这行字。
        # _frost_is_active() 只读一行文本、不 fork，放在这里不影响热路径预算。
        if changed:
            tail = "（壁纸+配色已切换）"
        elif not _frost_is_active():
            tail = "（已跳过：当前全局主题不是 Frost）"
        else:
            tail = "（无需变化）"
        print(f"太阳高度角 {el:+.1f}° → {which}{tail}")
