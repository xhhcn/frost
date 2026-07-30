#!/usr/bin/env bash
# 安装 Lightly (Bali10050 fork, Qt6) 到 ~/.local —— 控件风格 + 窗口装饰
# 注意：boehs/Lightly 已弃坑且是 Qt5，编译不过；这里用的是活跃的 Qt6 分支。
set -euo pipefail
# ★ 按脚本自身位置推导，不写死作者的家目录 ★
# 原来是 SRC=/home/hui/Documents/theme/ref-lightly6 —— 换用户/换机器跑，
# 第一行就报「!! 未构建，先跑 cmake --build」，而真正的原因是那个路径
# 根本不属于这台机器。更糟的是它在**作者自己机器上也已经失效**：
# ref-lightly6 目录不存在（theme/ 下只有 _BACKUP_* / frost / ref-arch /
# RESTORE.sh / 几个 .sh）。也就是说这个脚本长期处于「跑不起来」状态，
# 而它是全套里唯一能装 Darkly 的东西 —— 而 Darkly 是主题 defaults 里
# 无条件声明的依赖，任何官方源都没有。
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${FROST_LIGHTLY_SRC:-$ROOT/ref-lightly6}"

[ -d "$SRC/build" ] || { echo "!! 未构建，先跑 cmake --build"; exit 1; }

echo "==> 安装到 \$HOME/.local"
cmake --install "$SRC/build" --prefix "$HOME/.local"

if [ -f "$SRC/build/install_manifest.txt" ]; then
    # 清单给 uninstall-frost.sh 用，位置必须和它推导的一致（都是 theme/ 下）
    cp "$SRC/build/install_manifest.txt" "$ROOT/lightly_installed.txt"
    echo "    清单已存: lightly_installed.txt ($(wc -l < "$ROOT/lightly_installed.txt") 个文件)"
fi

# 和 Vinyl 一样，用户级安装的 Qt 插件需要 QT_PLUGIN_PATH 才能被找到
mkdir -p "$HOME/.config/environment.d"
cat > "$HOME/.config/environment.d/90-local-qt-plugins.conf" <<'EOF'
# 让 Qt/KWin 找到装在 ~/.local 的插件（控件风格、窗口装饰）
QT_PLUGIN_PATH=${HOME}/.local/lib/plugins:${QT_PLUGIN_PATH}
EOF
systemctl --user set-environment QT_PLUGIN_PATH="$HOME/.local/lib/plugins:${QT_PLUGIN_PATH:-}"

kbuildsycoca6 --noincremental >/dev/null 2>&1 || true

echo
echo "已安装的插件:"
find "$HOME/.local/lib/plugins" -name "*ightly*" -o -name "*arkly*" 2>/dev/null | sed 's|^|  |'
echo
echo "启用:  bash $ROOT/frost/apply-frost.sh --lightly"
echo "还原:  bash $ROOT/frost/restore-default.sh"
