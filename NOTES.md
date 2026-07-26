# Notes for agents

Read this alongside `CLAUDE.md` before editing. `CLAUDE.md` describes how the
skin *works*. This file is the memory: what we learned the hard way, what we
have built on top of upstream, and what we have changed recently.

All three sections are hand-written. Keeping them current is part of finishing a
task — see "Keep `NOTES.md` current" in `CLAUDE.md`.

- **Invariants** — live constraints, present tense. Edited in place; delete one
  when it stops being true. Read this before your first edit.
- **Background** — the work *we* have done on top of upstream. Rarely changes.
- **Log** — what we have changed, newest first. Curated, one entry per
  meaningful change; use `git log` for per-commit detail.

## Invariants

- **skinshortcuts v3 is a one-way door.** 3.0.2 cannot rebuild the v2 storage
  format, so checking out anything before `c1751cf` renders the skin black.
  There is no rollback — fix forward.

- **The live menu is not in this repo.** `shortcuts/*.DATA.xml` are stale
  upstream defaults, and they still hardcode personal Jellyfin `ParentId`s.
  The running configuration lives in
  `userdata/addon_data/script.skinshortcuts`. Read that before assuming
  anything about what the home screen contains.

- **Plugin URLs in `menus.xml` must not be quoted.** v3 derives the `path`
  property by string-stripping the action, so a leading `"` makes Kodi parse an
  empty addon id and segfault in `CPluginDirectory::StartScript`. The quotes
  are never needed: the URLs carry `%252C`-encoded commas, not raw ones.

- **Drive the running Kodi one input at a time**, confirming the window between
  each `Input.*` call. This is the user's live media centre, not a test
  harness — a wrong keypress navigates their TV.

- **`tools/lint-baseline.txt` suppresses the known-bad findings.** Anything the
  linter prints is debt you just created; exit code 1 is a regression. Only
  `--update-baseline` when deliberately accepting new debt.

- **Duplicate `$VAR`/`$EXP` definitions resolve first-registration-wins, and
  `Includes.xml`'s own inline definitions register before any `<include file>`
  recursion.** Measured on a running Kodi 21, four reloads:

  | Case | Winner |
  | --- | --- |
  | file included at `Includes.xml:7` vs file included at `:26` | the **earlier file** |
  | file included at `:7` vs a `<variable>` inline in `Includes.xml` (at `:344` **and** at `:4`) | the **inline** one, either way |
  | `<expression>`, file vs file | same rule as variables |

  So you **can** shadow a definition that lives in its own `Includes_*.xml` by
  including your file earlier — this is how
  `Includes_Images_Background_FakeBlur.xml` legitimately overrides
  `Image_Background_Blur` from `Includes.xml:24` vs `:25`. You **cannot** shadow
  anything defined inline in `Includes.xml` itself, which includes the 19
  `Path_*` variables (`:132-281`) and `ColorOverlay` (`:78`) — those can only be
  edited in place or moved out. `<include name>` shadowing is **untested**; probe
  it before relying on it.

- **`condition=` on `<include file>` is honoured**, evaluated at *skin load* — so
  flipping the underlying skin setting needs a `tools/kodi.py reload` before it
  takes effect, which makes it unsuitable for a live settings-menu toggle.

- **`Skin.HasSetting(TMDbHelper.Service)` does NOT control TMDbHelper's service.**
  The addon registers `resources/service.py` as `point="xbmc.service"`, so Kodi
  runs `ServiceMonitor().run()` whenever the addon is installed and enabled. That
  unconditionally constructs `PlayerMonitor()`, starts the cron and image threads,
  sets `TMDbHelper.ServiceStarted` and begins polling. The skin setting is only
  consulted inside `imgmon.py`, to gate crop/blur/desaturate/colors.

  So a fully de-TMDb'd skin still produced `api.themoviedb.org` traffic from
  `monitor/player.py` on playback, plus a cron thread visible as
  `GetDirectory - Error getting .../log_library/` every ten minutes. **No skin
  change can stop this** — the addon must be disabled or uninstalled. The skin's
  only lever was the `addon.xml` `<import>`, since Kodi refuses to disable an
  addon a running skin requires; that import is now gone.

  Corollary: `TMDbHelper.ServiceStarted` reading `True` is **live evidence the
  service is running**, not a stale leftover. Do not explain it away.

