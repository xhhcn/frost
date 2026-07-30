#!/usr/bin/env bash
# 把 Frost 打成一个可移植的归档
#
#   bash package-frost.sh
#   → frost-<版本>.tar.gz
#
# 为什么不是一个「全局主题包」就够：
#   KDE 的全局主题（look-and-feel）本身只是一张**清单** —— 它写的是
#   「用 Frost 这个 Plasma 样式、Frost-dusk 这套配色、Frost 这套图标」，
#   但不包含它们。系统设置里的「安装主题文件」只认单个 KPackage，
#   装进去之后那些被引用的资源仍然是缺的，结果是一套引用了不存在资源的主题。
#   所以这里打包的是**全部六类资产 + 一个安装脚本**。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$HERE/out"
VER="$(python3 -c "import json;print(json.load(open('$OUT/look-and-feel/com.xhhcn.frost/metadata.json'))['KPlugin']['Version'])" 2>/dev/null || echo 1.0)"
STAGE="$(mktemp -d)"
PKG="$HERE/frost-${VER}.tar.gz"
trap 'rm -rf "$STAGE"' EXIT

# ★ 打包前必须先构建 ★
# 曾经发生过：归档 23:00 打的，KWin 特效目录 00:49 才生成 —— 包里根本没有
# 主题唯一的代码资产，别人装上得到的最小化动画会回落到 stock squash。
# 那不是手滑，是流程里没有这道强制。build-theme.py 内含对比度门禁，
# 不达标会以非零码退出，等于打包前自动做了一次可访问性体检。
echo "==> 先重新构建（含对比度门禁）"
python3 "$HERE/build-theme.py" >/dev/null || {
    echo "!! 构建失败（很可能是对比度门禁未通过），不打包" >&2; exit 1; }

[ -d "$OUT" ] || { echo "构建后仍找不到 $OUT" >&2; exit 1; }

R="$STAGE/frost-$VER"
mkdir -p "$R/share"

echo "==> 收集资产"
# ★ 从**已安装的树**打包，不从 out/ ★
# 两个原因：
#   1) out/ 是扁平的（desktoptheme/ look-and-feel/ 都在顶层），
#      而安装目标要嵌在 plasma/ 下面 —— 从 out/ 打包就得把 install-frost.sh
#      的映射再抄一遍，抄错了很难发现（第一版就漏了两类资产）。
#   2) 有些东西是**安装时**才生成的，out/ 里没有 ——
#      比如 Arch 徽标（从 /usr/share/pixmaps 提取路径后转成单色）。
#      从已安装的树打包，装出来的就是此刻验证过能用的那一份。
SRC="${XDG_DATA_HOME:-$HOME/.local/share}"
[ -d "$SRC/plasma/desktoptheme/Frost" ] || {
    echo "!! 还没安装。先跑：bash $HERE/install-frost.sh" >&2; exit 1; }

# ★ 陈旧守卫：源码比已安装树新，就是在打包过期的字节 ★
# 上面刚跑过 build-theme.py（含三道门禁），但门禁校验的是**源码和 out/**，
# 而下面 cp 的是**已安装树** —— 两者是不同的东西。改了生成器却忘了
# install-frost.sh，门禁照样全过，包里却是上一版的资产，而且完全无声。
# （这不是假设：本轮就发生过 —— 改完 build-theme.py 只手动 cp 了特效的
#   main.js，其余资产仍是旧的。）
#
# 不能用「out/ 必须逐字节等于已安装树」做判据：daylight.py 按时段重写
# 已安装的文件夹图标（强调色），实测 16 个共有图标里 13 个不同 ——
# 去掉颜色值后结构完全一致，差异纯粹是 out/ 停在构建那一刻的时段
# （#f5b942 dusk）而系统里是当前时段（#68cbdf day）。那是设计使然。
# 所以判据是**时间**而不是内容：任何生成器比安装树最新的文件还新，就拒绝。
#
# ★ 必须排除 daylight.py 在运行时重写的文件，否则这道守卫是空操作 ★
# contents/splash/{Splash.qml,images/scene.svg} 由 sync_splash() /
# _sync_splash_accent() 在**每次切时段和每次登录预置**时重写（每天至少 4 次），
# 它们的 mtime 反映的是「最近一次时段同步」，不是「最近一次安装」。
# 留在集合里，newest_installed 就被推到当前时刻，任何早于它的源码修改
# 都不再算「更新」—— 守卫静默失效，而三道构建门禁全绿、退出码 0。
# 实测（本机，安装于 17:12:55，daylight 写 splash 于 18:20:25）：
#   把 build-theme.py 的 mtime 设到 17:30 → 不报警，一路打包过期资产；
#   设到 18:20 之后 → 才报警。同一棵树，判据被时间戳污染。
# 判定「哪些是运行时重写的」不靠猜：diff -rq 已安装树 out/ ——
# 差异恰好只有这两个文件（其余逐字节相同），所以排除范围就是 splash/。
# 文件夹图标（icons/Frost）也被 daylight 重写，但它本来就不在扫描集里。
newest_installed=$(find "$SRC/plasma/desktoptheme/Frost" "$SRC/plasma/look-and-feel/com.xhhcn.frost" \
                        -type f -not -path '*/contents/splash/*' \
                        -printf '%T@\n' 2>/dev/null | sort -n | tail -1)
