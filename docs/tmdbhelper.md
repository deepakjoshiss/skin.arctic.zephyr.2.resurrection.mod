# TMDbHelper in skin.vinelec

Reference for `plugin.video.themoviedb.helper` (TMDbHelper) as this skin uses it,
written while planning its removal. Companion to [jellycon.md](jellycon.md),
which covers what Jellyfin can supply instead.

Declared at `addon.xml:8` as a hard `<import>`. Inherited from upstream Arctic
Zephyr 2 Resurrection Mod — none of this integration is ours.

> **Headline: the skin no longer connects to TMDb.** `Startup.xml` now does
> `Skin.Reset(TMDbHelper.Service)`, which stops TMDbHelper's background monitor —
> the thing that watched the focused list item, looked it up against TMDb, and
> populated every `TMDbHelper.ListItem.*` / `.Player.*` property. What remains in
> the XML is inert code being removed phase by phase.
>
> Scope note: we make **no changes to TMDbHelper itself** and do not accommodate
> its behaviour. The goal is only that the skin never reaches out to TMDb.

## Verified live state

Queried against the running Kodi (`tools/kodi.py rpc XBMC.GetInfoLabels`).

| Property | Before (service on) | After `Skin.Reset(TMDbHelper.Service)` |
| --- | --- | --- |
| `Skin.HasSetting(TMDbHelper.Service)` | `True` | *(empty)* |
| `TMDbHelper.ListItem.Monitor.TMDb_ID` | `93740` | *(empty)* |
| `TMDbHelper.ListItem.Title` / `.Plot` / `.IMDb_Rating` / `.Trailer` / `.BlurImage` / `.Top250` | *(empty)* | *(empty)* |
| `TMDbHelper.TraktIsAuth` | *(empty)* | *(empty)* |

`Monitor.TMDb_ID` going from a real id to empty is the proof the *ListItem*
lookups stopped. The detail properties were already empty before, because
`Startup.xml` also sets `TMDbHelper.DisableExtendedProperties` — kept deliberately
as belt and braces.

**`TMDbHelper.ServiceStarted` still reads `True`, and that is not stale.** The
addon's service sets it on every run. Which leads to the important correction
below.

## The skin cannot switch the addon's service off

`Skin.HasSetting(TMDbHelper.Service)` does **not** control whether TMDbHelper's
service runs. Reading the addon's own source: `resources/service.py` is registered
as `point="xbmc.service"`, so Kodi starts `ServiceMonitor().run()` whenever the
addon is installed and enabled. That method unconditionally constructs
`PlayerMonitor()`, starts the cron and image threads, sets `ServiceStarted`, and
begins polling. The skin setting is only consulted *inside* `imgmon.py` to gate
specific image-processing behaviours (crop/blur/desaturate/colors).

So with the skin fully de-TMDb'd, this still happened on playback:

```
monitor/player.py
ConnectionError: HTTPSConnectionPool(host='api.themoviedb.org', port=443)
  ... /3/movie ... /3/search
```

The service's player monitor looks up whatever is playing. There is also a cron
thread, visible in the log as `GetDirectory - Error getting .../log_library/` and
`.../timer_report/` every ten minutes.

**Turning that off is not a skin change.** The addon has to be disabled or
uninstalled in Kodi. The skin's only lever was `addon.xml`, which declared the
addon a hard `<import>` — Kodi will not let you disable an addon a running skin
requires. That import has now been removed, which unblocks disabling it.

Two consequences before disabling:

- A configured video **source** is a TMDbHelper directory (see *Still live*
  below). Disabling the addon breaks that source.
- The skin's remaining references (`System.HasAddon`, `InstallAddon`,
  `Addon.OpenSettings`, `System.AddonVersion` in `SkinSettings.xml` and
  `Custom_1119`) all degrade cleanly when the addon is absent — they are guarded
  or are install prompts.

Two things this means in practice: the service setting **persists in userdata**, so
turning it off required an explicit `Skin.Reset` rather than just deleting the
`SetBool` line; and `Startup.xml` runs **only at Kodi launch**, so use
`kodi.py rpc GUI.ActivateWindow '{"window":"startup"}'` to apply it without a
restart (see `NOTES.md`).

## Integration surface

Three mechanisms, ~312 references in `1080i/*.xml`.

**1. Window properties.** The TMDbHelper service watches the focused list item and
writes ~80 distinct `TMDbHelper.*` properties onto the Home window. The skin
selects *which* container the service watches by writing
`TMDbHelper.WidgetContainer` — see *Traps*.

