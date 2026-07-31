#!/usr/bin/env bash
# 卸载 Frost：先切回 Breeze，再删除主题文件
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 认 XDG_DATA_HOME：daylight.py 的 DATA_HOME 就是这么解析的，写死 $HOME
# 的话「装在 A、卸 B」（发布包里同一处已修，见 package-frost.sh 的 BIN）。
# install-frost.sh 必须同步改，两边始终是同一个解析。
DEST="${XDG_DATA_HOME:-$HOME/.local/share}"

echo "==> 1/2  切回默认主题"
bash "$HERE/restore-default.sh"

echo
echo "==> 附加  还原启动画面 + 停用时段切换"
# ksplashrc 指向的包马上要被删，不改回去开机就是空白 splash
kwriteconfig6 --file ksplashrc --group KSplash --key Theme org.kde.breeze.desktop
systemctl --user disable --now frost-daylight.timer 2>/dev/null || true
# ★ 两个缓存都要删，路径必须认 XDG_CACHE_HOME ★
# frost-daylight-unapplied 是 _save_unapplied() 写的「Plasma 写不进去的键」
# 自校准集合。留着的话下次装回来会带着上一轮的结论，自愈逻辑的起点就不干净。
# 路径不能写死 $HOME/.cache —— daylight.py 的 CACHE_HOME 解析的是
# ${XDG_CACHE_HOME:-~/.cache}，写死就删不到它真正写的那个文件。
# （发布包的 uninstall.sh 已经删这两个，这条是补齐开发侧的对称。）
_FC="${XDG_CACHE_HOME:-$HOME/.cache}"
rm -f "$HOME/.config/plasma-workspace/env/frost-daylight.sh" \
      "$HOME/.config/systemd/user/frost-daylight.service" \
      "$HOME/.config/systemd/user/frost-daylight.timer" \
      "$_FC/frost-daylight-state" \
      "$_FC/frost-daylight-unapplied"
systemctl --user daemon-reload 2>/dev/null || true

echo "==> 2/2  删除 Frost 文件"
# 五套配色（不是一套）、图标主题、五个壁纸包，早先都漏了 ——
# 漏掉的后果不只是占空间：kdeglobals 里若还留着 Theme=Frost / ColorScheme=Frost-day，
# 卸载后这些名字指向不存在的资源，界面会回落到一半 Breeze 一半空白。
# ★ icons/Frost 和 icons/Frost-cursors 是**两个不同的主题**，都要删 ★
# 前者是图标主题（文件夹 + Arch 徽标），后者是光标主题。分开是因为一个
# index.theme 的 Inherits= 没法同时服务图标继承链和光标继承链。
# 光标主题是可选组件，构建时缺 rsvg-convert/xcursorgen 就没有它 ——
# rm -rf 对不存在的路径是无害的，不用加判断。
rm -rf "$DEST/plasma/desktoptheme/Frost" \
       "$DEST/plasma/look-and-feel/com.xhhcn.frost" \
       "$DEST/plasma/layout-templates/com.xhhcn.frost.topbarDock" \
       "$DEST/icons/Frost" \
       "$DEST/icons/Frost-cursors" \
       "$DEST/kwin/effects/frost_minimize" \
       "$DEST/frost"
# ★ $DEST/frost 必须删，即使本脚本自己不创建它 ★
# 它是**发布包**的 install.sh 建的（BIN="$DEST/frost"，里面是 daylight.py /
# tweak.py / __pycache__，约 110KB）。装发布包、之后又克隆仓库跑本脚本的用户，
# 会留下这一坨 —— 上面那几行刚把 systemd 单元删了，所以它们是彻底的死文件，
# 而脚本照样打印「已删除」。包内 uninstall.sh 一直删它，这里是补齐对称。
# rm -rf 对不存在的路径无害，从仓库安装的用户不受影响。

