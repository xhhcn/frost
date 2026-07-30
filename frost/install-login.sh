#!/usr/bin/env bash
# 安装 Frost 登录界面壁纸（需要 root）
#
#   sudo bash install-login.sh
#
# 为什么单独一个脚本、还要 sudo：
#   登录界面由 plasmalogin 用户运行，配置在 /var/lib/plasmalogin（drwxr-x---，
#   root 所有），普通用户进程读不到也写不了。而且它只认系统级的
#   /usr/share/wallpapers，读不到 ~/.local/share/wallpapers。
#   所以壁纸必须装到系统目录 —— 这一步绕不开 root。
#
#   装完之后，选哪张图是在「系统设置 → 登录屏幕」里点的，
#   那一步走 polkit 提权（输一次密码），不需要再用这个脚本。
#
# 关于「随时间变化」：
#   登录壁纸做不到。它是开机时由 root 服务读的系统设置，
#   用户会话还没起来，没有任何用户级机制能在登录前改它。
#   Frost 的做法是不去追这件事：登录用一张中性暮色，
#   构图和四张时段壁纸逐像素相同，色彩落在四者之间；
#   真正抹平落差的是启动画面（splash）—— 它在登录后运行，
#   知道当前时段，负责从登录那一帧交叉淡入到桌面那一帧。
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "需要 root。请运行：sudo bash $0" >&2
    exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/out/login-wallpaper/FrostLogin"
DST="/usr/share/wallpapers/FrostLogin"

if [ ! -d "$SRC" ]; then
    echo "找不到 $SRC" >&2
    echo "先跑一次：python3 $HERE/build-theme.py" >&2
    exit 1
fi

echo "==> 安装到 $DST"
rm -rf "$DST"
mkdir -p "$DST"
cp -r "$SRC/." "$DST/"
# 登录管理器以另一个用户身份读这些文件，必须全局可读
chmod -R a+rX "$DST"
find "$DST" -type d -exec chmod 755 {} +

echo
echo "已安装:"
find "$DST" -type f -printf '  %p  (%k KB)\n' | sort

cat <<'EOF'

────────────────────────────────────────────────────────
还差最后一步（需要你在图形界面点一下，这步没法脚本化 ——
它走 polkit 提权，必须有交互）：

  系统设置 → 登录屏幕 → 壁纸 → 选「Frost · 登录」→ 应用

注意：那个页面上还有一个「同步设置」按钮，作用是把当前桌面的
设置**快照**一份给登录界面。不建议用它 —— 它会把当下那个时段的
壁纸钉死（比如中午同步就永远是 day），到了晚上登录界面还是大白天，
反而比中性图跳得更厉害。
────────────────────────────────────────────────────────
EOF
