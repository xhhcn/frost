#!/usr/bin/env bash
# Frost 状态自检 —— 只读，不改任何东西。随时可跑。
echo "── 主题 ──"
printf '  %-22s %s\n' "全局主题"   "$(kreadconfig6 --file kdeglobals --group KDE --key LookAndFeelPackage)"
printf '  %-22s %s\n' "配色"       "$(kreadconfig6 --file kdeglobals --group General --key ColorScheme)"
printf '  %-22s %s\n' "Plasma 样式" "$(kreadconfig6 --file plasmarc --group Theme --key name)"
printf '  %-22s %s\n' "图标"       "$(kreadconfig6 --file kdeglobals --group Icons --key Theme)"
printf '  %-22s %s\n' "控件风格"   "$(kreadconfig6 --file kdeglobals --group KDE --key widgetStyle)"
printf '  %-22s %s\n' "窗口装饰"   "$(kreadconfig6 --file kwinrc --group org.kde.kdecoration2 --key theme)"
echo "── 面板 ──"
qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript '
var p=panels(); for (var i=0;i<p.length;i++) print("  "+p[i].location+" 厚度="+p[i].height);' 2>/dev/null \
  || echo "  (plasmashell 没响应)"
printf '  %-22s %s 处\n' "panelOpacity=2" "$(grep -c '^panelOpacity=2' ~/.config/plasmashellrc 2>/dev/null)"
echo "── KWin 特效 ──"
for e in frost_minimize squash magiclamp blur; do
  printf '  %-22s %s\n' "$e" "$(qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.isEffectLoaded $e 2>/dev/null)"
done
printf '  %-22s %s\n' "BlurStrength" "$(kreadconfig6 --file kwinrc --group Effect-blur --key BlurStrength)"
echo "── 任务栏 ──"
A=~/.config/plasma-org.kde.plasma.desktop-appletsrc
printf '  %-22s %s\n' "固定启动器" "$(grep -m1 '^launchers=' $A | tr ',' '\n' | wc -l) 个"
printf '  %-22s %s\n' "separateLaunchers" "$(grep -m1 '^separateLaunchers=' $A || echo '(未设)')"
echo "── 时段切换 ──"
printf '  %-22s %s / %s\n' "定时器" "$(systemctl --user is-active frost-daylight.timer)" "$(systemctl --user is-enabled frost-daylight.timer 2>/dev/null)"
printf '  %-22s %s\n' "unit 指向" "$(grep -h ExecStart ~/.config/systemd/user/frost-daylight.service 2>/dev/null | cut -d' ' -f2-)"
printf '  %-22s %s\n' "登录钩子" "$([ -f ~/.config/plasma-workspace/env/frost-daylight.sh ] && echo 已装 || echo 缺失)"
printf '  %-22s %s\n' "当前时段" "$(python3 ~/.local/share/frost/daylight.py --which 2>/dev/null || python3 ~/Documents/theme/frost/daylight.py --which 2>/dev/null)"
echo "── Konsole ──"
printf '  %-22s %s\n' "默认 profile" "$(kreadconfig6 --file konsolerc --group 'Desktop Entry' --key DefaultProfile)"
printf '  %-22s %s\n' "资产" "$(ls ~/.local/share/konsole/ 2>/dev/null | tr '\n' ' ')"
echo "── 资产完整性 ──"
for d in plasma/desktoptheme/Frost plasma/look-and-feel/com.xhhcn.frost icons/Frost kwin/effects/frost_minimize; do
  printf '  %-38s %s 个文件\n' "$d" "$(find ~/.local/share/$d -type f 2>/dev/null | wc -l)"
done
printf '  %-38s %s 套\n' "color-schemes/Frost*" "$(ls ~/.local/share/color-schemes/Frost*.colors 2>/dev/null | wc -l)"
printf '  %-38s %s 个\n' "wallpapers/FrostScene-*" "$(ls -d ~/.local/share/wallpapers/FrostScene-* 2>/dev/null | wc -l)"