stale=""
for g in build-theme.py wallpaper.py install-frost.sh; do
    [ -f "$HERE/$g" ] || continue
    gt=$(stat -c %Y "$HERE/$g")
    awk -v a="$gt" -v b="${newest_installed:-0}" 'BEGIN{exit !(a>b)}' && stale="$stale $g"
done
if [ -n "$stale" ]; then
    echo "!! 已安装树比源码旧 —— 会打包过期资产。较新的生成器：$stale" >&2
    echo "   先重新安装再打包：bash $HERE/install-frost.sh" >&2
    exit 1
fi

mkdir -p "$R/share/plasma/desktoptheme" "$R/share/plasma/look-and-feel" \
         "$R/share/plasma/layout-templates" "$R/share/icons" \
         "$R/share/color-schemes" "$R/share/wallpapers"
cp -r "$SRC/plasma/desktoptheme/Frost"              "$R/share/plasma/desktoptheme/"
cp -r "$SRC/plasma/look-and-feel/com.xhhcn.frost"     "$R/share/plasma/look-and-feel/"
cp -r "$SRC/plasma/layout-templates/com.xhhcn.frost."* "$R/share/plasma/layout-templates/"
cp -r "$SRC/icons/Frost"                            "$R/share/icons/"
cp    "$SRC/color-schemes/Frost"*.colors            "$R/share/color-schemes/"
cp -r "$SRC/wallpapers/FrostScene-"*                "$R/share/wallpapers/"
mkdir -p "$R/share/konsole"
cp    "$SRC/konsole/Frost.colorscheme"              "$R/share/konsole/" 2>/dev/null || true
# profile 必须一起进包：光有配色的话用户得手工去「设置 → 外观」里选，
# 有了 profile + konsolerc 的 DefaultProfile 才是自动生效。
cp    "$SRC/konsole/Frost.profile"                  "$R/share/konsole/" 2>/dev/null || true
# KWin 最小化动画（= squash + 提层）。装在 share/kwin/effects/ 下。
mkdir -p "$R/share/kwin/effects"
cp -r "$SRC/kwin/effects/frost_minimize"            "$R/share/kwin/effects/" 2>/dev/null || true

# 登录壁纸是系统级的（装到 /usr/share/wallpapers 要 root），
# 单独放一层，不混进用户级资产里，免得 install.sh 一股脑复制过去。
[ -d "$OUT/login-wallpaper" ] && cp -r "$OUT/login-wallpaper" "$R/"

# 时段切换的运行时脚本（daylight.py 是唯一的运行时组件；
# tweak.py 供「系统设置切换后补齐外观」用）
mkdir -p "$R/bin"
cp "$HERE/daylight.py" "$HERE/tweak.py" "$R/bin/"
# ★ 包内 README 前面必须钉一段发布版说明 ★
# 直接拷开发侧 README 的后果（实测）：它开头那张「工程结构」表列的是
# build-theme.py / install-frost.sh / apply-frost.sh / uninstall-frost.sh，
# 四个**都不在包里**（tar 条目逐个比对过；对照：install.sh / uninstall.sh 在，
# 证明这个比对逻辑有效）。而第 62 行还写着
#   python3 build-theme.py && bash install-frost.sh && bash apply-frost.sh
# 拿到包的人照着敲，四条全是 No such file or directory ——
# 而真正的入口 install.sh 在这份 README 里第一次出现是**第 1085 行**。
# 第一印象是「这个包坏的」。
# ★ 包里放的是一份自包含的英文 README，**不再拼上开发日志** ★
# 早先是「短头部 + cat frost/README.md」，产出 190KB —— 其中 189KB 是
# 那份 2635 行的工程日志。它对拿到包的人有害无益：里面反复出现的
# build-theme.py / install-frost.sh / apply-frost.sh 只存在于源码仓库，
# 照着敲全是 No such file or directory，而真正的入口 install.sh
# 在那份文档里第一次出现已经是第 1085 行 —— 第一印象是「这个包坏的」。
# 开发日志留在源码仓库本地即可（.gitignore 也把它排除了）。
cat > "$R/README.md" <<'EOR'
# Frost 1.0

