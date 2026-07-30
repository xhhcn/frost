#!/usr/bin/env bash
# 装完新图标主题（如 Fluent）后跑这个，让 Frost 的继承链立刻接管。
# 不需要改任何配置 —— Frost 的 index.theme 已经把 Fluent 排在继承链最前，
# 装上就自动生效，没装则自动跳过。
set -uo pipefail

echo "==> 继承链现状"
CHAIN=$(grep '^Inherits=' "$HOME/.local/share/icons/Frost/index.theme" | cut -d= -f2)
IFS=',' read -ra THEMES <<< "$CHAIN"
for t in "${THEMES[@]}"; do
    printf "    %-16s " "$t"
    if [ -d "/usr/share/icons/$t" ] || [ -d "$HOME/.local/share/icons/$t" ]; then
        n=$(find "/usr/share/icons/$t" "$HOME/.local/share/icons/$t" \
             \( -name '*.svg' -o -name '*.png' \) 2>/dev/null | wc -l)
        echo "✅ $n 个图标"
    else
        echo "—  未安装（跳过）"
    fi
done

echo
echo "==> 刷新图标缓存"
for t in "${THEMES[@]}"; do
    for base in /usr/share/icons "$HOME/.local/share/icons"; do
        [ -d "$base/$t" ] && gtk-update-icon-cache -f -t "$base/$t" 2>/dev/null
    done
done
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/Frost" 2>/dev/null
rm -f "$HOME/.cache/icon-cache.kcache"
kbuildsycoca6 --noincremental >/dev/null 2>&1

echo "==> 重启 Plasma 外壳"
systemctl --user restart plasma-plasmashell.service 2>/dev/null \
  || (kquitapp6 plasmashell 2>/dev/null; sleep 1; nohup plasmashell >/dev/null 2>&1 &)

echo
echo "完成。已打开的应用需要重启才会用新图标。"
