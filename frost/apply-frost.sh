#!/usr/bin/env bash
# 应用 Frost 主题
#   bash apply-frost.sh            只换外观，保留现有面板
#   bash apply-frost.sh --layout   同时套用「顶栏 + 底部 Dock」（会重排面板）
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LNF="com.xhhcn.frost"
WITH_LAYOUT="${1:-}"

# 套布局前再存一份面板配置，方便单独回滚面板
if [ "$WITH_LAYOUT" = "--layout" ]; then
    # ★ --layout 会用主题里那 4 条固定启动器**整串覆盖** launchers ★
    # 用户自己「固定到任务栏」的 app（模型经 onLauncherListChanged 回写进
    # launchers 键）会被抹掉，而且 tweak.py 救不回来 —— 它只在发现
    # preferred:// 时才写 launchers，没有 preferred:// 时完全不碰。
    # 下面那个快照是唯一退路，所以先把当前值打出来让人看见。
    CUR=$(kreadconfig6 --file plasma-org.kde.plasma.desktop-appletsrc \
          --group Containments --group 502 --group Applets --group 504 \
          --group Configuration --group General --key launchers 2>/dev/null)
    if [ -n "$CUR" ]; then
        echo "==> 注意：--layout 会把底栏固定图标重置为主题默认的 4 个"
        echo "    当前固定：$CUR"
    fi
    SNAP="$HERE/../_panel_before_frost.tar.gz"
    # ★ 只在快照不存在时创建 ★
    # 无条件覆盖的话，第二次跑 --layout 就把「Frost 之前」的快照
    # 替换成了「Frost 之后」的 —— 回滚点被自己毁掉，而且毫无提示。
    if [ -e "$SNAP" ]; then
        echo "==> 面板快照已存在，保留原有回滚点: $SNAP"
    else
        # ★ 必须检查 tar 的结果 ★
        # 早先是 `tar ... 2>/dev/null` 且不看退出码：源文件缺失或磁盘满时
        # 会留下一个空的/残缺的归档，而上面那个「已存在就跳过」的守卫
        # 会把它**永久固化成回滚点** —— 用户以为有退路，实际没有。
        if tar czf "$SNAP" -C "$HOME" \
               .config/plasma-org.kde.plasma.desktop-appletsrc \
               .config/plasmashellrc 2>/dev/null \
           && tar tzf "$SNAP" >/dev/null 2>&1 \
           && [ "$(tar tzf "$SNAP" 2>/dev/null | wc -l)" -ge 2 ]; then
            echo "==> 面板配置已单独快照: $SNAP"
        else
            rm -f "$SNAP"      # 宁可没有，也不要一个假的回滚点
            echo "!! 面板快照创建失败，已删除残留。" >&2
            echo "   继续会失去面板布局的回滚能力。" >&2
            printf "   仍要继续吗？[y/N] " >&2
            read -r ans; [ "$ans" = "y" ] || exit 1
        fi
    fi
fi

echo "==> 应用全局主题: $LNF"
if [ "$WITH_LAYOUT" = "--layout" ]; then
    plasma-apply-lookandfeel -a "$LNF" --resetLayout || { echo "!! 失败"; exit 1; }
else
    plasma-apply-lookandfeel -a "$LNF" || { echo "!! 失败"; exit 1; }
fi

restart_shell() {
    systemctl --user restart plasma-plasmashell.service 2>/dev/null \
      || (kquitapp6 plasmashell 2>/dev/null; sleep 1; nohup plasmashell >/dev/null 2>&1 &)
}

# 必须先重启 plasmashell，让它把新面板布局写盘，tweak.py 才读得到面板 id
echo "==> 重启 Plasma 外壳（写盘新布局）"
restart_shell
for _ in $(seq 20); do
    grep -q "location=4" "$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc" 2>/dev/null && break
    sleep 1
done

# plasmashell 运行时会用内存状态覆写 plasmashellrc，必须先停再写
echo "==> 停止 Plasma 外壳（避免配置被覆写）"
systemctl --user stop plasma-plasmashell.service 2>/dev/null || kquitapp6 plasmashell 2>/dev/null
sleep 2

echo "==> 补写 look-and-feel 不支持的设置（contrast / 模糊 / Dock 宽度）"
python3 "$HERE/tweak.py"

echo "==> 热重载 KWin（Wayland 下不重启合成器）"
qdbus6 org.kde.KWin /KWin reconfigure 2>/dev/null \
  || busctl --user call org.kde.KWin /KWin org.kde.KWin reconfigure 2>/dev/null \
  || echo "    (热重载失败，注销重登即可)"

echo "==> 启动 Plasma 外壳"
restart_shell

# 壁纸交给 daylight.py 按太阳高度角选时段 ——
# 写死一张会和动态切换打架（apply 设成 dusk，daylight 以为状态没变就跳过）。
# ★ 启用按时段切换 ★
# 早先只有**打包版**的 install.sh 会跑 --install，本地
# install-frost.sh + apply-frost.sh 这条路从来不装定时器和登录钩子 ——
# 结果是「主题装上了、壁纸也对，但一整天再也不会跟着时间变」。
# 作者机器上看不出来，因为当初手动跑过一次 --install。
# 幂等：重复跑只是重写单元文件并 restart，没有副作用。
echo "==> 启用按时段切换（systemd 定时器 + 登录前钩子）"
python3 "$HERE/daylight.py" --install || echo "    !! 定时器安装失败，壁纸不会自动跟时段变"

echo "==> 设置壁纸（按当前时段）"
for _ in $(seq 20); do
    busctl --user status org.kde.plasmashell >/dev/null 2>&1 && break
    sleep 1
done
rm -f "$HOME/.cache/frost-daylight-state"     # 强制重新判定
python3 "$HERE/daylight.py" || echo "    手动：桌面右键 → 配置桌面 → 壁纸 选 Frost · dusk"

echo
echo "完成。出问题: bash $HERE/restore-default.sh"