A hand-written frosted-glass theme for KDE Plasma 6.
Built for Arch Linux + Plasma 6.7 + Wayland.

Source and issues: https://github.com/xhhcn/frost

## Install

```bash
bash install.sh      # pure data, no compilation, no root
```

Then: **System Settings → Appearance → Global Theme → Frost → Apply**,
and **log out and back in once**.

The log-out matters: `plasma-apply-lookandfeel` only applies a whitelist of
settings. A login hook fills in the rest (panel opacity, blur, taskbar keys).

## Uninstall

```bash
bash uninstall.sh
```

Restores the previous look and removes every file this package installed.

## What's in here

| Path | |
|---|---|
| `install.sh` / `uninstall.sh` | the only two commands you need |
| `bin/daylight.py` | switches wallpaper and colours by solar elevation |
| `bin/tweak.py` | applies the settings the global theme can't carry |
| `share/` | all assets: Plasma style, colour schemes, wallpapers, icons, splash, KWin effect, Konsole |

## Time of day

The accent colour follows the **solar elevation angle** at your location,
derived from your timezone — nothing is stored or sent anywhere.

| | Accent |
|---|---|
| dawn | peach |
| day | cyan |
| dusk | gold |
| night | indigo |

Wallpaper, colour scheme, splash screen and lock screen all move together.
A systemd **user timer** checks every 20 minutes; there is no resident process.

## Optional components

Not included here. Without them the theme still installs and works — it just
degrades in the ways listed. `install.sh` warns about anything missing.

| Component | Where | Without it |
|---|---|---|
| `fluent-icon-theme` | AUR | Icons fall back to Breeze; two menu-category icons don't exist there and render blank |
| `papirus-icon-theme` | extra | Loses one inheritance fallback |
| Darkly | build `Bali10050/Lightly` into `~/.local` (not in any official repo) | Widget style and window decorations fall back to Breeze: no rounded corners, shadows or translucent menus. Panel glass, colours and time-of-day switching are unaffected |

## Licence

Code and Plasma packages are **GPL-2.0-or-later**; the wallpapers are
**CC0-1.0**. Full texts are in `LICENSES/`, and `LICENSE` explains which
component falls under which.

`share/kwin/effects/frost_minimize` is **not** self-authored: it is a
derivative of KWin's own `squash` effect (© Vlad Zahorodnii,
GPL-2.0-or-later) with window elevation added. This is stated in `LICENSE`
and in the file's own header.
EOR

# ★ 许可全文必须进包 ★
# 九个子包的 metadata.json 各自声明了 License（实测 GPL-2.0-or-later x4、
# CC0-1.0 x5；frost_minimize 已从 MIT 改成 GPL，全树再无 MIT 子包），
# 但发布包里一份全文都没有 —— 声明了 GPL 却不附
# 全文是不合规的，而且拿到包的人无从查证条款。
# 这里不是「可有可无的补充」，缺了就不该发布，所以下面用硬失败而不是
# `|| true`：早先包里很多 cp 都带 `|| true`，于是缺文件是静默的。
if [ ! -f "$HERE/licenses/LICENSE" ]; then
    echo "!! 找不到 $HERE/licenses/LICENSE —— 许可文件缺失，拒绝打包" >&2
    exit 1
fi
cp "$HERE/licenses/LICENSE" "$R/LICENSE"
mkdir -p "$R/LICENSES"
# ★ 从**实际声明**推导要带哪几份全文，不写死列表 ★
# 早先这里硬编码 `GPL-2.0-or-later MIT CC0-1.0`。后来 frost_minimize 的许可
# 从 MIT 改成 GPL-2.0-or-later（它是 squash 的衍生作品，见 licenses/LICENSE），
# 全树再没有子包声明 MIT —— 而硬编码的列表还在要求 MIT.txt，
# 于是包里会带一份**没有任何东西引用**的许可全文。
# 硬编码列表必然随声明漂移；从 metadata 反查就不会。
declared=$(grep -rho '"License": *"[^"]*"' "$R/share" "$R/login-wallpaper" 2>/dev/null \
           | sed 's/.*: *"//;s/"//' | sort -u)
