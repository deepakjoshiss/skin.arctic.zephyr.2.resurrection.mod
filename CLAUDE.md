# VinELEC — Kodi skin

`skin.vinelec`, a Kodi 21 (Omega) skin. It began as a fork of **Arctic Zephyr 2
Resurrection Mod** (heppen → jurialmunkey → pkscout → DenDyGH) and has diverged
since — notably the view system, the home screen, the OSD and the weather panel.
`README.md` is still upstream's text and describes the *parent* project, not this
one; trust `addon.xml` and this file instead.

There is no build step, no test suite and no compiler. A skin is ~46k lines of
declarative XML that Kodi interprets at runtime, and **Kodi fails silently**: a
misspelled include, an undefined `$VAR`, a missing colour or texture produces no
error — the control simply does not draw. The two tools below exist to close that
gap. Use them; do not rely on reading the XML and hoping.

## This repo is the live skin

It sits inside Kodi's addons directory, so editing a file here changes the running
UI as soon as the skin reloads. There is nothing between your edit and the user's
screen. A broken commit breaks their TV.

## The loop

```bash
python3 tools/lint.py         # static checks — run after every XML edit
python3 tools/kodi.py reload  # apply to the running Kodi, report skin errors
python3 tools/kodi.py shot    # screenshot -> .dev/screenshots/*.png, then read it
```

`lint.py` resolves every include, `$VAR`, `$CONST`, font, colour, texture and
`$LOCALIZE` id against its definition and reports what does not exist. The repo
has 42 pre-existing findings recorded in `tools/lint-baseline.txt`; those are
suppressed so that **anything the linter prints is something you just broke**.
Exit code 1 means a regression. Use `--all` to see the baselined ones too, and
`--update-baseline` only when deliberately accepting new debt.

`kodi.py` talks to the running Kodi over JSON-RPC on `127.0.0.1:9090` (enabled by
default — Settings → Services → Control → "Allow programs on this system to
control Kodi"; no web server or password needed). Other subcommands: `check`
(is Kodi up, which skin, which window), `go <window>` to navigate to the screen
you changed, `errors` / `log` for the Kodi log, `rpc` as a raw escape hatch.

Because this is a *visual* project, finish by looking at a screenshot. `reload`
distinguishes real skin-load failures (exit 1) from the ambient weather/scraper/
shortcut errors that appear on every reload and mean nothing.

## Layout

| Path | What |
| --- | --- |
| `1080i/*.xml` | All skin XML. The only resolution; everything is 1920×1080 coordinates. |
| `addon.xml` | Addon id, version, dependencies. Bump `version` when releasing. |
| `colors/*.xml` | Colour palettes. `defaults.xml` is the base; the others are user-selectable themes. |
| `fonts/` | `.ttf` files. `fonts/lyrics/` holds the karaoke display faces. |
| `media/` | Textures. `Textures.xbt` / `Square.xbt` are *compiled bundles* (1352 entries) — loose files under `media/` and the bundles are both searched. |
| `themes/square/` | Alternate texture set, swapped in via skin setting. |
| `shortcuts/` | `script.skinshortcuts` config: menu definitions, `overrides.xml`, `skinviewtypes.json`. |
| `language/` | `strings.po` per locale. Skin strings are ids **31000–31999**; anything else is a Kodi core string. |
| `extras/` | Backgrounds, icons and playlists offered to the user in skin settings. |
| `lib/*.py` | Small Python helper invoked as `RunScript(skin.vinelec,<arg>=true)`. Handles `generatefonts`, `gradient`, `monochrome`, `reload`. |
| `tools/` | The lint and Kodi-driver scripts. |

### File naming in `1080i/`

- `<WindowName>.xml` — a Kodi built-in window (`Home.xml`, `MyVideoNav.xml`,
  `DialogVideoInfo.xml`). The filename is fixed by Kodi; you cannot rename these.
- `Custom_<id>_<Name>.xml` — a skin-defined window, opened with
  `ActivateWindow(<id>)`. Ids here run 1113–1190. Pick an unused one for a new
  window and keep the name in the filename.
- `Includes_<Area>.xml` — reusable include library for one area (`Includes_OSD`,
  `Includes_Home`, `Includes_Weather`).
- `Includes_View_5<n>_<Style>.xml` — one media view style each.
- `Constants_Main.xml` — layout constants (`view_pad`, `item_list_height`, …).
  Prefer adding a constant here over hard-coding a magic number.
- `Includes.xml` — the manifest. **A new `Includes_*.xml` file is invisible until
  you add `<include file="..."/>` to it.** This is the single most common reason
  new markup "does nothing".

### Generated — never edit

`1080i/script-skinshortcuts-includes.xml`, `script-skinvariables-includes.xml`
and `script-skinviewtypes-includes.xml` are written at runtime by the helper
add-ons. The first and third are gitignored; `script-skinvariables-includes.xml`
is currently still tracked, which is an inconsistency — do not hand-edit it
either, and expect it to show up dirty. Edit their *sources* in `shortcuts/`
(`skinvariables.xml`, `skinviewtypes.json`, the `*.DATA.xml` menus). They still
define real includes and variables, so the linter reads them.

## Skin XML in one screen

```xml
<include name="Foo">…</include>          <!-- define -->
<include>Foo</include>                    <!-- use -->
<include content="Foo">                   <!-- use, with params -->
    <param name="height" value="80"/>
</include>
$PARAM[height]                            <!-- read a param -->

<variable name="Bar"><value condition="…">x</value></variable>
$VAR[Bar]                                 <!-- conditional value -->
<constant name="view_pad">80</constant>
$CONST[view_pad]                          <!-- compile-time number -->

$INFO[ListItem.Title]                     <!-- runtime data from Kodi -->
$LOCALIZE[31042]                          <!-- translated string -->
```

Colours are referenced by name (`panel_fg_100`) and resolve from `colors/`, or
literal `AARRGGBB`. Fonts are referenced by name and must exist in a `<fontset>`
— usually `Font.xml`, but the lyrics faces are declared inline in
`Includes_VideoLyrics.xml`. Texture paths are relative to `media/` and are
matched case-insensitively.

## The view system

`shortcuts/skinviewtypes.json` maps numeric view ids (50 = List, 51 = Poster
Wall, 52 = Poster Showcase, …) to labels, and `rules` picks which views are
offered per content type (movies, tvshows, artists, files, …). `script.skinvariables`
turns that into the generated includes at runtime; the actual layouts live in
`Includes_View_5*.xml`, with `Includes_Views_Fallbacks.xml` catching the rest.
Adding a view means touching all three: the json, a layout include, and
`Includes.xml`.

## Dependencies

Declared in `addon.xml` and assumed present: `script.skinshortcuts` (menus),
`script.skinhelper`, `script.skinvariables` (view generation),
`plugin.video.themoviedb.helper` (artwork, TMDb info, blur), plus the
`resource.images.*` icon packs. Missing dependencies also fail quietly.

## Conventions

- Match the surrounding indentation (4 spaces) and the existing tag order.
- Give non-obvious controls a `<description>`; several id-only controls exist and
  are hard to place without one.
- Reuse an include rather than copy-pasting a control block — `Includes_Object.xml`
  and `Includes_Defs.xml` already hold most primitives.
- Numbers that describe layout belong in `Constants_Main.xml`.
- Never edit the generated includes; never rename a Kodi built-in window file.
- Run `tools/lint.py` before finishing, and screenshot anything visual.
