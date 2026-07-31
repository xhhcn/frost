#!/usr/bin/env bash
# 安装 Frost 主题到 ~/.local/share（纯数据，无编译，无 root）
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$HERE/out"
# 认 XDG_DATA_HOME —— daylight.py 的 DATA_HOME 解析的就是这个。写死 $HOME
# 的话，XDG_DATA_HOME 一被设置，资产装到 ~/.local/share 而运行时脚本去
# $XDG_DATA_HOME 找，什么都找不到（uninstall-frost.sh 必须同步，已同步）。
DEST="${XDG_DATA_HOME:-$HOME/.local/share}"

[ -d "$OUT" ] || { echo "!! 未找到 out/，先跑: python3 build-theme.py"; exit 1; }

echo "==> 安装 Plasma 样式"
mkdir -p "$DEST/plasma/desktoptheme"
rm -rf "$DEST/plasma/desktoptheme/Frost"
cp -r "$OUT/desktoptheme/Frost" "$DEST/plasma/desktoptheme/"

echo "==> 安装配色方案"
mkdir -p "$DEST/color-schemes"
cp "$OUT/color-schemes/Frost"*.colors "$DEST/color-schemes/"

echo "==> 安装全局主题包"
mkdir -p "$DEST/plasma/look-and-feel"
rm -rf "$DEST/plasma/look-and-feel/com.xhhcn.frost"
cp -r "$OUT/look-and-feel/com.xhhcn.frost" "$DEST/plasma/look-and-feel/"

echo "==> 安装布局模板"
mkdir -p "$DEST/plasma/layout-templates"
rm -rf "$DEST/plasma/layout-templates/com.xhhcn.frost.topbarDock"
cp -r "$OUT/layout-templates/com.xhhcn.frost.topbarDock" "$DEST/plasma/layout-templates/"

echo "==> 安装 KWin 最小化动画（squash 逐行照抄 + 提层）"
# 唯一一处「代码」资产。与 Breeze 的 squash 语义差异是 elevate() 辅助函数
# 加**五处**调用：两个槽开头各 elevate(true)、两条「无 iconGeometry 早退」
# 路径上各 elevate(false)、animationFinished 里 elevate(false)。
# ★ 早退那两处不是多余的 ★ 删掉它们，没有任务栏条目的窗口会永久提层 ——
# 症状极隐蔽（只有它本该被别的窗口盖住时才看得出来），且不会自愈。
# 见 build-theme.py 的 kwin_effect_files() 对照表。
mkdir -p "$DEST/kwin/effects"
rm -rf "$DEST/kwin/effects/frost_minimize"
cp -r "$OUT/kwin-effects/frost_minimize" "$DEST/kwin/effects/"

echo "==> 安装图标主题"
mkdir -p "$DEST/icons"
rm -rf "$DEST/icons/Frost"
cp -r "$OUT/icons/Frost" "$DEST/icons/"

# Arch 徽标：各图标主题里的都是「蓝圆底 + 白 A」，
# 系统自带的 /usr/share/pixmaps/archlinux-logo.svg 才是裸的官方标。
# 放进 Frost 的 apps/ 目录，就能盖掉继承链上 Fluent 那个圆底版本。
ARCH_LOGO=/usr/share/pixmaps/archlinux-logo.svg
if [ -f "$ARCH_LOGO" ]; then
    mkdir -p "$DEST/icons/Frost/apps/scalable"
    # 官方 SVG 有三条 path：第一条是 A 形，另两条是 ™ 标记；
    # 填充色写死 Arch 蓝 (#1793d1)。
    # 面板上一排托盘图标都是细线单色，蓝色徽标在里面很突兀 ——
    # 只取 A 形、丢掉 ™、改用 currentColor，让它跟随主题文字色。
    python3 - "$ARCH_LOGO" "$DEST/icons/Frost/apps/scalable" <<'PYEOF'