- **`Startup.xml` runs only at Kodi launch, never on `tools/kodi.py reload`.**
  Confirmed from the log: one `Loading skin file: Startup.xml` at launch and none
  across seven reloads. So nothing in it — the `TMDbHelper.*` service bools, the
  `SkinInit` defaults block — is exercised by the normal dev loop, and a change
  there will look like it did nothing. To re-run it without restarting Kodi:

  ```bash
  python3 tools/kodi.py rpc GUI.ActivateWindow '{"window":"startup"}'
  ```

  It ends in `ReplaceWindow($INFO[System.StartupWindow])`, so it lands back on Home
  (or window 1113 if `StartupPlaylist` is set). Its onloads are idempotent. Confirm
  it actually ran by watching the `Startup.xml` count in the log go up.

- **`1080i/schema.xsd` is broken; ignore IDE XML errors on skin files.** It cannot
  validate the repo's own files: `xmllint --schema` rejects
  `Includes_Expressions.xml:4` and `Includes_Views_Fallbacks.xml:4` because its
  `xs:sequence` demands a `<default>` before any `<expression>`, and it rejects
  the `file=` attribute on `<include>` — Kodi's core include mechanism, used on
  every line of the `Includes.xml` manifest. Real Kodi accepts all of it. Trust
  `tools/lint.py`, not the editor.

- **TMDbHelper's declared and installed versions disagree.** `addon.xml`
  imports `plugin.video.themoviedb.helper` 5.5.11; the installed copy is
  6.15.6. Kodi treats the import as a floor so it resolves, but the ~80
  `TMDbHelper.*` window properties the skin reads were written against 5.x. If
  one reads empty for no visible reason, suspect a renamed property before
  suspecting the XML.

## Background

`skin.vinelec` began as a fork of **Arctic Zephyr 2 Resurrection Mod**
(heppen → jurialmunkey → pkscout → DenDyGH). The `origin` remote still points at
the fork's original name and `README.md` is still upstream's text — it describes
the *parent* project, not this one. Trust `addon.xml`, `CLAUDE.md` and this file
instead.

Work happens on `dj-dev`. Upstream `main` is merged in periodically rather than
rebased onto, so the history has merge commits by design, and upstream's own
churn (version bumps, translations, texture updates, its ratings and up-next
work) is interleaved with ours. **What follows is only our work** — the 27
commits on `dj-dev` that upstream does not have. When something below conflicts
with an upstream README or an old upstream commit, this file is right.

- **The view system was rebuilt.** This is the largest divergence and the reason
  `Includes_View_5*.xml`, `shortcuts/skinviewtypes.json` and
  `script.skinvariables` are wired the way `CLAUDE.md` describes. Along with it:
  per-content-type view offerings were re-picked (video content defaults to
  Banner Wall, not List Square), default-view aspect ratios were corrected, and
  library content was allowed more view choices.

- **The home screen and main menu were reworked** — layout, menu width, fonts
  (including Google fonts), the select-box treatment, the progress line, and a
  new set of default widgets.

- **Search was added**: a dedicated search window, an "all sources" search,
  breadcrumbs, and the keyboard handling to go with it.

- **Two windows exist that upstream does not have** — a Media Info window and a
  System Info window.

- **The OSD gained an action menu and OSD actions**, plus popup behaviour and
  layout fixes.

- **The weather panel gained an AQI display**, and later moved off the synthetic
  bold weather font.

- **IMDb ranking display** was added to the ratings area.

- **Jellyfin/JellyCon is the primary media source.** This is why the home menu
  and widgets are full of `plugin://plugin.video.jellycon` paths, and why a
  restart-Jellyfin helper script exists.

- **Settings were reorganised** and an XML schema added for them.

Two more recent changes matter because they affect *how you work in this repo*
rather than how the skin looks — the **skinshortcuts v3 migration** and the
**agent tooling**. Both are in the Log below.

## Log

Newest first. Curated — one entry per meaningful change, not per commit.

### 2026-07-26 — Correction: the two entries below overclaimed; dropped the `addon.xml` import

Deepak checked the log and found live TMDb traffic *after* all of the work below:

```
2026-07-26 14:03:10  monitor/player.py
  ConnectionError: HTTPSConnectionPool(host='api.themoviedb.org', port=443)
  ... /3/movie ...  /3/search ...
```

The two entries below claim "the skin now issues no TMDb requests" and call
`Skin.Reset(TMDbHelper.Service)` "the actual off-switch". **Both are wrong as
stated.** The accurate claim is narrower: *the skin's own XML* makes no TMDb
requests. TMDbHelper's service runs on its own and no skin setting stops it — see
the new invariant above for the mechanism.