[ -n "$declared" ] || { echo "!! 产物里一个 License 声明都没有，异常，拒绝打包" >&2; exit 1; }
# ★ 逐行读，不要靠 shell 词分割 ★
# License 允许是 SPDX 表达式（"GPL-2.0-or-later OR MIT"）。`for l in $declared`
# 会把它拆成 GPL-2.0-or-later / OR / MIT 三个词，然后去找 licenses/OR.txt，
# 打包以「licenses/OR.txt 缺失」硬失败 —— 一个无从下手的错误信息。
# 当前九个子包都是单一许可名，所以还没触发；这是防将来。
# 用 <<< 而不是管道：while 必须跑在当前 shell 里，否则里面的 exit 1 只退子壳。
while IFS= read -r l; do
    [ -n "$l" ] || continue
    if [ ! -s "$HERE/licenses/$l.txt" ]; then
        echo "!! 有子包声明 License=$l，但 licenses/$l.txt 缺失或为空 —— 拒绝打包" >&2
        exit 1
    fi
    cp "$HERE/licenses/$l.txt" "$R/LICENSES/"
done <<< "$declared"

cat > "$R/install.sh" <<'EOS'
#!/usr/bin/env bash
# 安装 Frost。纯数据，无编译，不需要 root。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}"

# ★ 外部依赖必须自己检查 —— 包里没有任何依赖声明机制 ★
# 现状实测：138 个 tar 条目里没有 PKGBUILD/DEPENDS/requirements；
# 50 行 install.sh 里 `command -v` 出现 0 次。
# 缺 python3 时的实际表现：资产已经拷完 70 个文件，到 daylight.py --install
# 那行才以 127 退出，屏幕上只有一行 "python3: command not found"，
# 连末尾「装好了 / 接下来做什么」都不打印 —— 用户既不知道成功没有，也不知道要不要卸。
#
# ★ 位置必须在 cp 之前 ★ 第一版把这段放在「安装运行时脚本」前面，
# 实测仍落盘 68 个文件才拦住 —— 检查缺失命令却先拷 68 个文件毫无意义。
# 现在它在「复制资产」之前，缺命令时落盘数为 0。
# 顺带记一次测量陷阱：验证时如果 PATH 里留着 /usr/bin，
# 被"抽掉"的命令会从那儿被找到，预检不触发而你以为它坏了 ——
# 要用只含桩 + coreutils 符号链接的 PATH，并且拿一个**仍存在**的命令做对照
# （我用 plasma-apply-colorscheme），证明 PATH 不是空的。
missing=""
for c in python3 kwriteconfig6 kreadconfig6 plasma-apply-colorscheme \
         plasma-apply-wallpaperimage plasma-apply-lookandfeel; do
    command -v "$c" >/dev/null 2>&1 || missing="$missing $c"
done
if [ -n "$missing" ]; then
    echo "!! 缺少必需命令：$missing" >&2
    echo "   python3 来自 python；其余来自 plasma-workspace / kconfig。" >&2
    exit 1
fi
# 下面两项缺了会明显退化但装得上，所以只警告不退出。
if [ ! -d /usr/share/icons/Fluent-dark ] && [ ! -d "$DEST/icons/Fluent-dark" ]; then
    cat >&2 <<'EOW'
!! 未找到 Fluent 图标主题（AUR: fluent-icon-theme，官方源没有）。
   icons/Frost/index.theme 的 Inherits 第一项就是它。Frost 自己只带
   14 个 places 图标 + 4 个 Arch 徽标 + 1 个托盘图标，其余全靠继承链；
   缺了会整体落到 breeze —— 能用，但和截图不是一套图标语言。
   另有两个菜单分类图标名在 breeze 里根本不存在（会是空白）：
     accessories-text-editor-symbolic   office-calendar-symbolic
EOW
fi
if [ ! -f "$HOME/.local/lib/plugins/styles/darkly6.so" ]; then
    cat >&2 <<'EOW'