import re, sys, os
src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()
paths = re.findall(r'<path[^>]*\sd="([^"]{200,})"', s)   # 只要长路径 = A 形
vb = re.search(r'viewBox="([^"]*)"', s)
vb = vb.group(1) if vb else "0 0 256 256"
if paths:
    # 用 Breeze 图标的配色类机制：Plasma 会把 .ColorScheme-Text 的 color
    # 替换成当前配色的文字色，图标就跟着主题走（明暗主题都对）。
    # 只写 fill="currentColor" 而不给 class 的话，单独渲染会是黑色。
    svg = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
           f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" '
           f'width="256" height="256">\n'
           f'  <defs><style id="current-color-scheme" type="text/css">'
           f'.ColorScheme-Text {{ color:#e8eaed; }}</style></defs>\n'
           f'  <path d="{paths[0]}" class="ColorScheme-Text" fill="currentColor"/>\n'
           f'</svg>\n')
    for n in ("distributor-logo-archlinux", "archlinux",
              "start-here-archlinux", "start-here-archlinux-symbolic"):
        open(os.path.join(dst, n + ".svg"), "w").write(svg)
    print("    Arch 徽标：单色版（只取 A 形，currentColor 跟随主题）")
else:
    print("    !! 未能从官方 SVG 提取路径，回退到原图")
    import shutil
    for n in ("distributor-logo-archlinux", "archlinux", "start-here-archlinux"):
        shutil.copy(src, os.path.join(dst, n + ".svg"))
PYEOF
else
    echo "    !! 未找到 $ARCH_LOGO"
fi