**2. `plugin://` container paths.** 19 `Path_*` variables in `Includes.xml:132-281`
plus 5 inline paths, feeding cast, crew, similar, recommendations, collection,
discover-by-genre/year/studio, poster and fanart galleries, OSD cast/episodes, and
the person-credit lists in `Includes_DialogVideoInfo.xml:431-464`.

**3. `RunScript(plugin.video.themoviedb.helper,...)`** — 17 sites using
`add_path`, `add_query`, `call_auto`, `call_update`, `call_path`, `call_id`,
`close_dialog`, `playmedia`, `sync_trakt`.

### The indirection layer

~95% of references sit inside **~40 named definitions** across six files. That is
what makes the dependency removable without touching consumers:

| File | Holds |
| --- | --- |
| `Includes.xml:132-281` | the 19 `Path_*` variables; `ColorOverlay` at `:78` |
| `Includes_Labels.xml` | 11 variables (plot, tagline, title, biography, next-aired, studio, director, Oscars) |
| `Includes_Images.xml` | 8 variables (clearlogo crop, blur, Rotten Tomatoes badges) |
| `Includes_Expressions.xml` | 5 expressions (`Exp_HasClearlogo`, `RatingsVisiblity`, `Exp_Ratings_*`) |
| `Includes_Object.xml` | 7 includes, incl. `Object_Ratings_Content:2052` |
| `Includes_Defs.xml` | `Defs_InfoList_OnClick:254`, `Def_Cast_List:305` |

Only ~14 reads leak outside a named definition.

## Dead code inventory

| Item | Why dead |
| --- | --- |
| `Container(99950)` — 50 reads in `Includes_Object.xml` | **no control with that id exists anywhere in the skin** |
| `Object_Info_Ratings:2547`, `Object_Rating_Line_Label:1154` | every call site sits inside the XML comment at `Includes_Object.xml:2444-2542` |
| `Startup.xml:16-19` (`CustomRating.*`) | feeds only the above, so it has no visible effect |
| `Path_Param_Query:132`, `Path_Param_Type:144`, `Path_FromGenre:163`, `Path_FromYear:168` | zero consumers repo-wide |
| `Label_Splash` (`Includes_Labels.xml:4`) | zero consumers |
| `Includes_OSD.xml:1504` | inside a comment block opening at `:1492` |
| Window 1142 (OSD Cast) | `OSD.DisableCastDialog=True` live, and nothing else opens it |
| Window 1193 (VideoOSDInfo) | its only entry point is that commented block |
| Button 8151 (Trakt watchlist) | requires `TraktIsAuth`, which is empty |
| Button 8115 | requires `ListItem.Property(tmdb_id)` or `ListItem.IMDbNumber`; JellyCon sets neither |

## Still live

The short list worth actual attention:

- **A configured video *source* is a TMDbHelper directory.** Found while
  verifying: the "Movies" entry under the Videos window resolves to
  `plugin://plugin.video.themoviedb.helper/?info=dir_movie&tmdb_type=None`
  (40 items — Popular, etc.). This is in Kodi's sources, **not** in the skin, so
  no amount of skin work removes it and dropping the `addon.xml` import will
  leave a dead source behind. Decide separately whether to delete that source or
  keep TMDbHelper installed-but-undeclared.

- **DialogVideoInfo** — `EnableExtendedProperties` is on inside it, so cast, crew,
  similar, recommendations, collection, poster/fanart galleries and the person
  pages (`DialogPersonInfo`, 100% TMDb) all really work here.
- **`Path_VideoInfo_OnlineStudio`** — actively wrong, see *Defects*.
- **Window 1190** — an empty 13-line shell populated entirely by
  `call_auto=1190`. 17 `RunScript` sites route into it.
- **Play / Browse / Search buttons** (`Includes_Info.xml:147,148,160-166,180`) —
  the `RunScript` **is** the action, not a decoration.
- **`Monitor.TMDb_ID` / `Monitor.TMDb_Type`** — the only populated properties.

## Traps

**`TMDbHelper.WidgetContainer` is the skin's own state.** Despite the name, the
skin writes it (9 sites) and reads it (4 sites, all `Includes_Animations.xml:65-77`);
`Startup.xml:8` `UseLocalWidgetContainer` is what tells TMDbHelper to read it too.
A bulk `TMDbHelper.` grep-and-delete destroys home widget focus tracking. Renaming
it means touching the **generated** `script-skinshortcuts-includes.xml:3432`,
which `CLAUDE.md` forbids, plus its source `shortcuts/templates.xml:301`.

**`Container(99950).Property(top250)` → `ListItem.Top250` is the wrong fix.** It
looks like the obvious modernisation. JellyCon sets `setTop250(1)` to mean *is a
favourite* (`item_functions.py:515`), so every favourite would render `#1`. See
[jellycon.md](jellycon.md).