Worth recording how the mistake was made, because it was avoidable. The service
being off was verified by two *proxies* — `Skin.HasSetting(TMDbHelper.Service)`
reading empty and `Monitor.TMDb_ID` going from `93740` to empty — rather than by
the thing actually claimed, which is network traffic. And the one piece of
evidence that contradicted the conclusion, `ServiceStarted` still reading `True`,
was written off in `docs/tmdbhelper.md` as "a stale property nothing clears"
instead of being chased. It was the service announcing itself.

The fix available skin-side: `addon.xml` no longer `<import>`s
`plugin.video.themoviedb.helper`. That does not stop the service by itself, but it
was what *prevented* stopping it — Kodi will not disable an addon that the running
skin declares as a hard dependency. Disabling or uninstalling the addon is now
possible and is the step that actually silences the traffic.

Before disabling it, note a configured video **source** is a TMDbHelper directory
(`plugin://...?info=dir_movie`), which lives in Kodi's sources rather than the
skin and will break. The skin's own leftovers (`System.HasAddon`, `InstallAddon`,
`Addon.OpenSettings`, `System.AddonVersion`) all degrade cleanly.

### 2026-07-26 — Replaced the TMDb `RunScript` actions

Of the 20 `RunScript(plugin.video.themoviedb.helper,...)` calls, only **two were
the action itself** rather than a decoration, and both had to be replaced rather
than dropped or they would have become visible buttons that do nothing:

- **Play (3101)** — was `RunScript(...,close_dialog=1190,playmedia=...)`. Now
  `PlayMedia(...)` followed by `Dialog.Close(all,true)`. **Order is the whole
  point:** closing first discards the ListItem context, so `$ESCINFO[...]` would
  resolve empty and `PlayMedia` would silently play nothing. Same act-first,
  close-last idiom as the trailer button (8899) directly below it, which is the
  in-repo proof the ordering works.
- **Browse (3102)** — was six calls (`call_update=` inside MyVideoNav,
  `call_path=` outside). Now one `ActivateWindow(Videos,<path>,return)` per case:
  activating the window closes the dialog itself, so the split and the ordering
  hazard both disappear, and `$INFO[...]` is still evaluated while the ListItem is
  valid.

Search (8115) got `ActivateWindow(1138)` — everything else about it was already
local. It is invisible in this setup regardless, needing `tmdb_id`/`IMDbNumber`
that JellyCon never sets; left hidden rather than widened, since making a hidden
button appear is a feature, not a fix.

The rest were removed. Several were already unreachable, but were removed anyway
wherever their dormancy depended on **external** state rather than ours — the same
rule applied to the content paths. `Defs_InfoList_OnClick`'s three were the notable
case: unlike the widget-spotlight equivalents they were *not* gated on a TMDb path,
only on DBID/DBType, so any future Jellyfin-backed row added to the info dialog
would have started invoking TMDbHelper again.

**Net result: no live code path in the skin invokes TMDbHelper.** What remains is
the `addon.xml` import, the settings-UI rows that install/open/version-check it,
three inert `shortcuts/templates.xml` search templates that no live shortcut names,
and one `RunScript` inside an XML comment (`Includes_OSD.xml:1504`).

**Not verified: the Play button press.** The code is correct by construction and
the button renders, but the info dialog cannot be driven interactively here — the
YouTube row fires four content queries and each raises a `key.requirement` dialog
that steals focus. Note this is *not* suppressed by the page-2 guard: Kodi loads
containers whose `<visible>` is false, which is precisely what makes that guard
work. Setting `DisableInfoListYouTube` (Custom_1119) would stop the noise and make
the dialog testable.

### 2026-07-26 — Removed every TMDb content path; fixed the missing genre

The skin now issues **no TMDb requests**. Turning the service off (previous entry)
only stopped the background property monitor; a `<content>` of
`plugin://plugin.video.themoviedb.helper/...` invokes the addon whenever that
container loads, which is a live request regardless. Those are all gone.

The 19 `Path_*` variables were extracted verbatim from `Includes.xml` into
`1080i/Includes_Paths.xml` first, because they were defined **inline** and Kodi
registers inline definitions ahead of every `<include file>` — so they could not
be shadowed, only edited in place, in a range upstream touches a few times a year.
Owning the file turns a recurring conflict into a single delete/modify one. The
move was verified byte-exact against `HEAD` before any value changed.

