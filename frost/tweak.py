#!/usr/bin/env python3
"""
Frost 后处理 —— 补上 plasma-apply-lookandfeel 不认的设置。

look-and-feel 的 defaults 文件只有一小撮白名单键会被应用
（ColorScheme / Icons / widgetStyle / 装饰 / 光标 / 启动画面 / Plasma 样式）。
毛玻璃真正依赖的 contrast、KWin 模糊参数、面板长度模式都不在其中，
必须在应用主题之后单独写入。
"""
import re, subprocess, sys, os

# ★ --appearance-only ★
# 从「系统设置 → 全局主题」切换 Frost 时，plasma-apply-lookandfeel 只应用
# 一份白名单里的键 —— 本文件写的 24 项一个都拿不到，其中 panelOpacity=2
# 是玻璃效果的命门（缺了面板直接变不透明）。
# 所以开机前钩子会以这个模式补齐**纯外观**的设置，
# 但**不碰面板几何和托盘排布** —— 那些属于布局，用户可能手工调过，
# 每次登录都重写会把人家的调整冲掉。
APPEARANCE_ONLY = "--appearance-only" in sys.argv

CFG = os.path.expanduser("~/.config")

def kwrite(file, groups, key, value):
    """groups 可以是字符串或列表。嵌套组必须传多个 --group，
    写成 'A][B' 会被当成字面量，生成 A\\x5d\\x5bB 这种假组。"""
    if isinstance(groups, str):
        groups = [groups]
    cmd = ["kwriteconfig6", "--file", file]
    for g in groups:
        cmd += ["--group", g]
    cmd += ["--key", key, str(value)]
    subprocess.run(cmd, check=False)

def _kwin_effect(method, name):
    """★ 只写 <name>Enabled=… 是不够的 ★
    `/KWin reconfigure` 只让各特效重读**自己的参数**（[Effect-*] 组），
    不会重新决定加载哪些特效 —— [Plugins] 里的开关只在 KWin 启动时读一次。
    实测：写完 squashEnabled=false 再 reconfigure，
    isEffectLoaded("squash") 仍然返回 true，动画照旧。
    要立刻生效必须显式 loadEffect / unloadEffect。
    没有 qdbus / KWin 没跑（比如打包机上）时静默跳过，不影响安装。"""
    for tool in ("qdbus6", "qdbus"):
        r = subprocess.run([tool, "org.kde.KWin", "/Effects",
                            f"org.kde.kwin.Effects.{method}", name],
                           capture_output=True, check=False)
        if r.returncode == 0:
            return True
    return False

def kwin_load_effect(name):   return _kwin_effect("loadEffect", name)
def kwin_unload_effect(name): return _kwin_effect("unloadEffect", name)