!! 未找到 Darkly 控件风格（~/.local/lib/plugins/styles/darkly6.so）。
   本包既不含它、也不含它的安装脚本，**任何官方源里都没有**
   （pacman -Ss '^darkly' 无输出）—— 要自己编译 Bali10050/Lightly 到 ~/.local。
   全局主题的 defaults 无条件写 widgetStyle=Darkly 和 library=org.kde.darkly，
   缺了这两项会退回 Breeze：圆角、阴影、菜单半透明都没有。
   面板毛玻璃 / 配色 / 壁纸按时段切换不受影响。
EOW
fi

echo "==> 复制资产到 $DEST"
mkdir -p "$DEST"
cp -r "$HERE/share/." "$DEST/"

echo "==> 安装运行时脚本"
# ★ 必须和 DEST 用同一个解析 ★ 上面 DEST="${XDG_DATA_HOME:-$HOME/.local/share}"，
# 而 uninstall.sh 删的是 "$DEST/frost"。这里写死 $HOME 的话，XDG_DATA_HOME
# 一被设置就成了「装在 A、卸 B」：daylight.py、tweak.py 和它们的 systemd
# unit 永久残留，而卸载脚本退出码 0、还打印「已卸载」。
BIN="$DEST/frost"
mkdir -p "$BIN"
cp "$HERE/bin/daylight.py" "$HERE/bin/tweak.py" "$BIN/"
chmod +x "$BIN/daylight.py"

echo "==> 清缓存（不清的话新 SVG 不会生效）"
rm -f  "$HOME/.cache/plasma_theme_"*.kcache "$HOME/.cache/icon-cache.kcache"
rm -rf "$HOME/.cache/ksvg-elements"
kbuildsycoca6 --noincremental >/dev/null 2>&1 || true

echo "==> 启用按时段切换（systemd user timer + 启动前钩子）"
python3 "$BIN/daylight.py" --install

cat <<'EOT'

装好了。接下来：

  系统设置 → 外观 → 全局主题 → 选「Frost」→ 应用

然后**注销重登一次**。

为什么要重登：plasma-apply-lookandfeel 只应用一份白名单里的配置键，
毛玻璃真正依赖的那些（面板半透明、KWin 模糊、Darkly 控件风格）都不在里面。
启动前钩子会在下次登录时自动补齐 —— 它跑在 plasmashell 之前，
那正是写 plasmashellrc 唯一不会被覆写的时机。

不想重登也可以立刻补：
  python3 ~/.local/share/frost/tweak.py --appearance-only

登录界面壁纸是系统级设置（root 所有），要的话单独装：
  sudo cp -r login-wallpaper/FrostLogin /usr/share/wallpapers/
  再到 系统设置 → 登录屏幕 里选「Frost · 登录」

卸载：bash uninstall.sh

  （早先这里写的是「删掉 $HOME/.local/share 下所有 Frost*」——那是错的：
    资产全嵌在 plasma/ icons/ color-schemes/ wallpapers/ konsole/ kwin/ 下，
    顶层那个 glob 一个都匹配不到，照字面执行什么也删不掉。）
EOT
EOS
chmod +x "$R/install.sh"

# ─────────────────────────────────────────────────────────────────────
# 卸载脚本。以前包里根本没有 —— install.sh 末尾那两行文字说明按字面执行
# 什么也删不掉，等于「装得上、卸不掉」，这是不能发布的组合。
# ─────────────────────────────────────────────────────────────────────
cat > "$R/uninstall.sh" <<'EOU'
#!/usr/bin/env bash
# 卸载 Frost，回到 KDE 默认外观。不需要 root。
set -uo pipefail
DEST="${XDG_DATA_HOME:-$HOME/.local/share}"

echo "==> 1/5  切回 Breeze 全局主题"
# ★ 必须先切主题，不能只删文件 ★
# kdeglobals 里已经烘焙了完整的 [Colors:*] 十套色块。只删文件的话，
# 桌面会保持 Frost 的配色，而 ColorScheme= 指向一个不存在的方案。
plasma-apply-lookandfeel -a org.kde.breezedark.desktop 2>/dev/null \
  || plasma-apply-lookandfeel -a org.kde.breeze.desktop 2>/dev/null || true
plasma-apply-desktoptheme default    2>/dev/null || true
plasma-apply-colorscheme  BreezeDark 2>/dev/null || true

