# Frost

A hand-written frosted-glass theme for KDE Plasma 6. Every asset is generated from code — no SVG, colour or icon was downloaded from anywhere.

Built for Arch Linux + Plasma 6.7 + Wayland.

<!-- Add a desktop screenshot here after publishing. A GitHub landing page with an image reads very differently from one without. -->

## What it covers

| | |
|---|---|
| **Plasma style** | Translucent panels, popups, tooltips and dialogs (KSvg nine-slice, generated) |
| **Colour schemes** | Five — a base plus one per time of day |
| **Wallpapers** | Four hand-drawn valley scenes, pixel-aligned so they cross-fade cleanly |
| **Icons** | Hand-drawn folders that follow the accent; everything else inherited |
| **Splash** | Bridges the login screen into the desktop |
| **KWin effect** | Minimise animation drawn above other windows |
| **Konsole** | Colour scheme and profile, applied automatically |
| **GTK** | Colour names mapped so GTK3/GTK4 apps follow along |

## Time of day

The accent colour follows the **solar elevation angle** at your location, computed from your timezone. Nothing is stored, and nothing leaves the machine.

| Period | Accent | |
|---|---|---|
| dawn | `255,179,122` | peach |
| day | `104,203,223` | cyan |
| dusk | `245,185,66` | gold |
| night | `152,173,230` | indigo |

Wallpaper, colour scheme, splash and lock screen all move together. A systemd **user timer** runs a short Python script every 20 minutes — there is no resident process, and idle cost is roughly 1.5 seconds of CPU per day.

## Design rules

Three constraints shaped most of the decisions:

- **Colour carries exactly two meanings.** Accent means *time*; selection, hover and focus mean *state*. Everything else is monochrome. This is why the terminal is the one surface that does *not* take the accent — ANSI is already a colour language there, and a third one would compete with it.
- **Every number is measured, not chosen.** Opacities, contrast ratios and animation timings were derived from rendered pixels. Text is held to 4.5:1, non-text UI components to 3:1.
- **Glass is for chrome, not content.** Panels and popups are translucent; a terminal body is not.

## Install

```bash
git clone https://github.com/xhhcn/frost.git && cd frost/frost
python3 build-theme.py     # generate everything into out/
bash install-frost.sh      # copy into ~/.local/share
bash apply-frost.sh        # apply — add --layout for the top bar + dock
```

Or use a release tarball from [Releases](https://github.com/xhhcn/frost/releases):

```bash
tar xzf frost-1.0.tar.gz && cd frost-1.0 && bash install.sh
```

After applying, **log out and back in once**. `plasma-apply-lookandfeel` only carries a whitelist of settings; a login hook fills in the rest.

Nothing needs root and nothing is compiled.

## Roll back

```bash
bash RESTORE.sh                   # back to Breeze Dark, keeps Frost's files
bash frost/uninstall-frost.sh     # remove Frost entirely
```

## Check the state

```bash
bash frost/check-frost.sh         # read-only; prints every setting Frost owns
```

## Optional components

The theme installs and works without these; it degrades in the listed ways, and the installer warns about anything missing.

| Component | Where | Without it |
|---|---|---|
| `fluent-icon-theme` | AUR | Icons fall back to Breeze; two menu-category icons don't exist there and render blank |
| `papirus-icon-theme` | extra | Loses one inheritance fallback |
| Darkly | build `Bali10050/Lightly` into `~/.local` | Widget style and window decorations fall back to Breeze — no rounded corners, shadows or translucent menus. Panel glass, colours and time-of-day switching are unaffected |

## How it's built

`build-theme.py` is the single source of truth. Change a design variable at the top, re-run it, and the whole tree — SVGs, colour schemes, layout script, metadata — is regenerated. Four gates run on every build:

- **Source self-check** (AST): duplicate dict keys, dead constants, module visibility, cross-file constants
- **Output structure**: JS comment boundaries and cross-references, SVG XML and id references, QML balance and imports, JSON validity
- **Contrast**: 5 colour schemes × every colour group × 8 foreground keys × 2 backgrounds, plus 30 Konsole sections
- **Manifest**: the package must contain every required path before it is written

## Licence

Code and Plasma packages are **GPL-2.0-or-later**; the wallpapers are **CC0-1.0**. Full texts and the per-component breakdown are in [`frost/licenses/LICENSE`](frost/licenses/LICENSE).

One component is **not** self-authored, and is labelled as such: `kwin-effects/frost_minimize` is a derivative of KWin's own `squash` effect (© Vlad Zahorodnii, GPL-2.0-or-later) with window elevation added.

## Status

Tested on one machine: ThinkPad X1 Carbon Gen 9, Arch Linux, Plasma 6.7.3, Wayland, single 1920×1200 display.

Two things are known and open:

- The **day** scene is bright enough that popup body text drops below 4.5:1 over part of it, and the taskbar indicator sits just under its 3:1 target in the worst case. Both trace to the same cause — the day wallpaper's lighting — and fixing it means repainting that scene rather than changing any value.
- **Non-pinned** windows have no persistent order across a plasmashell restart. This is upstream behaviour: the task manager's config schema has no key that stores it, so pinning is the only way to fix a position. Breeze behaves the same way.