Variable *names* are all kept (≈20 controls reference them); only values changed —
`Null.xsp` where the variable feeds a `<content>` directly, empty where it is a URL
fragment its caller concatenates.

Four paths were neutralised explicitly even though they are currently dormant,
because they are dormant **only for reasons on our own JellyCon to-do list**: the
`DialogPersonInfo` lists key off `ListItem.UniqueID(tmdb)` (empty only because
JellyCon sets no provider IDs) and `Def_Cast_List` keys off `ListItem.Cast` (empty
only because `include_people` is off). Adding either — both planned — would have
silently resumed TMDb traffic. Two more (`Custom_1193`, the director rows) were
written out rather than left relying on `$VAR[name,prefix]` collapsing when empty,
which is unverified Kodi behaviour and would otherwise have left a bare
`?info=details&tmdb_type=` stub that still invokes the addon.

**Genre had stopped rendering everywhere except the Showcase view.**
`Object_Info_Line` read `TMDbHelper.ListItem.base_genre` unless `$PARAM[fullgenre]`
was true — it defaults false and only `Includes_View_52_Showcase.xml:386` overrides
it — and `Flix_Object_Info_Line` had no local fallback at all. Both now use
`ListItem.Genre`, which JellyCon supplies. Confirmed on screen before and after.

Verified live on a real JellyCon movie list, not just by lint: genre back in the
info line, ratings row showing `IMDb 6.5` + tomato `83%` with no blank band, info
dialog page 1 complete, and page 2 correctly *gone* — `Control.IsVisible(4000)`
and `Container(9000).HasNext` both empty, focus staying on the button row instead
of landing on a blank screen.

Two things seen while verifying that are **not** ours: the info dialog's YouTube
row raises a `key.requirement` dialog because `plugin.video.youtube` has no API key
(its content is YouTube title searches, nothing to do with TMDb), and the 67
remaining `PluginName` comparisons live in the **generated**
`script-skinviewtypes-includes.xml`, which CLAUDE.md forbids editing and which are
view-selection tests rather than requests.

### 2026-07-26 — Stopped the skin connecting to TMDb; empty-state guards; lint gains `$EXP`

`Startup.xml` now does `Skin.Reset(TMDbHelper.Service)` instead of `SetBool`. That
setting is what started TMDbHelper's background monitor, so this is the actual
off-switch for the skin's TMDb traffic — verified by
`TMDbHelper.ListItem.Monitor.TMDb_ID` going from `93740` to empty. It had to be an
explicit `Reset`, not a deleted line, because the setting persists in userdata.
`DisableExtendedProperties` is kept set as belt and braces. Home renders unchanged.
The remaining `TMDbHelper.*` XML is now inert and is being removed phase by phase.

Also fixed `SkinInit`, which nothing ever set — so `Startup.xml:20-56` re-asserted
37 skin settings (including a `RunScript`) on every Kodi launch, and any settings
change came back on restart. The fix was behaviourally inert: those keys were
rewritten each launch, so the saved value already equalled the forced value.

Added empty-state guards ahead of emptying the TMDb content paths, because
"renders empty" and "renders broken" are different outcomes. The interesting part
was that the lists were never the problem — `Info_Widget_Poster`
(`Includes_Info.xml:54`) already self-collapses. What leaked was the
`common/osd-dim.png` in windows 1142/1143, which sits *outside* the group holding
the list, so a dim strip stayed over playing video. Also gated
`DialogVideoInfo`'s `group id="4000"` (page 2 always claimed content, so the
down-chevron always drew) and `Object_Ratings_Content` (fixed 32px, no `<visible>`,
leaving a blank band at five-plus call sites).

Two tooling findings worth keeping:

- **`tools/lint.py` never validated `$EXP[]`.** Added; it immediately justified
  itself — the now-deleted `Path_Param_Type` referenced `$EXP[Exp_IsPersonInfo]`,
  which was never defined anywhere. An undefined expression makes its condition
  never true, so the control silently never draws: precisely what this linter is
  for. Verified the new rule fires by deliberately breaking a reference.
- **`$EXP[RatingsVisiblity]` is useless as a gate.** JellyCon sets both `Rating`
  and `UserRating` on every item, so it is always true. Gate on the specific
  sources instead. See `docs/jellycon.md`.

### 2026-07-26 — Integration reference docs, ahead of dropping TMDbHelper