echo "==> 2/5  停用按时段切换"
# 不停掉的话：定时器每 20 分钟把 Frost 的配色和壁纸重新写回来，
# 卸载脚本跑完看着是好的，二十分钟后又变回去。
systemctl --user disable --now frost-daylight.timer 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/frost-daylight.timer" \
      "$HOME/.config/systemd/user/frost-daylight.service" \
      "$HOME/.config/plasma-workspace/env/frost-daylight.sh" \
      "$HOME/.cache/frost-daylight-state" \
      "$HOME/.cache/frost-daylight-unapplied"
systemctl --user daemon-reload 2>/dev/null || true

echo "==> 3/5  还原 KWin 特效与外观键"
# 写配置只管下次 KWin 启动；要立刻回到默认的最小化动画必须显式 load/unload。
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.unloadEffect frost_minimize >/dev/null 2>&1 || true
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.loadEffect   squash          >/dev/null 2>&1 || true
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.loadEffect   windowaperture  >/dev/null 2>&1 || true
for k in frost_minimizeEnabled squashEnabled magiclampEnabled windowapertureEnabled blurEnabled; do
    kwriteconfig6 --file kwinrc --group Plugins --key "$k" --delete 2>/dev/null || true
done
for k in BlurStrength NoiseStrength; do
    kwriteconfig6 --file kwinrc --group Effect-blur --key "$k" --delete 2>/dev/null || true
done
kwriteconfig6 --file kdeglobals --group KDE --key contrast      --delete 2>/dev/null || true
kwriteconfig6 --file kdeglobals --group KDE --key frameContrast --delete 2>/dev/null || true
# ★ ksplashrc 用 --delete，不要写 breeze ★
# 本机实测 ~/.config/ksplashrc 是 0 字节、从未被写过 —— kreadconfig6 返回
# com.xhhcn.frost 是 look-and-feel 的 defaults 级联在供值，删掉 LnF 包就自然消失。
# 在目标机上凭空写一个 Theme= 反而会覆盖用户自己选过的启动画面。
kwriteconfig6 --file ksplashrc --group KSplash --key Theme --delete 2>/dev/null || true
# 锁屏壁纸指向即将被删的目录，必须清掉
kwriteconfig6 --file kscreenlockerrc --group Greeter --group Wallpaper \
    --group org.kde.image --group General --key Image --delete 2>/dev/null || true
# ★ WallpaperPlugin 也是 daylight.py 写的，一起删 ★
# set_lockscreen() 无条件写 [Greeter] WallpaperPlugin=org.kde.image。
# 只删 Image 的话实测残留：假 HOME 上走完 install→uninstall 往返，
# kscreenlockerrc 里还剩这一个键 —— 用户原来若用的是 org.kde.slideshow
# 之类，被静默改掉且永不还原（幻灯片没了，还不知道是谁干的）。
kwriteconfig6 --file kscreenlockerrc --group Greeter \
    --key WallpaperPlugin --delete 2>/dev/null || true
# ★ 桌面壁纸：和上面锁屏**同一个失败模式**，早先只修了锁屏那一半 ★
# 下面 rm -rf 掉 wallpapers/FrostScene-* 之后，daylight.py 往**每个**桌面容器
# 写过的 Image=file://…/FrostScene-x 就指向了不存在的目录 ——
# 桌面背景变成纯色/兜底图，用户刚卸完主题就发现壁纸坏了，没有任何线索。
# 必须遍历所有容器：外接显示器各有自己的容器，id 由 plasmashell 分配，写不死。
# 只删指向 FrostScene 的那些（指向别处的容器不会被选中，已对照验证）。
# 局限：没记录用户原来的壁纸，只能删键让 Plasma 用默认值，无法还原原图。
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
    done
fi
# ★ plasmashellrc 的面板外观键不属于任何主题包 ★
# tweak.py --appearance-only（登录钩子每次登录都跑）写 panelOpacity=2。
# breeze 的 look-and-feel defaults 里没有 PlasmaViews 段，所以切回 Breeze
# 不会还原它 —— 卸载后面板继续被强制半透明，而 blurEnabled 已经删了，
# 于是变成「半透明但不模糊」，比 Breeze 默认还难看，用户不知道去哪改。
if [ -f "$HOME/.config/plasmashellrc" ]; then
    grep -oE '^\[PlasmaViews\]\[Panel [0-9]+\]' "$HOME/.config/plasmashellrc" 2>/dev/null \
      | sed -E 's/^\[PlasmaViews\]\[(Panel [0-9]+)\]$/\1/' \
      | while IFS= read -r g; do
            kwriteconfig6 --file plasmashellrc --group PlasmaViews --group "$g" \
                --key panelOpacity --delete 2>/dev/null || true
        done