def main():
    print("==> 1/4  Breeze 半透明（毛玻璃的地基）")
    # contrast 越低，菜单/工具提示/KRunner/托盘弹窗越透明；0 = 最透
    kwrite("kdeglobals", "KDE", "contrast", 0)
    kwrite("kdeglobals", "KDE", "frameContrast", 0.15)
    print("    contrast=0  frameContrast=0.15")

    print("==> 2/4  KWin 模糊")
    kwrite("kwinrc", "Plugins", "blurEnabled", "true")
    kwrite("kwinrc", "Effect-blur", "BlurStrength", 13)
    kwrite("kwinrc", "Effect-blur", "NoiseStrength", 4)
    print("    blur=on  强度=13  噪点=4")
    # 注意：不要写 contrastEnabled。
    # KWin 6.7 的特效列表里已经没有 "contrast"（背景对比特效被移除/并入 blur），
    # 写了也是无效键。实测 isEffectLoaded("contrast") 恒为 false。
    # 因此玻璃通透度不能压太低 —— 没有背景对比兜底，壁纸太花时文字会糊。

    print("==> 3/4  最小化动画：squash 逐行照抄 + 动画期间提层")
    # ★ 唯一一处偏离上游，理由写清楚 ★
    # 实测窗口层级（KWin 脚本读 stackingOrder，全部 keepAbove=false）：
    #   Claude=5(最顶) / konsole=4 / dolphin=3 / systemsettings=2 / firefox=1
    # 最小化一个**非顶层**窗口时，它按自己的堆叠位置绘制 ——
    # 从顶层窗口下面穿过去，只看得见露在外面的部分。
    # 用户三次报告，措辞一致：「所有应用的最小化从 claude 下面过去了」。
    #
    # macOS / Windows 的最小化动画都画在所有窗口之上，
    # 而用户最早提的需求就是「类似 mac 或者 win 都是缩小到底部栏」。
    # 16 个自带 JS 特效用 setElevatedWindow 的确实是 0 个 —— 这是刻意偏离，
    # 不是「上游漏了」。setElevatedWindow 是 libkwin 导出的正规接口。
    #
    # ★ 我曾用错误的理由加过它、又用错误的推论删过它 ★
    # 加的时候写「窗口一旦 minimized 会被 KWin 从堆叠顺序里摘出去」——假的。
    # 但删的时候我把「那句解释是假的」推成了「提层不需要」——也不成立：
    # 窗口留在原位恰恰意味着**它在谁下面就画在谁下面**。
    # **证否一个理由 ≠ 证否那个结论。**
    #
    # 提层不产生第二种动画：曲线/时长/三条通道全不变，
    # 只是保证那一种动画始终画在最上层。#163 的碰撞守卫没有回来。
    kwrite("kwinrc", "Plugins", "frost_minimizeEnabled", "true")
    kwrite("kwinrc", "Plugins", "squashEnabled",         "false")  # 同互斥类别
    kwrite("kwinrc", "Plugins", "magiclampEnabled",      "false")
    ok = kwin_load_effect("frost_minimize")
    kwin_unload_effect("squash")
    kwin_unload_effect("magiclamp")
    print("    frost_minimize=on（squash+提层）  squash/magiclamp=off")
    print("    运行时生效: " + ("已生效" if ok else "跳过（KWin 未运行，下次启动生效）"))

    # ─────────────────────────────────────────────────────────────
    # ★ stock 特效裁定表 ★
    # 审计指出的真问题不是缓动，而是「主题接管了 minimize 这个互斥类别、
    # 其余类别一行没写」—— 接管一半比完全不接管更难解释。
    # 根因是一条原则从来没写下来。补上它：
    #
    #   【原则 1 的补充条款】不透明度动画只允许表达「存在性变化」
    #     （无→有 / 有→无），不允许表达「位置或状态变化」。
    #
    # 按这条逐个裁定所有会动不透明度的 stock 特效：
    #   scale（开窗/关窗）        保留 —— 存在性变化。窗口原本不存在，
    #                                   一个还不存在的东西没有材质可言
    #   fadingpopups（弹窗）      保留 —— 存在性变化，且弹窗本就是玻璃(chrome)
    #   login / logout（会话起止）保留 —— 存在性变化
    #   squash（最小化）          换成 frost_minimize —— 但**不是因为淡出**。
    #     ★ 这里原来写的理由是假的，别再照着它改代码 ★
    #     旧注释说「淡化它等于说它变成半透明了」，暗示替换是为了去掉 Opacity。
    #     实际 frost_minimize **完整保留**了 Opacity 1.0→0.0，与 squash 逐字相同。
    #     替换的唯一理由是**提层**（见 build-theme.py 的 kwin_effect_files()）。
    #     淡出这条按原则 1 确实可议，但保留它换来「与 squash 逐行一致」；
    #     动它就又要维护一个分支 —— 那正是 #163/#165 的失败模式。
    #   windowaperture（看桌面）  ↓ 关掉，唯一真正的违规
    #
    # 动亮度/饱和度的三个不受这条约束（去饱和是**移除**颜色而非引入新色相，
    # 不违反原则 2），全部保留：
    #   dialogparent  模态对话框时压暗父窗口   —— 合理的去强调
    #   dimscreen     提权/管理员提示时压暗屏幕 —— 安全信号，不该动
    #   frozenapp     无响应应用去饱和         —— 有用的状态信息
    #
    # 纯几何的全部保留：maximize / fullscreen（同族）、slide / slidingpopups /
    # slidingnotifications（面板与弹窗位移）。
    #
    # 未加载但已装机的，一旦有人在系统设置里勾上就会违反原则 1，
    # 一并裁定（不写进 kwinrc —— 它们默认关闭，写了反而是无谓的配置偏离）：
    #   eyeonscreen（excl=show-desktop，与 windowaperture 同类别）
    #                             ✗ 对现存窗口做 Scale+Opacity→0，同罪
    #   fadedesktop（excl=desktop-animations，与已加载的 slide 争同一类别）
    #                             ✗ 切虚拟桌面时把**现存**窗口整窗淡出淡入 —— 状态变化
    #   fade（excl=toplevel-open-close-animation，与已加载的 scale 争）
    #                             ○ 原则上允许（开关窗=存在性变化），但 scale
    #                               同时给了几何线索，信息更多，继续用 scale
    #
    # ★ 这张表的适用范围要说清楚，不要暗示"覆盖全部" ★
    # 实测库存：JS 脚本特效 16 + 内建特效 37 = **装机 53**，当前加载 29。
    # 本表点名 14 个（其中 squash/windowaperture 已关，不在加载集），
    # 加上 squash 共 **13 个已裁定**，剩 16 个已加载未裁定：
    #   blendchanges blur colorpicker highlightwindow kscreen outputlocator
    #   overview screenedge screentransform sessionquit shakecursor
    #   startupfeedback systembell tileseditor windowview zoom
    # 这 16 个里绝大多数不动"窗口的材质感"——是工具（colorpicker/zoom/
    # outputlocator/tileseditor）、模式切换（overview/windowview）、
    # 硬件过渡（kscreen/screentransform）、光标或提示（shakecursor/
    # startupfeedback/systembell/screenedge），以及 blur（本主题自己开的）
    # 和 blendchanges（是**工具**，见下方强调色转场的待办）。
    # sessionquit 实测是空动画（duration 30s、from 0.0 to 0.0、
    # 自称 "just hold a reference"），零视觉影响。
    # 唯一真正落在原则 1 射程内的是 highlightwindow ↓
    # ─────────────────────────────────────────────────────────────
    # highlightwindow：悬停任务栏条目时压暗**其他现存窗口**来高亮一个 ——
    # 状态变化，和 windowaperture 同罪。但**不关它**，理由是它打不响：
    #   · 167 条 kwin 快捷键里 highlight 0 条（用带 service 名的
    #     `qdbus6 org.kde.kglobalaccel /component/kwin ...shortcutNames`；
    #     不带 service 名会返回 0 行，那是命令无效不是真阴性）
    #   · 全盘 `grep -ra 'highlightWindows'` 只命中 kwin_wayland 与
    #     libkwin.so（都是它自己的 RTTI 符号），plasmashell 0 次
    #   · QML 侧 0 命中（对照：同目录搜 'kwin' 有命中，证明扫描有效）
    #   Plasma 6 的任务栏已改用缩略图，不再调这个 DBus 口。
    #   它 EnabledByDefault=True 且无互斥类别 —— 关掉只是无谓的配置偏离，
    #   而万一将来上游恢复了任务栏侧调用，静默关掉它反而是个意外。
    # ─────────────────────────────────────────────────────────────
    # windowaperture 让**现存的内容窗口**变半透明去看桌面 —— 状态变化，
    # 直接违反原则 1。
    # ★ 这里原来引的证据是无效的 ★
    # 旧注释写「实测 kglobalaccel shortcutNames | grep -c windowaperture
    # 返回 0：根本没有快捷键能触发它，纯粹白占着一个特效槽」。
    # 那个 0 什么也没证明 —— **快捷键是按「动作」命名的，不是按特效命名的**，
    # 特效名永远不会出现在 shortcutNames 里。正确的查法是找它争的那个
    # 互斥类别对应的动作：windowaperture 的 excl 是 show-desktop，
    # 而实测 167 条快捷键里 "Show Desktop" **有 1 条绑定** ——
    # 所以它**完全能被触发**。关掉它的真实理由比我原先写的更强：
    # 不是"反正打不响"，而是"它会响，而且响的时候违反原则 1"。
    kwrite("kwinrc", "Plugins", "windowapertureEnabled", "false")
    kwin_unload_effect("windowaperture")
    print("    windowaperture=off（让现存窗口变透明，违反「不透明度只承载语义」）")

    print("==> 4/4  面板（顶栏 + 底栏）")
    # location: 3=顶部  4=底部
    applets = os.path.join(CFG, "plasma-org.kde.plasma.desktop-appletsrc")
    # ★ 必须守卫 ★
    # 这个文件在 Plasma 首次创建面板之前不存在；用户也可能删过。
    # 早先直接 open() 会抛异常，而登录钩子是
    # `python3 tweak.py --appearance-only >/dev/null 2>&1 || true` ——
    # 输出全丢、退出码吞掉，后面的 Darkly 配置和托盘设置一条都不执行，
    # 完全静默。
    try:
        txt = open(applets).read()
    except OSError as e:
        print(f"    !! 读不到 {applets}: {e}", file=sys.stderr)
        print("       跳过面板配置（Plasma 可能还没创建过面板）", file=sys.stderr)
        txt = ""
    # ★ 必须用列表，不能用字典 ★
    # 早先是 panels[{"3":"顶栏","4":"底栏"}.get(loc)] = cid ——
    # 同一边有两条面板时（外接显示器各加一条顶栏，或单屏并排两条底栏），
    # 后一个会把前一个从字典里挤掉，被挤掉的那条**永远拿不到 panelOpacity=2**
    # （玻璃效果的命门），回落到「自适应」，窗口一贴近就变不透明。
    # 而且末尾那句「未找到任何面板」也不会触发 —— 字典非空，完全无提示。
    # location 5/6（左/右栏）原先会落进 .get 的兜底分支、被当成底栏写 60px 高，
    # 而竖栏的 thickness 是宽度，60px 明显不对。
    panels = []
    for m in re.finditer(r"\[Containments\]\[(\d+)\]\n((?:(?!\[)[^\n]*\n)*)", txt):
        cid, body = m.group(1), m.group(2)
        if "plugin=org.kde.panel" not in body:
            continue
        loc = re.search(r"location=(\d+)", body)
        if loc:
            panels.append((cid, loc.group(1)))

    # 顶栏高度直接指定像素。
    # 布局脚本里写 gridUnit*N 不可靠 —— Plasma 会按内容再撑开，
    # 实测 2.2→22px 而 3.2→58px，不是线性关系，调不准。
    # 两条栏都要显式给高度（曾经以为底栏「改不动」，是错的）。
    TOP_THICKNESS = 34
    # 底栏必须显式给高度。早先以为「不写就交给 icontasks 自己撑」——
    # 错的，Plasma 会回落到一个很小的默认值，实测图标只有 22px。
    # 实测对应关系：面板 44→图标 33 / 52→37 / 60→49。
    # 取 60：图标 49px 是舒适的 dock 尺寸，和 34px 的顶栏形成清晰主次。
    BOTTOM_THICKNESS = 60

    def _resolve_preferred(val):
        """把 launchers 里的 preferred://X 解析成具体的 .desktop。

        ★ 这是「重启后 app 顺序会变、最小化飞错图标」的根因 ★
        用户给的复现方法定位了它：重启面板后立刻截图、再过 10 秒截图，
        顺序变了。实测（+3s / +14s / +25s 三次抓图 + 像素相关识别）：
            +3s   settings → Claude  → dolphin → firefox → konsole
            +14s  settings → dolphin → firefox → konsole → Claude   ← 重排
        而 KWin 拿到的 iconGeometry 三次**完全相同**、正好等于 +3s 那一刻的顺序 ——
        **任务栏在重排后没有重新上报几何**，所以那个值永久过期。
        这才是最小化飞到相邻应用图标上的真正原因；不是特效的 bug，
        也不是「排列错乱」，更不是纯启动器数量（那两条假设都实测证否了）。

        重排的来源：`preferred://filemanager` / `preferred://browser` 是间接引用，
        要查 mimeapps 才知道具体是哪个 .desktop，**这一步是异步的**。
        解析完成前，Dolphin/Firefox 的窗口匹配不上任何启动器条目，
        和未固定的应用一样排在后面；解析完成后 launchInPlace 把它们收进各自
        槽位，未固定的应用就被挤到末尾 —— 正好一格的位移。

        ★ 更正：Breeze 并非「不配置 launchers」★
        它的 defaultPanel/layout.js 确实不 writeConfig（grep 计数 0），但
        「不写」= 用 applet 的 KConfigXT 默认值，而那个默认值是
            applications:systemsettings.desktop,applications:org.kde.discover.desktop,
            preferred://filemanager,preferred://browser
        —— 同样 4 条固定启动器、同样含 2 条 preferred://。
        旁证：vinyl 的 layout.js 显式写的 launchers **逐字等于**这一串。
        所以「Breeze 免疫」是错的推论。真正的差异是 separateLaunchers
        （Breeze 用默认值 true → 重排后不重报几何；本主题写 false）。

        ★ 更正：解析本身是**同步**的 ★
        `nm -DC /usr/lib/libtaskmanager.so` → `T TaskManager::defaultApplication(QUrl const&)`
        返回 QString，没有任何 Job/Watcher/信号。
        延迟重排的真正来源是 KSycoca：同一份 nm 里有 `U KSycoca::databaseChanged()`，
        登录后 kbuildsycoca6 重建完毕会触发 launcher 列表**重新解析**一次。
        预先解析成具体 .desktop 就绕开了 sycoca —— 这才是本函数真正的作用。

        修法就是在这里把 preferred:// 解析掉，启动时不再有异步窗口。
        仍然保留可移植性 —— 每台机器按自己的默认应用解析一次，
        而不是把 dolphin/firefox 写死在主题里。
        解析不出来时保留原值：宁可顺序会变，也不要写一个无效条目让图标消失。
        """
        import shutil
        MIME = {"preferred://filemanager": "inode/directory",
                "preferred://browser":     "x-scheme-handler/http"}
        if not shutil.which("xdg-mime"):
            return val, 0
        out, fixed = [], 0
        for e in val.split(","):
            m = MIME.get(e.strip())
            if not m:
                out.append(e); continue
            r = subprocess.run(["xdg-mime", "query", "default", m],
                               capture_output=True, text=True, check=False)
            d = r.stdout.strip()
            if r.returncode == 0 and d.endswith(".desktop"):
                out.append("applications:" + d); fixed += 1
            else:
                out.append(e)          # 解析失败就保留原值
        return ",".join(out), fixed

    # ── 任务栏排序：必须放在 panels 构建之后 ──
    # （早先插在 main() 前部，引用了还没定义的 panels/txt，
    #   py_compile 过得去、实跑才 NameError —— 同 README #118）
    # ★ 这是「重启后 app 顺序一直在变」的根因 ★
    # 用户实测：用 Breeze 时顺序不变，换 Frost 后开始乱。差异定位到一处 ——
    # Breeze 的 defaultPanel 模板**也用 org.kde.plasma.icontasks**（同一个组件，
    # `X-Plasma-RootPath = org.kde.plasma.taskmanager`），
    # ★ 更正：不能说 Breeze「完全不配置 launchers」★
    # 它的 layout.js 确实不 writeConfig launchers（grep 计数 0），但「不写」
    # = 用 applet 的 KConfigXT 默认值，而那个默认值同样是 4 条、同样含 2 条
    # preferred://（解出的 main.xml 可查，详见 _resolve_preferred() 里那段更正）。
    # 所以「Breeze 免疫是因为它没有固定启动器」是**错的推论** ——
    # 真正的差异是 separateLaunchers：Breeze 用默认值 true（重排后不重报几何），
    # 本主题显式写 false。按旧说法推理会得出「少配几个启动器就能修」，
    # 那个方向已经被证否过了。
    #
    # ★★ 这里曾经写三个排序键，实测证明它们对顺序**毫无影响**，已删 ★★
    # 原先写 launchInPlace=true / separateLaunchers=true / sortingStrategy=1，
    # 并声称「这是本问题的直接原因」「顺序一稳落点自然就对」。
    # 用删除测试直接证否了：把三个键**全部删掉**（= Breeze 的状态，它一个都不设）
    # 再重启 plasmashell 两次，窗口顺序与保留三个键时**逐字完全相同**，
    # 而且两次重启之间也完全一致。三种配置（三键齐 / separateLaunchers=false /
    # 全删）给出同一个顺序 —— 它们是无效配置，只是徒增与上游的偏离。
    #
    # 真正的机制（实测复现）：plasmashell 在任务栏重排后**不保证**给所有窗口
    # 重报 iconGeometry。触发一次重排（关掉一个 app）后：
    #     真实渲染   systemsettings 830 / firefox 961 / konsole 1026 / Claude 1092
    #     KWin 手里  systemsettings 830 / firefox 962 / konsole 1027 / Claude **830**
    # systemsettings 与 Claude 交换了槽位，前者的几何更新了、**后者没有**。
    # 出问题的总是**没有被固定（不在 launchers 里）的那个窗口** ——
    # 固定过的 app 有自己的永久槽位，关掉它启动器还在原处，什么都不动。
    #
    # 所以这里能做的只有一件事：把 preferred:// 解析掉（消除启动期的异步重排）。
    # 剩下的两条防线在别处：
    #   · 用户侧：把常用 app 固定到 dock，它的槽位就永不移动（macOS/Windows 同理）
    #   · 特效侧：曾加过碰撞守卫，但它造成「两种动画」，**只删掉了守卫** ——
    #     两个窗口报同一个图标格时那份数据可证伪，宁可原地淡出也不飞错 app。
    #     注意措辞：早先这里写「已随自制特效一起删除」，但自制特效
    #     frost_minimize **还在**（本函数上面就写着 frost_minimizeEnabled=true，
    #     实测 isEffectLoaded → true）。删掉的只是守卫那段逻辑。
    # 教训：**「配了一个键 + 问题好转」不等于那个键起了作用。**
    # 当时问题好转是 _resolve_preferred() 的功劳，三个排序键搭了便车。
    # 判据只有一个：把它删掉，看读数变不变。
    tray_grp = None
    for pid, loc in panels:
        if loc != "4":            # 只处理底栏
            continue
        # 找底栏里的 icontasks
        m = re.findall(
            r"\[Containments\]\[%s\]\[Applets\]\[(\d+)\]\nimmutability=\d+\nplugin=org\.kde\.plasma\.icontasks"
            % pid, txt)
        if not m:
            m = re.findall(
                r"\[Containments\]\[%s\]\[Applets\]\[(\d+)\][\s\S]{0,200}?plugin=org\.kde\.plasma\.icontasks"
                % pid, txt)
        for aid in m:
            g = ["Containments", pid, "Applets", aid, "Configuration", "General"]
            # ★ 先解析 preferred://，这是根因修复；排序键是配套 ★
            cur = subprocess.run(
                ["kreadconfig6", "--file", "plasma-org.kde.plasma.desktop-appletsrc",
                 "--group", "Containments", "--group", pid, "--group", "Applets",
                 "--group", aid, "--group", "Configuration", "--group", "General",
                 "--key", "launchers"],
                capture_output=True, text=True, check=False).stdout.strip()
            if cur:
                new, cnt = _resolve_preferred(cur)
                if cnt:
                    kwrite("plasma-org.kde.plasma.desktop-appletsrc", g, "launchers", new)
                    print(f"    已把 {cnt} 个 preferred:// 解析成具体 .desktop"
                          f"（消除启动时重排 → iconGeometry 不再过期）")
            # ★ 对齐两个上游参照，逐键说明（两边都取自源码原文）★
            # Breeze: /usr/share/plasma/layout-templates/
            #         org.kde.plasma.desktop.defaultPanel/contents/layout.js:27
            #         —— 只有 addWidget("org.kde.plasma.icontasks")，什么都不设
            # vinyl : plasma/layout-templates/com.ekaaty.vinyl.desktop.bottomPanel/
            #         contents/layout.js —— 只写 launchers + separateLaunchers=false
            #
            # | 键 | schema 默认 | Breeze | vinyl | 这里 |
            # |---|---|---|---|---|
            # | launchers              | 4 条含 preferred:// | 不设 | **设** | 设（并解析 preferred://）|
            # | separateLaunchers      | true | 不设 | **显式 false** | **显式 false**（对齐 vinyl）|
            # | sortingStrategy        | 1    | 不设 | 不设 | **不设**（我们写的就是 1，纯空操作）|
            # | showOnlyCurrentDesktop | true | 不设 | 不设 | **不设**（上游都不设）|
            # | indicateAudioStreams   | true | 不设 | 不设 | **不设**（我们写的就是 true，纯空操作）|
            # | launchInPlace          | 不是配置键 | — | — | 删除（清旧安装残留）|
            #
            # 原则：**只写真正偏离默认、且有实测理由的键**。
            # 唯一符合这条的是 separateLaunchers（默认 true → 我们要 false，
            # 它是 iconGeometry 重报的开关，README #163）。
            #
            # separateLaunchers=false 的含义：启动器与运行窗口**不分组**，
            # 运行中的 app 占用它自己启动器的槽位 —— 这正是 dock 想要的。
            #
            # ★ 它不是空操作，默认值也不是 false —— 旧注释这两条都错 ★
            # KConfigXT schema（taskmanager.so 的 QRC，zstd）写的是
            #     <entry name="separateLaunchers" type="Bool"><default>true</default>
            # 当初那个「未设时的顺序与显式 false 逐字相同」的观测，对这个键
            # **没有任何区分力**：icontasks 下 model 的 separateLaunchers 被
            # Tasks.qml 在 `!tasks.iconsOnly` 处短路成恒 true，所以它本来就
            # 改不动分组与顺序 —— 测顺序当然测不出差别。
            # 它真正控制的是 Task.qml:232-234：重排时要不要 requestLayout()，
            # 也就是 500ms 后要不要把 iconGeometry 重报给 KWin
            # （完整源码链见 build-theme.py 的 layout_js()）。必须显式 false，
            # 否则任务栏重排后 KWin 手里的图标几何永久过期，最小化动画飞到
            # 相邻 app 的图标上（README #163）。
            # 顺带也对齐了 vinyl-theme —— 它同样是 icontasks + 固定启动器的 dock。
            kwrite("plasma-org.kde.plasma.desktop-appletsrc", g,
                   "separateLaunchers", "false")
            # ★ sortingStrategy = 1 (SortManual) —— 这**不是**偏离，是钉死默认值 ★
            # applet 自己的 KConfigXT schema（在 taskmanager.so 的 QRC 里，
            # **zstd** 压缩不是 zlib —— 扫 28 b5 2f fd 魔数再 unzstd 就能解出）
            # 写的就是 <default>1</default>。Breeze 和 vinyl 都不设这个键，
            # 所以它们最终也是 1 —— **「上游不设」不等于「上游不是 1」**。
            # 我此前写「刻意偏离两个上游参照」是错的。
            # 保留显式写入的理由只有一条：用户可能在部件设置的「排序」下拉框里
            # 改成 SortAlpha(2) / SortLastActivated(5)，那才会点一下就换位置。
            # 枚举（/usr/lib/qt6/qml/org/kde/taskmanager/taskmanager.qmltypes）：
            #   0 SortDisabled  1 SortManual  2 SortAlpha  3 SortVirtualDesktop
            #   4 SortActivity  5 SortLastActivated  6 SortWindowPositionHorizontal
            # SortManual 的定义就是「保持手动顺序、不自动排序」——
            # 这正是「5 个固定图标的 dock」需要的性质。
            #
            # ★★ 最终决定：**不写这个键** ★★
            # 依据一（对照上游原文，不是回忆）：
            #   Breeze  /usr/share/plasma/layout-templates/
            #           org.kde.plasma.desktop.defaultPanel/contents/layout.js
            #           第 27 行只有 panel.addWidget("org.kde.plasma.icontasks")，
            #           三个键一个都不设，连 launchers 也不设。
            #   vinyl   plasma/layout-templates/com.ekaaty.vinyl.desktop.bottomPanel/
            #           contents/layout.js 只写 launchers + separateLaunchers=false。
            #   两个参照都不设 sortingStrategy。
            # 依据二：我们写的值 **就是 schema 默认值 1**，属于纯空操作。
            # 依据三（安全性，不是「反正是默认值」这种含糊理由）：
            #   launchInPlace 是派生属性 `sortingStrategy === 1`；键不设时
            #   KConfigXT 返回默认值 1，`=== 1` 仍为真 → launchInPlace 不变。
            #
            # ★ 那条「防点击重排」的旧理由已作废 ★
            # 旧注释说保留它是为了「用户可能在部件设置里改成 SortAlpha，
            # 那才会点一下换位置」。问题在于：那是**用户自己改的**，
            # 每次完整应用把它按回 1 等于跟用户对抗。要防的是我们自己写错值，
            # 而不是覆盖用户的选择。
            # 枚举留档（/usr/lib/qt6/qml/org/kde/taskmanager/taskmanager.qmltypes）：
            #   0 SortDisabled  1 SortManual  2 SortAlpha  3 SortVirtualDesktop
            #   4 SortActivity  5 SortLastActivated  6 SortWindowPositionHorizontal
            #
            # ★ 顺带记一个实测事实，免得以后又来回改 ★
            # 「非 pin 窗口的顺序重启后会变」和这个键无关，也和主题无关：
            # applet 的 schema 一共 32 个 entry，能持久化顺序的只有 launchers；
            # 拖动走的是 tasksModel.move(from,to)，它**不写任何配置**
            # （只有 launcher 列表变化才会 onLauncherListChanged →
            #   Plasmoid.configuration.launchers = launcherList）。
            # 所以想让某个 app 位置固定，唯一办法是 pin 它 —— 任何主题都一样。
            # 实测：Frost 配置 3 次重启 1 次重排、Breeze 配置 3 次 0 次，
            # 这个样本量区分不开，不能据此说有差异。
            # launchInPlace 仍然删除：两个上游都不设，且它的语义
            # （启动器槽位被自己的窗口复用）在 separateLaunchers=false 下本就成立。
            for dead in ("launchInPlace",):
                subprocess.run(
                    ["kwriteconfig6", "--file",
                     "plasma-org.kde.plasma.desktop-appletsrc",
                     "--group", "Containments", "--group", pid,
                     "--group", "Applets", "--group", aid,
                     "--group", "Configuration", "--group", "General",
                     "--key", dead, "--delete"],
                    capture_output=True, check=False)
            # 输出只陈述真正做过的事：写了一个键、删了一个遗留键。
            # （曾经这里打印 sortingStrategy=1 —— 那个键现在根本不写了。
            #   更早还有一版在 --appearance-only 下也照样宣称写过它，
            #   而实际一次都没写；桩运行日志里出现 0 次。教训是：
            #   输出文案必须和实际动作逐项对应，否则排查时会被自己误导。）
            print(f"    底栏 applet {aid}: separateLaunchers=false（对齐 vinyl）"
                  "  已清除 launchInPlace")
            tray_grp = aid
    if tray_grp is None:
        print("    !! 底栏没找到 icontasks，跳过排序设置", file=sys.stderr)

    LOC_NAME = {"3": "顶栏", "4": "底栏", "5": "左栏", "6": "右栏"}
    for pid, loc in panels:
        label = LOC_NAME.get(loc, f"面板{loc}")
        grp = ["PlasmaViews", f"Panel {pid}"]

        # ── 布局类：只在完整模式写 ──
        # 这些决定面板多高、多长、会不会自动隐藏 —— 属于用户可能手工调过的东西。
        # --appearance-only（开机前钩子用）不碰它们，否则每次登录都把调整冲掉。
        if not APPEARANCE_ONLY:
            # ★ 顶栏和底栏各写各的高度 ★
            # 早先这里对**每个**面板都写 TOP_THICKNESS，把底栏也压成 34px，
            # 图标挤成一团；后来又矫枉过正、干脆不写，Plasma 回落到更小的
            # 默认值，图标只剩 22px。两次都是用户实际撞到的。
            # 竖栏（左/右）的 thickness 是**宽度**，34/60 都不适用，跳过不动
            th = {"3": TOP_THICKNESS, "4": BOTTOM_THICKNESS}.get(loc)
            if th is not None:
                kwrite("plasmashellrc", ["PlasmaViews", f"Panel {pid}", "Defaults"],
                       "thickness", th)
            # panelLengthMode: 0=FillAvailable  1=FitContent  2=Custom
            kwrite("plasmashellrc", grp, "panelLengthMode", 0)
            kwrite("plasmashellrc", grp, "floating", 0)
            kwrite("plasmashellrc", grp, "panelVisibility", 0)

        # ── 外观类：两种模式都要写 ──
        # panelOpacity: 0=自适应 1=不透明 2=半透明
        # 必须显式设成半透明。默认的「自适应」会在窗口贴近时切到 solid/ 分支，
        # 毛玻璃时有时无，既不好排查也不好看。这是玻璃效果的命门。
        kwrite("plasmashellrc", grp, "panelOpacity", 2)
        th = {"3": TOP_THICKNESS, "4": BOTTOM_THICKNESS}.get(loc)
        print(f"    {label} (面板 {pid}) → "
              f"{str(th)+'px ' if th else ''}贴边常驻 + 强制半透明")
    if not panels:
        print("    !! 未找到任何面板，跳过")

    # ---- Konsole 默认 profile ----
    # 资产（Frost.colorscheme / Frost.profile）由 install-frost.sh 装；
    # 这里只写「用哪个」这一个设置，和本文件其余部分的分工一致。
    #
    # ★ 只有 profile 真的装上了才写 ★ 否则 konsolerc 会指向一个不存在的
    # profile，Konsole 启动时静默回退到内置默认 —— 用户看到的是「主题装了
    # 但终端没变」，而 konsolerc 里却写着 Frost，排查时非常误导。
    #
    # ★ 组名是 [Desktop Entry]，不是 [General] ★
    # 实测确认：写完之后 Konsole 的 DBus 报 /Windows/1 default=Frost。
    _kprof = os.path.expanduser("~/.local/share/konsole/Frost.profile")
    if os.path.exists(_kprof):
        kwrite("konsolerc", "Desktop Entry", "DefaultProfile", "Frost.profile")
        print("==> 附加  Konsole 默认 profile = Frost（新开的终端自动应用配色）")
    # 注意：不动用户已有的其它 profile，也不改字体/滚动条/光标 ——
    # 那些是功能偏好不是主题事项，理由见 build-theme.py 的 konsole_profile()。

    # ---- Darkly（Lightly 的 Qt6 活跃分支）控件风格 ----
    # 只有装了才配；没装就跳过，主题照常用 Breeze。
    if os.path.exists(os.path.expanduser(
            "~/.local/lib/plugins/styles/darkly6.so")):
        print("==> 附加  Darkly 控件风格（圆角 + 半透明）")
        # plasma-apply-lookandfeel 会校验控件风格是否存在，而它运行时没有
        # QT_PLUGIN_PATH，找不到 ~/.local 里的 Darkly 就会静默退回 Breeze。
        # 所以这里必须直接写 kdeglobals，并且两个位置都写。
        kwrite("kdeglobals", "KDE", "widgetStyle", "Darkly")
        kwrite("kdedefaults/kdeglobals", "KDE", "widgetStyle", "Darkly")
        # darklyrc 分三个组，键放错组会被静默忽略：
        #   [Common]  圆角、阴影      —— kstyle 和 kdecoration 共用
        #   [Style]   各类控件不透明度、边框开关 —— 只有 kstyle 读
        #   [Windeco] 窗口装饰专属
        # 早期版本把 CornerRadius/ShadowStrength 写进了 [Style]，完全没生效。

        # ---- [Common] 圆角与阴影 ----
        kwrite("darklyrc", "Common", "CornerRadius", 10)      # 跟 Frost 的 RADIUS 对齐
        kwrite("darklyrc", "Common", "ShadowSize", "ShadowMedium")
        kwrite("darklyrc", "Common", "ShadowStrength", 102)
        kwrite("darklyrc", "Common", "ShadowIntensity", "Medium")
        kwrite("darklyrc", "Common", "OutlineCloseButton", "false")
        kwrite("darklyrc", "Common", "FancyMargins", "true")

        # ---- [Style] 半透明 + 去掉多余边框（扁平化的关键）----
        #
        # 只有 MenuOpacity 能安全地设成半透明 —— 弹出菜单是独立的顶层窗口，
        # KWin 会给它单独做模糊。
        #
        # 其余几个（MenuBar / ToolBar / TabBar / Dolphin*）作用于**窗口内部区域**，
        # 没有独立的合成表面。设成半透明会读到过期的帧缓冲内容，
        # 表现为工具栏里透出后面窗口的文字残影。必须保持 100。
        kwrite("darklyrc", "Style", "MenuOpacity", 82)
        kwrite("darklyrc", "Style", "MenuBarOpacity", 100)
        kwrite("darklyrc", "Style", "ToolBarOpacity", 100)
        kwrite("darklyrc", "Style", "TabBarOpacity", 100)
        kwrite("darklyrc", "Style", "DolphinSidebarOpacity", 100)
        kwrite("darklyrc", "Style", "DolphinViewOpacity", 100)
        kwrite("darklyrc", "Style", "DockWidgetDrawFrame", "false")
        kwrite("darklyrc", "Style", "TitleWidgetDrawFrame", "false")
        kwrite("darklyrc", "Style", "SidePanelDrawFrame", "false")
        kwrite("darklyrc", "Style", "KTextEditDrawFrame", "false")
        kwrite("darklyrc", "Style", "RoundedRubberBandFrame", "true")
        kwrite("darklyrc", "Style", "WidgetDrawShadow", "true")

        # ---- [Windeco] 窗口装饰：无边框 + 圆角 + 去渐变 ----
        kwrite("darklyrc", "Windeco", "BorderSize", "BorderNone")
        kwrite("darklyrc", "Windeco", "RoundedCorners", "true")
        # 不要写 -1（原意是「跟随 CornerRadius」）—— kwriteconfig6 会把 -1
        # 当成命令行选项，报 "Unknown option '1'" 并跳过这次写入。直接给同值。
        kwrite("darklyrc", "Windeco", "OtherCornerRadius", 10)
        kwrite("darklyrc", "Windeco", "DrawBackgroundGradient", "false")
        kwrite("darklyrc", "Windeco", "DrawTitleBarSeparator", "false")
        kwrite("darklyrc", "Windeco", "DrawBorderOnMaximizedWindows", "false")
        kwrite("darklyrc", "Windeco", "TitleAlignment", "AlignCenter")
        kwrite("darklyrc", "Windeco", "AnimationsEnabled", "true")
        print("    [Common] 圆角=10 阴影=Medium/102")
        print("    [Style]  菜单=82（半透明）；窗口内区域全部 100（避免残影）")
        print("    [Windeco] 无边框 + 圆角 + 去渐变 + 标题居中")
    # 托盘的常显/折叠排布同样属于布局，--appearance-only 不碰
    if not APPEARANCE_ONLY:

        # ---- 系统托盘：显式指定项目 ----
        # 新建的托盘没有 [General] 段，走默认项，笔记本上连电池都不显示。
        # 注意组路径是 Containments][<面板id>][Applets][<托盘id>][General，
        # 不是托盘 applet 的 [Configuration][General]。
        tray_id = tray_panel = None
        for m in re.finditer(r"\[Containments\]\[(\d+)\]\[Applets\]\[(\d+)\]\n"
                             r"((?:(?!\[)[^\n]*\n)*)", txt):
            if "org.kde.plasma.systemtray" in m.group(3):
                tray_panel, tray_id = m.group(1), m.group(2)
        if tray_id:
            items = ",".join([
                "org.kde.plasma.battery", "org.kde.plasma.brightness",
                "org.kde.plasma.volume", "org.kde.plasma.networkmanagement",
                "org.kde.plasma.bluetooth", "org.kde.plasma.clipboard",
                "org.kde.plasma.notifications", "org.kde.plasma.devicenotifier",
                "org.kde.plasma.keyboardlayout", "org.kde.plasma.mediacontroller",
                "org.kde.kscreen", "org.kde.plasma.manage-inputmethod",
            ])
            # extraItems/knownItems 只是「注册」，不代表常显 ——
            # Plasma 默认把它们折叠进 ⌃ 隐藏区。要常显必须写 shownItems。
            # 不含 keyboardlayout —— 本机只有一个键盘布局，那个图标是纯噪音，
            # 参考图的托盘里也没有。
            shown = ",".join([
                "org.kde.plasma.battery", "org.kde.plasma.volume",
                "org.kde.plasma.networkmanagement", "org.kde.plasma.bluetooth",
                "org.kde.plasma.brightness", "org.kde.plasma.clipboard",
            ])
            # 没列进 shownItems 的项会走「自动」，仍可能自己冒出来 ——
            # 键盘布局就是这样，本机只有一个布局，那个图标纯属噪音。
            # 要真正藏掉必须写进 hiddenItems。
            hidden = ",".join([
                "org.kde.plasma.keyboardlayout", "org.kde.plasma.keyboardindicator",
                "org.kde.plasma.manage-inputmethod", "org.kde.plasma.vault",
                "org.kde.plasma.printmanager", "org.kde.plasma.weather",
                "org.kde.plasma.cameraindicator", "org.kde.kscreen",
                "org.kde.plasma.devicenotifier", "org.kde.plasma.mediacontroller",
                "org.kde.plasma.notifications",
            ])
            grp = ["Containments", tray_panel, "Applets", tray_id, "General"]
            kwrite("plasma-org.kde.plasma.desktop-appletsrc", grp, "extraItems", items)
            kwrite("plasma-org.kde.plasma.desktop-appletsrc", grp, "knownItems", items)
            kwrite("plasma-org.kde.plasma.desktop-appletsrc", grp, "shownItems", shown)
            kwrite("plasma-org.kde.plasma.desktop-appletsrc", grp, "hiddenItems", hidden)
            print(f"    托盘 {tray_id} → 6 项常显（含电池），11 项收进折叠区")
        else:
            print("    !! 未找到系统托盘")

    # 清掉早期版本 kwriteconfig6 组名转义 bug 留下的假组
    shellrc = os.path.join(CFG, "plasmashellrc")
    try:
        txt = open(shellrc).read()
    except OSError:
        txt = ""            # 文件不存在就没什么可清理的
    cleaned = re.sub(r"\[PlasmaViews\\x5d\\x5bPanel \d+\]\n(?:[^\[\n][^\n]*\n)*", "", txt)
    if txt and cleaned != txt:
        open(shellrc, "w").write(cleaned)
        print("    已清除转义 bug 产生的无效配置组")

if __name__ == "__main__":
    main()