**`Timers.xml` is self-disabling — leave it alone.** Both auto-trailer timers gate
`<start>`, `<reset>`, `<stop>` and both `<onstart>` blocks on
`!String.IsEmpty(...TMDbHelper.ListItem.Trailer)`. Empty property ⇒ never starts.
Rewriting it to `ListItem.Trailer` would be actively harmful: JellyCon sets that
for every movie and series regardless of whether a trailer exists, and it resolves
to a `dialog.select`, so the timer would pop a selection dialog on the TV
repeatedly while idle. `trailer_delay` is also empty, so the elapsed comparison is
true almost immediately.

**`Includes_Animations.xml:65-77` is safe by accident.** Both positive and negated
forms of the `WidgetContainer == 5610` test exist, so an empty property means the
negated pair wins and a plain fade replaces the zoom. Delete one side only and you
get no animation, or a doubled one.

**Case variants defeat a naive grep.** `TMDbHelper` (466), `TMDb` (87),
`TMDBhCrop` (8), `TMDBHelper` (5), and one each of `TMDBh` / `TMDbH` /
`TMDbHelperSplash`. The `TMDBHelper` spelling appears at `Includes_Images.xml:123,129`,
`Includes_Expressions.xml:14,15` and `Includes_Topbar.xml:104`.

**Empty-state gaps.** `Custom_1143_OSD_Playlist.xml` and `Custom_1142_OSD_Cast.xml`
both have `defaultcontrol always="true"` on a container that collapses when empty,
and neither `Path_OSD_Episodes` nor `Path_OSD_Cast` has an unconditional fallback —
so they can render as a dim strip over live video with nothing focusable. 1143 is
reachable today with one keypress from the OSD (`Includes_OSD.xml:2462`).
`Includes_DialogVideoInfo.xml:70` (`group id="4000"`) has no `<visible>`, so the
info dialog always has a page 2 and always draws the down-chevron.
`Object_Ratings_Content` (`Includes_Object.xml:2072`) has a hard
`<height>32</height>` and no `<visible>`, leaving a 32px hole at the five-plus
call sites that don't wrap it in a gated group.

## Pre-existing defects found while planning

Neither is caused by TMDb removal.

**`SkinInit` was never set — fixed 2026-07-26.** Nothing anywhere did
`Skin.SetBool(SkinInit)`, so `!Skin.HasSetting(SkinInit)` was permanently true and
all 37 `SetBool`/`SetString` calls in `Startup.xml:20-56` re-fired **every time
`Startup.xml` ran — i.e. on every Kodi launch, not on skin reload** (see the
`Startup.xml` invariant in `NOTES.md`). Six are inverted `Ratings.*` flags
(`Skin.HasSetting(Ratings.X)` = *hidden*), so any rating enabled in the settings UI
came back off after a Kodi restart. The block also re-ran a
`RunScript(script.skinhelper,gradient=true,...)` every launch.

Closing it was behaviourally inert: `SetBool`/`SetString` rewrote those keys on
every launch, so the saved value always already equalled the forced value. Verified
by reading all 37 before and after — none moved. `Startup.xml:16-19` was always
correctly guarded with `String.IsEmpty(...)`; only the `SkinInit` block was broken.

**`Path_VideoInfo_OnlineStudio` has no `Null.xsp` fallback.** `Includes.xml:258` is
an **unconditional** final `<value>` emitting
`plugin://...?info=discover&...&with_companies=` with an empty company id, so the
"From \<studio\>" row on the info dialog shows unrelated popular titles under a
label sourced from the local `ListItem.Studio`. 9 of the 10
`Path_VideoInfo_Online*` variables guard to
`special://skin/extras/playlists/Null.xsp`; this one does not, and neither do
`Path_OSD_Cast:187` or `Path_OSD_Episodes:193`.

## Merge context

`Includes_Object.xml` is already **+721/−178** from `origin/main`, and
`Object_Ratings_Content` has structurally diverged: upstream rewrote it (5 params,
delegating body) and we hold the old one (16 params, inline body) — upstream's new
version *is* the comment block at `:2444-2542`. Upstream touched that range in Jan
and Mar 2026, so it conflicts on every upstream ratings commit regardless of what
we do.

By contrast the `Path_*` block (`Includes.xml:132-281`) and `ColorOverlay` (`:78`)
are **pristine upstream text**, as are `Includes_Expressions.xml`,
`Includes_Info.xml`, `Timers.xml`, `Custom_1190_TMDB_Info.xml`,
`Includes_DialogVideoInfo.xml` and `shortcuts/templates.xml`. Check with
`git diff origin/main HEAD -- <file>` and read the hunk headers before editing —
pristine regions are better shadowed than edited.