fi
# darklyrc 是 tweak.py 建的（26 个键）。Darkly 本体由用户自己编译安装、
# 不在本包管辖范围，但**这个配置文件是我们写的**，卸载就该带走。
rm -f "$HOME/.config/darklyrc"

echo "==> 4/5  删除资产"
# 写全路径。**不要**用 $DEST/Frost* 这种顶层 glob —— 资产全嵌在子目录里，
# 顶层一个都匹配不到（这正是旧说明失效的原因）。
rm -rf "$DEST/plasma/desktoptheme/Frost" \
       "$DEST/plasma/look-and-feel/com.xhhcn.frost" \
       "$DEST/plasma/layout-templates/com.xhhcn.frost."* \
       "$DEST/icons/Frost" \
       "$DEST/kwin/effects/frost_minimize" \
       "$DEST/frost"
rm -f  "$DEST"/color-schemes/Frost*.colors \
       "$DEST"/konsole/Frost.colorscheme \
       "$DEST"/konsole/Frost.profile
# ★ konsolerc 的 DefaultProfile 也要清 ★
# 不清的话它继续指向刚被删掉的 Frost.profile，Konsole 启动时静默回退到内置
# 默认 —— 表面能用，但配置里留着一个死引用。只在确实是我们写的值时才删，
# 不碰用户自己选的别的 profile。用 --delete 让 Konsole 自己决定默认。
if [ "$(kreadconfig6 --file konsolerc --group "Desktop Entry" --key DefaultProfile 2>/dev/null)" = "Frost.profile" ]; then
    kwriteconfig6 --file konsolerc --group "Desktop Entry" --key DefaultProfile --delete 2>/dev/null || true
fi
rm -rf "$DEST"/wallpapers/FrostScene-*

echo "==> 5/5  清缓存"
rm -f  "$HOME/.cache/plasma_theme_Frost"*.kcache "$HOME/.cache/icon-cache.kcache"
rm -rf "$HOME/.cache/ksvg-elements"
kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
qdbus6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
systemctl --user restart plasma-plasmashell.service 2>/dev/null || true

echo
echo "已卸载。若界面仍不正常，注销重登一次即可。"
if [ -d /usr/share/wallpapers/FrostLogin ]; then
cat <<'EOT'

登录界面壁纸是系统级的，需要你手动处理，**顺序很重要**：
  1. 先到「系统设置 → 登录屏幕」把壁纸改回 Breeze
     （这一步走 polkit，助手会清掉 /var/lib/plasmalogin 下的副本
       并重写 /etc/plasmalogin.conf）
  2. 之后再删系统目录：
     sudo rm -rf /usr/share/wallpapers/FrostLogin
反过来做没用：登录屏读的是 /var/lib 里的副本，先删 /usr/share 只会让
系统设置的列表里少一项、你再也看不出当前选的是什么。
EOT
fi
EOU
chmod +x "$R/uninstall.sh"

# ─────────────────────────────────────────────────────────────────────
# 清单校验。归档过期那次就是因为没有这一道：包里少了 kwin/effects，
# 而没有任何检查会发现。
# ─────────────────────────────────────────────────────────────────────
echo "==> 校验包内清单"
miss=0
need=(
  "share/plasma/desktoptheme/Frost/metadata.json"
  "share/plasma/look-and-feel/com.xhhcn.frost/metadata.json"
  "share/icons/Frost/index.theme"
  "share/konsole/Frost.colorscheme"
  "share/konsole/Frost.profile"
  "bin/daylight.py" "bin/tweak.py"
  "install.sh" "uninstall.sh"
  "share/kwin/effects/frost_minimize/metadata.json"
  "share/kwin/effects/frost_minimize/contents/code/main.js"
)
for f in "${need[@]}"; do
  [ -e "$R/$f" ] || { echo "  !! 缺少 $f" >&2; miss=1; }
done
# 四时段资产必须齐
for w in dawn day dusk night; do
  [ -d "$R/share/wallpapers/FrostScene-$w" ] || { echo "  !! 缺少壁纸 FrostScene-$w" >&2; miss=1; }
  [ -f "$R/share/color-schemes/Frost-$w.colors" ] || { echo "  !! 缺少配色 Frost-$w" >&2; miss=1; }
