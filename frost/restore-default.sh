#!/usr/bin/env bash
# ============================================================
#  Revert to the default Plasma theme (Breeze Dark).
#  Frost's files stay installed — this only changes the look.
#
#    bash restore-default.sh
#
#  To remove Frost's files as well, use uninstall-frost.sh.
# ============================================================
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"


echo "==> 1/3  用 Plasma 官方工具切回 Breeze Dark 全局主题"
plasma-apply-lookandfeel -a org.kde.breezedark.desktop 2>/dev/null && echo "    ok" || echo "    (跳过)"
plasma-apply-desktoptheme default            2>/dev/null && echo "    Plasma 样式 -> default" || true
plasma-apply-colorscheme  BreezeDark         2>/dev/null && echo "    配色 -> BreezeDark"    || true
# 光标：这一条同时负责三件事，别删。
#   1. 写 kcminputrc [Mouse] cursorTheme
#   2. 触发 kde-gtk-config 的 kded 模块，把 gtk-3.0/gtk-4.0/.gtkrc-2.0 里的
#      gtk-cursor-theme-name 一并同步回 breeze_cursors —— 实测验证过：
#      往 settings.ini 写一个哨兵值再切换光标主题，哨兵会被覆盖。
#      所以本脚本**不需要**自己动 GTK 文件。
#   3. 通知运行中的会话立即换回
plasma-apply-cursortheme  breeze_cursors     2>/dev/null && echo "    光标 -> breeze_cursors（GTK 由 kde-gtk-config 跟随）" || true

echo "==> 2/3  还原窗口装饰 / 图标 / 控件风格"
kwriteconfig6 --file kwinrc    --group org.kde.kdecoration2 --key library org.kde.breeze
kwriteconfig6 --file kwinrc    --group org.kde.kdecoration2 --key theme   Breeze
kwriteconfig6 --file kdeglobals --group Icons --key Theme  breeze-dark
kwriteconfig6 --file kdeglobals --group KDE   --key widgetStyle Breeze
# 启动画面：不还原的话，ksplashrc 仍指向已删除的 com.xhhcn.frost，开机是空白 splash
kwriteconfig6 --file ksplashrc --group KSplash --key Theme org.kde.breeze.desktop

# ★ 必须停掉时段切换，否则这次还原会被撤销 ★
# frost-daylight.timer 每 20 分钟把 Frost 的配色和壁纸重新写回去，
# 启动前钩子还会在下次登录时抢先写一遍 —— 不停掉的话，
# 这个脚本跑完看着是好的，二十分钟后又变回 Frost。
systemctl --user disable --now frost-daylight.timer 2>/dev/null || true
# 锁屏壁纸同样要还原，否则指向马上要被删的 Frost 壁纸目录
if kreadconfig6 --file kscreenlockerrc --group Greeter --group Wallpaper \
        --group org.kde.image --group General --key Image 2>/dev/null | grep -q FrostScene; then
    kwriteconfig6 --file kscreenlockerrc --group Greeter --group Wallpaper \
        --group org.kde.image --group General --key Image --delete 2>/dev/null || true
    echo "    锁屏壁纸设置已清除"
fi
# ★ WallpaperPlugin 也是 daylight.py 写的，只删 Image 不够 ★
# set_lockscreen() 无条件写 [Greeter] WallpaperPlugin=org.kde.image
# （本机现在 kscreenlockerrc 里就有这一行）。只删 Image 的话它留着 ——
# 用户原本若用 org.kde.slideshow，幻灯片被静默改掉且永不还原。
kwriteconfig6 --file kscreenlockerrc --group Greeter \
    --key WallpaperPlugin --delete 2>/dev/null || true
rm -f "$HOME/.config/plasma-workspace/env/frost-daylight.sh"
echo "    已停用 frost-daylight 时段切换（含启动前钩子）"
echo "    启动画面 -> org.kde.breeze.desktop"

# ★ tweak.py 写进 kwinrc 的特效设置也要撤 ★
# 这些不属于任何主题包，切回 Breeze 不会自动还原 —— 不撤的话，
# 用户以为回到了默认，实际最小化动画仍然是关的、模糊强度仍然是 13。
# 用 --delete 而不是写回默认值：让 KDE 自己用内置默认，
# 免得哪天上游改了默认值，这里写死的旧值反而成了新的偏离。
for k in squashEnabled magiclampEnabled blurEnabled frost_minimizeEnabled windowapertureEnabled; do
    kwriteconfig6 --file kwinrc --group Plugins --key "$k" --delete 2>/dev/null || true
done
for k in BlurStrength NoiseStrength; do
    kwriteconfig6 --file kwinrc --group Effect-blur --key "$k" --delete 2>/dev/null || true