Added [docs/tmdbhelper.md](docs/tmdbhelper.md) and
[docs/jellycon.md](docs/jellycon.md), linked from `CLAUDE.md`. Groundwork for
removing the `plugin.video.themoviedb.helper` dependency so Jellyfin/JellyCon
becomes the single metadata source.

Investigating first changed the plan substantially. The premise was only half
true: `Startup.xml:10` sets `TMDbHelper.DisableExtendedProperties` on every load,
so the ~80 detail properties are already empty everywhere except inside
DialogVideoInfo — most of the ~40 TMDb definitions are already no-ops, and the
work is mostly deleting dead code. Also found `Container(99950)` is a phantom (50
reads, no such control), `Object_Info_Ratings` is unreachable (all its call sites
sit inside an XML comment), and the ratings row already shows Jellyfin's
community + critic values, just under the wrong logos.

Two unrelated live defects surfaced and are recorded in the docs: `SkinInit` was
never set, so `Startup.xml:20-56` re-asserted 37 settings on every Kodi launch and
any ratings toggle came back off after a restart (fixed — see the next entry); and
`Path_VideoInfo_OnlineStudio` (`Includes.xml:258`) has an unconditional value that
emits an unfiltered TMDb discover query, so the "From \<studio\>" row shows
unrelated titles.

The docs exist separately from this file because they are reference material read
on demand, not constraints read before every edit. Kept as two files, split by
integration, so the JellyCon one can outlive the TMDb removal.

### 2026-07-26 — Agent notes file

Added this file and pointed `CLAUDE.md` at it. The reasoning behind past changes
existed only in commit bodies, which no agent reads before editing, and in a
per-session memory no other tool can see. The Invariants above were the
immediate motivation: each had already cost a segfault, a black screen or a
wasted session to learn.

Considered generating the Log mechanically from `git log` via a `post-commit`
hook, and rejected it — a script can only project commit metadata, which
reproduces `git log` instead of summarising it, and the output was dominated by
noise (`fix skinshortcuts`, `Normalize line endings`). Maintenance is an
instruction in `CLAUDE.md` instead. The tradeoff is real: instructions are
advisory where a hook was enforcement. If this file starts going stale, the next
step is a reminder hook that nudges when XML changed but `NOTES.md` did not —
without mechanising the prose.

Also corrected `CLAUDE.md`, which claimed 42 baselined lint findings; the actual
count is 35.

### 2026-07-26 — Ported the live menu to skinshortcuts v3

The v3 migration rebuilt the home menu from `shortcuts/menus.xml`, which had
been seeded from the repo's stale `*.DATA.xml` defaults. Those were not what was
actually running — the live menu lives in userdata and differed in several ways
(a different Jellyfin mode, a different Media `ParentId`, a `RunScript` search)
— and all three Jellyfin home widgets were lost entirely, because v3 does not
read v2's widget storage.

`tools/port-v2-menu-to-v3.py` is the converter, kept so the mapping stays
reproducible rather than hand-transcribed. Three things are normalised on the
way through: plugin URLs are unquoted (see the segfault invariant above),
`image://` thumbs pointing at absolute local addon paths become
`special://home/addons/...`, and `$LOCALIZE[32032]` / `UnknownUser.png` — which
resolve to nothing in this skin — become `$LOCALIZE[341]` / `DefaultUser.png`.

Verified: 24 menus load, skin reloads with no errors, lint clean, Home shows all
12 items plus the three JellyCon widgets populated. See `a2a266e`, `91d7bce`,
`c1751cf`.

### 2026-07-26 — Agent tooling: lint and a Kodi driver

Kodi fails silently on skin mistakes — a misspelled include, an undefined
`$VAR`, a missing colour or texture draws nothing and logs nothing — so there was
no way to tell a broken edit from a working one without hunting through the UI
by hand.

`tools/lint.py` resolves every include, `$VAR`, `$CONST`, font, colour, texture
and `$LOCALIZE` id against its definition. `tools/kodi.py` drives the running
Kodi over JSON-RPC (reload, navigate, screenshot, read the log) and separates
real skin-load failures from the ambient weather/scraper/shortcut errors that
appear on every reload and mean nothing. See `d33499b`.

### 2026-07-26 — Weather font and video view types

`font_weather_bold` now uses `RobotoCondensed-Regular` without the synthetic
bold style. Video content offers List / Banner Wall / List Square / Flix
Landscape, defaulting to Banner Wall instead of List Square. See `67600b0`.