# ★ 删掉特效目录还不够 ★
# KWin 已经把它加载进内存了；不显式卸载的话，最小化动画会继续跑到
# 下次 KWin 重启为止，而那时脚本已经没了 —— 表现为"卸载后动画还在，
# 重启后动画突然消失"。同时把 KDE 默认的 squash 装回来。
# ★ 措辞更正：frost_minimize 是本主题**当前在装**的资产 ★
# 早先这里写「旧安装可能还装着 …（现在主题用自带的 squash）」—— 那是错的。
# 实测 isEffectLoaded frost_minimize → true、squash → false，
# 而且 build-theme.py / install-frost.sh / package-frost.sh / tweak.py
# 六条路径都在引用它。下面这三条**动作**在卸载语境下依然正确且必需
# （卸掉自制的、把 KDE 默认的 squash 装回来、清掉开关键），只是理由变了。
# 不要因为这段注释过期就顺手删掉动作 —— 本轮已经因为类似判断反复删改四次。
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.unloadEffect frost_minimize >/dev/null 2>&1 || true
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.loadEffect   squash          >/dev/null 2>&1 || true
kwriteconfig6 --file kwinrc --group Plugins --key frost_minimizeEnabled --delete 2>/dev/null || true
rm -f  "$DEST"/color-schemes/Frost.colors \
       "$DEST"/color-schemes/Frost-*.colors
rm -rf "$DEST"/wallpapers/FrostScene-*
rm -f  "$DEST"/konsole/Frost.colorscheme \
       "$DEST"/konsole/Frost.profile
# konsolerc 的 DefaultProfile 指向刚删掉的 profile，不清就是死引用
# （Konsole 会静默回退到内置默认，表面能用但配置脏了）。
# 只在值确实是我们写的时候删，不碰用户自己选的别的 profile。
if [ "$(kreadconfig6 --file konsolerc --group "Desktop Entry" --key DefaultProfile 2>/dev/null)" = "Frost.profile" ]; then
    kwriteconfig6 --file konsolerc --group "Desktop Entry" --key DefaultProfile --delete 2>/dev/null || true
    echo "    已清除 Konsole DefaultProfile（原先指向 Frost.profile）"
fi

# 锁屏壁纸：daylight.py 的 set_lockscreen() 写过它，但早先没人还原 ——
# 卸载后 kscreenlockerrc 仍指向已被删除的 FrostScene-* 目录，
# 锁屏会退化成纯黑或 Plasma 的兜底图。
if kreadconfig6 --file kscreenlockerrc --group Greeter --group Wallpaper \
        --group org.kde.image --group General --key Image 2>/dev/null | grep -q FrostScene; then
    kwriteconfig6 --file kscreenlockerrc --group Greeter --group Wallpaper \
        --group org.kde.image --group General --key Image --delete 2>/dev/null || true
    echo "    已清除锁屏壁纸设置（原先指向 Frost 壁纸）"
fi