# ---- 菜单分类图标 ----
#
# 默认：**不覆盖**，让继承链自己解决。
#
# 为什么最终选了单色。这套主题里颜色是有语义的：
#   * 强调色  = 时刻（跟着太阳走）
#   * 选中/悬停/焦点 = 状态
# 往侧栏塞 21 个彩色分类图标，等于把颜色降格成装饰 —— 既稀释了强调色
# 作为信号的强度，本身又是死的（换时段、换壁纸它们纹丝不动）。
#
# 而且实测继承链的结果比覆盖更好：Fluent-dark 自带
# symbolic/categories/applications-*-symbolic.svg（单色 #dedede），
# 和托盘用的是同一套 Fluent 图标 —— 整个界面归一到一个家族，
# 比「托盘 Fluent 单色 + 菜单 Fluent 彩色」的混搭干净。
#
# 这终究是审美取舍，所以留开关。想回到彩色分类图标：
#     FROST_COLOR_CATEGORIES=1 bash install-frost.sh
if [ "${FROST_COLOR_CATEGORIES:-0}" = "1" ]; then
    # 判据：以 /usr/share/desktop-directories/*.directory 为权威 ——
    # 那些文件的存在意义就是定义菜单分类，它们 Icon= 的名字按定义就是分类图标。
    # 按 applications-/preferences- 前缀猜会漏掉 Help、Editors、Terminal 等 7 个。
    SRC_ICONS=/usr/share/icons/Fluent-dark
    if [ -d "$SRC_ICONS" ]; then
        ICONDIR="$DEST/icons/Frost/categories/scalable"
        mkdir -p "$ICONDIR"
        rm -f "$ICONDIR"/*.svg 2>/dev/null || true
        WANT=$(
            grep -h "^Icon=" /usr/share/desktop-directories/*.directory 2>/dev/null \
              | sed 's/^Icon=//' | grep -E -- '-symbolic$' | sort -u
            echo "applications-all-symbolic"
        )
        n=0
        for name in $WANT; do
            base="${name%-symbolic}"
            # 先筛彩色再取最大：Fluent 的 scalable/apps/ 是应用图标（不少是单色），
            # 32/categories/ 才是彩色分类图标。只按尺寸排会挑到单色的 scalable 版。
            best=""; best_sz=-1
            for cand in $(find -L "$SRC_ICONS" -name "$base.svg" 2>/dev/null | grep -v "@[23]x" || true); do
                ncol=$(grep -oE '#[0-9a-fA-F]{6}' "$cand" 2>/dev/null | sort -u | wc -l)
                [ "${ncol:-0}" -lt 2 ] && continue
                case "$cand" in */scalable/*) sz=9999 ;;
                    *) sz=$(printf '%s\n' "$cand" | grep -oE '/[0-9]+/' | head -1 | tr -d '/') ;;
                esac
                [ -z "$sz" ] && sz=0
                if [ "$sz" -gt "$best_sz" ]; then best="$cand"; best_sz="$sz"; fi
            done
            [ -z "$best" ] && continue
            cp -L "$best" "$ICONDIR/$name.svg"; n=$((n+1))
        done
        echo "    菜单分类图标：彩色覆盖 $n 个（FROST_COLOR_CATEGORIES=1）"
    fi
else
    # 清掉上一次装的彩色覆盖，否则残留会继续生效。
    # 只删 .svg，**保留目录本身** —— index.theme 声明了 categories/scalable，
    # 目录不存在的话下次开开关时就是「声明了但没有」的半吊子状态。
    rm -f "$DEST/icons/Frost/categories/scalable"/*.svg 2>/dev/null || true
    mkdir -p "$DEST/icons/Frost/categories/scalable"
    echo "    菜单分类图标：交给继承链（Fluent symbolic 单色，与托盘同一家族）"
    echo "      要彩色版：FROST_COLOR_CATEGORIES=1 bash install-frost.sh"
fi

gtk-update-icon-cache -f -t "$DEST/icons/Frost" 2>/dev/null || true

# ---- Konsole 终端配色 ----
# 终端原本是唯一没统一进来的地方：面板/窗口/文件管理器都是 Frost，
# 一开终端却是另一套颜色。
if [ -f "$OUT/konsole/Frost.colorscheme" ]; then
    mkdir -p "$DEST/konsole"
    cp "$OUT/konsole/Frost.colorscheme" "$DEST/konsole/"
    # ★ 光装配色不够，还要装 profile ★
    # 只装 .colorscheme 的话，用户必须自己去「设置 → 编辑当前方案 → 外观」
    # 里选 Frost —— 这行手工步骤在这里打印了很久。装一个 profile 并由
    # tweak.py 把它设成 konsolerc 的 DefaultProfile，配色才会自动生效。
    # 实测确认：装 profile 之前新开的终端用的是 Konsole 默认配色
    # （截图里底色不是 23,26,31），装了之后才是 Frost；
    # Konsole 的 DBus 也确认 /Windows/1 default=Frost。
    if [ -f "$OUT/konsole/Frost.profile" ]; then
        cp "$OUT/konsole/Frost.profile" "$DEST/konsole/"
        echo "    Konsole 配色 + profile 已装（新开的终端自动是 Frost）"
    else
        echo "    Konsole 配色已装（Konsole → 设置 → 编辑当前方案 → 外观 → 选 Frost）"
    fi
fi

echo "==> 安装壁纸"
mkdir -p "$DEST/wallpapers"
rm -rf "$DEST/wallpapers/FrostScene-"*
cp -r "$OUT/wallpapers/FrostScene-"* "$DEST/wallpapers/"

# ---- 光标主题（可选组件）----
# ★ 目标名是 Frost-cursors，不是 Frost ★
# $DEST/icons/Frost 是**图标**主题（文件夹 + Arch 徽标），它的 index.theme
# 里 Inherits=Fluent-dark,... 是给图标继承链用的；光标继承要的是
# Inherits=breeze_cursors。一个 index.theme 没法同时充当两者，合进去会打架。
# 光标包自己的 index.theme 写 Name=Frost，所以系统设置里仍然显示「Frost」，
# 而 kcminputrc 存的是目录名 Frost-cursors。
#
# out/cursors 不存在 = 构建时缺 rsvg-convert / xcursorgen，build-theme.py
# 已经警告过并跳过。这里静默跳过即可，光标继续用 breeze_cursors。
if [ -d "$OUT/cursors/Frost-cursors" ]; then
    echo "==> 安装光标主题"
    mkdir -p "$DEST/icons"
    rm -rf "$DEST/icons/Frost-cursors"
    cp -r "$OUT/cursors/Frost-cursors" "$DEST/icons/"
    echo "    $(ls "$DEST/icons/Frost-cursors/cursors" | wc -l) 个光标名（应用见 apply-frost.sh）"
else
    echo "==> 光标主题：跳过（构建时未生成，缺 rsvg-convert / xcursorgen）"
fi

echo "==> 刷新缓存"
# ★ 必须清 plasma_theme_<Id>.kcache ★
# Plasma 把渲染好的 SVG 缓存在这里，不清的话改了 SVG 也看不到效果 ——
# 会误以为「主题没生效」，实际是缓存挡着。
rm -f "$HOME/.cache/plasma_theme_Frost"*.kcache
rm -f "$HOME/.cache/icon-cache.kcache"
# KSvg 还有第二个缓存，只清 plasma_theme_*.kcache 不够
rm -f "$HOME/.cache/ksvg-elements"
kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
rm -f "$HOME/.cache/plasma_theme_Frost"*.kcache 2>/dev/null || true

# ★ 必须把基础方案同步成当前时段，否则「从系统设置应用主题」会拿到黄色 ★
# look-and-feel 的 defaults 里写的是 ColorScheme=Frost（**基础**方案），
# 而基础方案是用 DEFAULT_ACCENT（dusk 暖金 245,185,66）构建的。
# 上面刚把它原样拷进 $DEST —— 如果就这样停手，用户去
# 「系统设置 → 全局主题 → 应用」，拿到的就是 dusk 的黄色，
# 而且要等最长 20 分钟（定时器周期）才会被 sync_base_scheme 纠正。
# 实测撞到过：23:40 跑完本脚本，随即从系统设置应用 → 强调色 245,185,66，
# 当时是 night，应该是 152,173,230。
#
# 发布包的 install.sh 没有这个问题：它结尾跑 `daylight.py --install`，
# 而那条会 apply(force=True) → 内部第一步就是 sync_base_scheme。
# 这里补齐同一件事，让两条安装路径行为一致。
# ★ 范围：只同步「我们自己装出去的资产」，不碰用户配置 ★
# 上面 cp 进 $DEST 的两样东西带着构建时的时段：
#   · color-schemes/Frost.colors                     强调色 = DEFAULT_ACCENT(dusk)
#   · look-and-feel/.../splash/{Splash.qml,images/}  同上
# 两者都由 daylight.py 在运行时按时段重写，所以装完必须立刻同步一次，
# 否则「从系统设置应用」拿到 dusk 黄、开机 splash 也是 dusk 的强调色。
# 不调 set_lockscreen / sync_gtk_* —— 那些写的是**用户配置**，
# 属于 apply-frost.sh 的职责，本脚本只管装资产。
# 也不调 apply()：它不带 force 时会被 _frost_is_active() 挡住
# （新机器上还没应用 Frost），带 force 又会顺手改壁纸和配色 —— 都不是这里该做的。
if [ -f "$HERE/daylight.py" ]; then
    python3 - "$HERE/daylight.py" <<'PYEOF' || echo "    !! 资产时段同步失败，从系统设置应用可能拿到构建时的强调色"
import importlib.util, sys
spec = importlib.util.spec_from_file_location("dl", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
lat, lon = m.coords()
el, ha = m.sun_elevation(lat, lon)
which = m.pick(el, ha)
m.sync_base_scheme(which)   # 基础方案 → 当前时段（决定系统设置里应用出来的颜色）
m.sync_splash(which)        # splash 底图 + 强调色行（内部会调 _sync_splash_accent）
print(f"    已装资产同步成当前时段：{which}（基础方案 + splash）")
PYEOF
fi

echo
echo "已安装:"
echo "  Plasma 样式  $DEST/plasma/desktoptheme/Frost"
echo "  配色         $DEST/color-schemes/Frost.colors"
echo "  全局主题     $DEST/plasma/look-and-feel/com.xhhcn.frost"
echo "  布局模板     $DEST/plasma/layout-templates/com.xhhcn.frost.topbarDock"
echo
echo "应用:      bash $HERE/apply-frost.sh          # 只换外观，保留现有面板"
echo "含布局:    bash $HERE/apply-frost.sh --layout # 顶栏 + 底部 Dock（会重排面板）"
echo "还原:      bash $HERE/restore-default.sh"