done
# 已安装树里有、包里没有的资产类别（防止将来新增资产忘了加进这里）
# 文件数比对：已安装的那份 vs 包内的那份，逐目录数。
# ★ 早先只比对了三类，漏掉 look-and-feel 和 layout-templates ★
# 那两个目录里是 splash 的 QML、defaults、以及面板布局脚本 ——
# 恰恰是最容易在 cp 里被 `|| true` 静默漏掉、又完全没有替代品的东西
# （splash 少一个 QML 就是开机白屏，布局模板少一个就是面板建不出来）。
# 数量相符不等于内容相符，但它能抓住「整个文件没进包」这一类，
# 而这一类正是 `cp ... || true` 会产生的失败模式。
# ★ 每一项都必须是 Frost 专属路径 ★ layout-templates 早先写成整个目录，
# 而包里只 cp 了 com.xhhcn.frost.* —— 用户目录里一旦多出任何第三方布局模板
# （另一套主题、或手工存的面板布局），这条就会以一个和 Frost 完全无关的
# 理由硬失败。本机现在恰好只有 com.xhhcn.frost.topbarDock（a=b=2）所以没暴露。
for d in plasma/desktoptheme/Frost \
         plasma/look-and-feel/com.xhhcn.frost \
         plasma/layout-templates/com.xhhcn.frost.topbarDock \
         icons/Frost \
         kwin/effects/frost_minimize; do
  a=$(find "$SRC/$d" -type f 2>/dev/null | wc -l)
  b=$(find "$R/share/$d" -type f 2>/dev/null | wc -l)
  [ "$a" = "$b" ] || { echo "  !! $d 文件数不符：已安装 $a / 包内 $b" >&2; miss=1; }
  [ "$a" = "0" ]   && { echo "  !! $d 在已安装侧是空的 —— 比对没有意义" >&2; miss=1; }
done

# 许可：每一种被声明的许可，包里都必须有对应的全文；反过来也不该多带。
# 同样从声明反查，不写死列表（理由见上面收集阶段那段注释）。
[ -s "$R/LICENSE" ] || { echo "  !! 包内缺顶层 LICENSE 索引" >&2; miss=1; }
declared=$(grep -rho '"License": *"[^"]*"' "$R/share" "$R/login-wallpaper" 2>/dev/null \
           | sed 's/.*: *"//;s/"//' | sort -u)
while IFS= read -r l; do            # 逐行读，理由同收集阶段（SPDX 表达式）
  [ -n "$l" ] || continue
  [ -s "$R/LICENSES/$l.txt" ] || {
    echo "  !! 有子包声明 License=$l，但包里没有 LICENSES/$l.txt" >&2; miss=1; }
done <<< "$declared"
# 反向：包里的全文都得有人声明 —— 多带一份没人用的许可是噪音，
# 也说明某个子包的许可被改过而这里没跟上。
#
# ★ 注意：这半边在当前流程里**永远不会命中**，不要当成一道生效中的门禁 ★
# $R/LICENSES 全部由上面收集阶段的 `while ... <<< "$declared"` 填充，
# 这里又用逐字相同的命令重算 declared（输入也没变），两个集合按构造恒等。
# 独立 harness 验证过这段逻辑本身是对的：人为往 $R/LICENSES 预置一份
# 没人声明的 BSD-3-Clause.txt → 确实报错。保留它是为了防将来有人往
# LICENSES/ 里加旁路拷贝，那时它才有判据。
# 正向那半边是真的有效：声明 Apache-2.0（无对应 txt）在收集阶段就硬失败。
for f in "$R/LICENSES"/*.txt; do
  [ -e "$f" ] || continue
  n=$(basename "$f" .txt)
  echo "$declared" | grep -qx "$n" || {
    echo "  !! 包里带了 LICENSES/$n.txt 但没有任何子包声明它" >&2; miss=1; }
done
[ "$miss" = 0 ] || { echo "!! 清单校验未通过，不打包" >&2; exit 1; }
echo "  清单校验通过（${#need[@]} 个必需项 + 四时段资产 + 五类文件数比对 + 许可全文覆盖声明）"

echo "==> 打包"
tar czf "$PKG" -C "$STAGE" "frost-$VER"

echo
echo "  $PKG"
echo "  大小 $(du -h "$PKG" | cut -f1)，解包后 $(du -sh "$R" | cut -f1)，共 $(find "$R" -type f | wc -l) 个文件"
echo
echo "  在另一台机器上："
echo "    tar xzf $(basename "$PKG") && cd frost-$VER && bash install.sh"