# ★ 桌面壁纸：和上面锁屏**完全同一个失败模式**，但早先只修了锁屏那一半 ★
# 上面第 58 行 rm -rf 掉了 wallpapers/FrostScene-*，而 daylight.py 的
# preseed()/apply() 往**每个**桌面容器写过
#   [Containments][N][Wallpaper][org.kde.image][General] Image=file://…/FrostScene-x
# 不清的话卸载后桌面背景指向一个不存在的目录 —— 表现为桌面变成纯色/兜底图，
# 用户刚卸完主题就发现壁纸坏了，且没有任何线索。
# 必须遍历所有容器：外接显示器各有自己的容器，id 由 plasmashell 分配，写不死。
# 只删指向 FrostScene 的那些（对照验证过：指向别处的容器不会被选中）。
# 局限：我们没有记录用户原来的壁纸，所以这里只能删掉键让 Plasma 用默认值，
# 无法还原成他原来那张图 —— 和锁屏那条一样的取舍。
_A="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"
if [ -f "$_A" ]; then
    awk -F'[][]' '
      /^\[Containments\]\[[0-9]+\]\[Wallpaper\]\[org\.kde\.image\]\[General\]$/ { cid=$4; next }
      /^\[/ { cid="" }
      cid && /^Image=.*FrostScene/ { print cid }
    ' "$_A" | sort -u | while IFS= read -r cid; do
        kwriteconfig6 --file plasma-org.kde.plasma.desktop-appletsrc \
            --group Containments --group "$cid" \
            --group Wallpaper --group org.kde.image --group General \
            --key Image --delete 2>/dev/null || true
        echo "    已清除桌面容器 $cid 的壁纸设置（原先指向 Frost 壁纸）"
    done
fi
rm -f  "$_FC/plasma_theme_Frost"*.kcache "$_FC/icon-cache.kcache"
rm -rf "$_FC/ksvg-elements"
kbuildsycoca6 --noincremental >/dev/null 2>&1
echo "    已删除"
echo

# ★ 系统级登录壁纸：本脚本删不掉，但绝不能装作不存在 ★
# install-login.sh 用 sudo 把壁纸装到 /usr/share/wallpapers/FrostLogin。
# 那是 root 所有的，这个脚本（普通用户）没有权限删。
# 早先这里什么都不做就直接打印「完成。」—— 于是「已完全卸载」是假的：
# 系统目录里留着 Frost 的文件，而且如果登录屏幕正指向它，
# 卸载后登录界面会变成空白或回退到默认图，用户不知道为什么。
# 现在的做法：检测 + 给出确切命令，并且**不再声称干净完成**。
LOGIN_DST="/usr/share/wallpapers/FrostLogin"
if [ -d "$LOGIN_DST" ]; then
    echo "────────────────────────────────────────────────────────"
    echo "!! 还有系统级残留（需要 root，本脚本无权删除）："
    echo "     $LOGIN_DST"
    echo
    echo "   删除它："
    echo "     sudo rm -rf $LOGIN_DST"
    echo
    echo "   如果你曾在「系统设置 → 登录屏幕」里选过「Frost · 登录」，"
    echo "   请在删除**之前**先去那里改回别的壁纸 —— 否则登录界面会指向"
    echo "   一个不存在的路径。那个设置在 /var/lib/plasmalogin 下，"
    echo "   只能走图形界面的 polkit 提权改，脚本碰不到。"
    echo "────────────────────────────────────────────────────────"
    echo
    echo "完成（用户级已全部卸载；上面那一项待你手动处理）。"
else
    echo "完成。"
fi

# ---- Darkly（Lightly Qt6 分支）----
# 清单路径按脚本自身位置推导，不写死 /home/hui ——
# 这个脚本在 frost/ 下，清单在它的上一级（theme/）。
MANIFEST="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/lightly_installed.txt"
echo "==> 附加  卸载 Darkly"
if [ -f "$MANIFEST" ]; then
    while IFS= read -r f; do [ -e "$f" ] && rm -f "$f"; done < "$MANIFEST"
    echo "    已按清单删除 Darkly 的文件"
elif [ -e "$HOME/.local/lib/plugins/styles/darkly6.so" ]; then
    # ★ 清单不存在时不能什么都不做 ★
    # 整段原来被 `if [ -f "$MANIFEST" ]` 包着。而清单只有 install-lightly.sh
    # 从 cmake 的 install_manifest.txt 拷过来才有 —— 它的 SRC 长期指向一个
    # 不存在的目录（见那个脚本开头的注释），所以清单**从来没被生成过**。
    # 实测：lightly_installed.txt 不存在，而
    # ~/.local/lib/plugins/styles/darkly6.so 1081608 字节实实在在装着。
    # 于是整段被跳过 —— 连 darklyrc 和 environment.d 那两个**我们自己写的**
    # 文件都留着，而脚本一声不响打印「完成」。「已完全卸载」是假的。
    echo "    !! 找不到清单 $MANIFEST，无法按文件删除 Darkly 本体。"
    echo "       仍装着的插件（需要你手动删）："
    find "$HOME/.local/lib/plugins" -name "*arkly*" 2>/dev/null | sed 's|^|         |'
fi
# 这两个文件是 tweak.py / install-lightly.sh 写的，不依赖清单，无条件删。
# 90-local-qt-plugins.conf 尤其要删 —— 它把 QT_PLUGIN_PATH 永久指向
# ~/.local/lib/plugins，留着会影响所有 Qt 应用的插件搜索。
rm -f "$HOME/.config/darklyrc" \
      "$HOME/.config/environment.d/90-local-qt-plugins.conf"
echo "    已清除 darklyrc 与 QT_PLUGIN_PATH 配置"