done
kwriteconfig6 --file kdeglobals --group KDE --key contrast      --delete 2>/dev/null || true
kwriteconfig6 --file kdeglobals --group KDE --key frameContrast --delete 2>/dev/null || true
# ★ plasmashellrc 的面板不透明度同样不属于任何主题包 ★
# tweak.py（含 --appearance-only 登录钩子）写 [PlasmaViews][Panel N][Defaults]
# panelOpacity=2（半透明）。breeze 的 look-and-feel defaults 里没有
# PlasmaViews 段，所以切回 Breeze 不会还原它。上面刚把 blurEnabled 删了 ——
# 不删这个就变成「半透明但不模糊」，比 Breeze 默认还难看，用户不知道去哪改。
# 本机实测 plasmashellrc 里有两处 panelOpacity=2（[PlasmaViews][Panel 482]
# 与 [Panel 502]，两级组、没有第三级），所以要遍历所有面板组，
# 不能只改一个写死的组名 —— 面板 id 是 plasmashell 分配的，每台机器不同。
# 正则整行锚定（$ 结尾）而不是 [^]]*.* ：后者遇到假想的三级组
# [PlasmaViews][Panel N][Defaults] 会抽出 "Panel N" 却写到两级组去，静默删不到。
if [ -f "$HOME/.config/plasmashellrc" ]; then
    grep -oE '^\[PlasmaViews\]\[Panel [0-9]+\]$' "$HOME/.config/plasmashellrc" 2>/dev/null \
      | sed -E 's/^\[PlasmaViews\]\[(Panel [0-9]+)\]$/\1/' \
      | sort -u \
      | while IFS= read -r g; do
            kwriteconfig6 --file plasmashellrc --group PlasmaViews --group "$g" \
                --key panelOpacity --delete 2>/dev/null || true
        done
fi
# 删掉配置只管下次 KWin 启动 —— 和 tweak.py 里那条对称：
# reconfigure 不重新决定加载哪些特效，要立刻回到 KDE 默认的最小化动画
# （默认是 squash 开、magiclamp 关），必须显式 load/unload。
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.loadEffect   squash         >/dev/null 2>&1 || true
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.unloadEffect magiclamp      >/dev/null 2>&1 || true
# ★ 措辞更正：自制特效**没有**从主题移除，它当前在装（isEffectLoaded → true）★
# 这条 unloadEffect 依然是必需的：还原到默认就该把它从内存里卸掉。
# 只是理由不是「旧安装残留」，而是「本主题正在用它」。动作不要动。
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.unloadEffect frost_minimize >/dev/null 2>&1 || true
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.loadEffect   windowaperture >/dev/null 2>&1 || true
echo "    已清除 Frost 写入的 KWin 特效 / 半透明设置（回到 KDE 内置默认）"

# ★ Konsole 默认 profile 也要还原 ★ tweak.py 写的 konsolerc DefaultProfile
# 不属于任何主题包，切回 Breeze 不会动它 —— 不清的话新开的终端仍是 Frost 配色，
# 而用户以为已经回到默认了。这里只删键，让 Konsole 用它自己的内置默认；
# Frost.profile 文件本身留着（RESTORE 只回滚外观，不删文件，删除是 uninstall 的事）。
if [ "$(kreadconfig6 --file konsolerc --group "Desktop Entry" --key DefaultProfile 2>/dev/null)" = "Frost.profile" ]; then
    kwriteconfig6 --file konsolerc --group "Desktop Entry" --key DefaultProfile --delete 2>/dev/null || true
    echo "    已还原 Konsole 默认 profile（新开的终端回到 Konsole 内置默认）"
fi

echo "==> 3/3  热重载 KWin + 重启 Plasma 外壳"
# Wayland 下绝不 kwin_wayland --replace（会掉会话），用 DBus 热重载配置
qdbus6 org.kde.KWin /KWin reconfigure 2>/dev/null \
  || qdbus org.kde.KWin /KWin reconfigure 2>/dev/null \
  || busctl --user call org.kde.KWin /KWin org.kde.KWin reconfigure 2>/dev/null \
  || echo "    (KWin 热重载失败，注销重登即可)"

systemctl --user restart plasma-plasmashell.service 2>/dev/null \
  || (kquitapp6 plasmashell 2>/dev/null; sleep 1; nohup plasmashell >/dev/null 2>&1 &)

echo
# ★ 系统级登录壁纸不在本脚本的能力范围内，但必须说出来 ★
# install-login.sh 装的 /usr/share/wallpapers/FrostLogin 是 root 所有的。
# 这个脚本以普通用户跑，删不掉。不提的话，「已恢复默认」就是假话 ——
# 桌面回到了 Breeze，登录界面还是 Frost 那张图。
if [ -d /usr/share/wallpapers/FrostLogin ]; then
    echo "注意：登录界面壁纸是系统级的，本脚本无权还原。"
    echo "      去「系统设置 → 登录屏幕」把壁纸改回 Breeze（走 polkit 提权），"
    echo "      如果还要删掉文件：sudo rm -rf /usr/share/wallpapers/FrostLogin"
    echo
fi
echo "完成。若界面仍不正常，注销后重新登录即可彻底生效。"
