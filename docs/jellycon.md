# Jellyfin / JellyCon as a metadata source

Reference for what the skin can actually read from Jellyfin, written while
planning TMDbHelper's removal. Companion to [tmdbhelper.md](tmdbhelper.md).

Line references are to `plugin.video.jellycon/resources/lib/`, verified 2026-07-26.

## Topology — this is the constraint everything else follows from

**The Jellyfin library is not in Kodi's native video library.** `MyVideos146.db`
has **0 movies, 0 tvshows, 0 episodes**. No sync addon is installed (no
`plugin.video.jellyfin`, no `script.jellyfin`); a stale orphaned
`userdata/Database/jellyfin.db` dated Sep 2024 is residue from one that was
removed.

Everything reaches Kodi through the `plugin.video.jellycon` plugin path, so
**only what JellyCon explicitly sets on each ListItem exists.** There is no
`videodb://`, no `VideoLibrary.*` JSON-RPC, and no Kodi-side sets, actors or
artwork tables. Any skin XML that reads `videodb://` resolves to nothing — which
is why, for example, the info dialog's NextUp
(`videodb://inprogresstvshows`) and Seasons (`videodb://tvshows/titles`) rows are
empty here even though they are not TMDb-dependent.

**The addon is a fork we maintain.** `id="plugin.video.jellycon"`,
`name="Jellyvin"`, `version="1.0.0+py3"`,
`provider-name="DJ | Jellyfin Contributors"`. It carries additions upstream
JellyCon does not have (a local IMDb-250 map, a RottenTomatoes property, a custom
search screen, a media-info dialog, intro skipper). So everything in *Deferred
fork work* below is reachable — it is our code.

## Measured on a real item

Everything below was confirmed live against `Ad Astra` in a JellyCon movie list
(231 items, `ListItem.DBType` = `movie`) rather than read from the source:

| Infolabel | Value | Note |
| --- | --- | --- |
| `ListItem.Rating(imdb)` | `6.5` | the **community** rating, filed under `imdb` |
| `ListItem.Rating` | `6.5` | same value, registered as default |
| `ListItem.Property(RottenTomatoes_Rating)` | `83` | critic rating = RT tomatometer |
| `ListItem.UserRating` | `83` | **the 0-100-in-a-1-10-field bug, live** |
| `ListItem.Genre` | `Science Fiction / Drama` | |
| `ListItem.Studio` | 8 studios, ` / `-joined | network is folded in here |
| `ListItem.Tagline` | present | |
| `ListItem.Top250` | *(empty)* | not a favourite; see encodings below |
| `ListItem.Property(IMDB_Ranking)` | *(empty)* | static map, this title is not in it |

So the ratings row renders `IMDb 6.5` beside a tomato `83%` — the number next to
the IMDb logo is Jellyfin's community score, and the tomato is genuinely the
tomatometer.

## Three encodings the skin must know about

These are non-obvious and each one has bitten, or will bite, a refactor.

| Where | What it does | Consequence for the skin |
| --- | --- | --- |
| `item_functions.py:646,649` | Jellyfin's **community** rating is registered under the rating type `"imdb"` *and* made the default | `ListItem.Rating(imdb)` and `ListItem.Rating` are both the community rating. The ratings row therefore draws a community score **under an IMDb logo**. |
| `item_functions.py:651` | Jellyfin's **critic** rating → `ListItem.Property(RottenTomatoes_Rating)` | Jellyfin's `CriticRating` **is** the Rotten Tomatoes tomatometer, so the `rtfresh`/`rtrotten`/`certified` icons are factually correct — not stale TMDb branding. Don't delete them as "TMDb leftovers". |
| `item_functions.py:515` | `setTop250(1)` when `favorite == 'true'` | **`ListItem.Top250` means "is a Jellyfin favourite", not a rank.** Any refactor that points a top-250 display at `ListItem.Top250` prints `#1` on every favourite. |

Two more scale/semantics gotchas:

- `item_functions.py:613` — `setUserRating(round(critic_rating))` pushes Jellyfin's
  **0-100** critic rating into Kodi's `setUserRating`, which expects **1-10**. So
  `ListItem.UserRating` reads e.g. `89`, and `$INFO[ListItem.UserRating,,.0]`
  renders `89.0`. Gated on the addon's `addUserRatings` setting.
- `item_functions.py:616` — `setTrailer("plugin://plugin.video.jellycon?mode=playTrailer&id=...")`
  is set for **movies and series unconditionally**, whether or not a trailer
  exists. So `ListItem.Trailer` is never empty and tells you nothing. Resolution
  happens at click time (`/LocalTrailers` + `Fields=RemoteTrailers`, YouTube URLs
  only) and always opens a `dialog.select`. **No real trailer URL is exposed to
  the skin.**

## Capability table

Kodi ≥ 20 here (`MyVideos146`), so the InfoTag branch (`item_functions.py:493-665`)
is the live path; the Kodi-19 `setInfo` branch (`:667-749`) is dead.

| Field | Available | How |
| --- | --- | --- |
| Title, SortTitle | yes | `setTitle`, `setSortTitle` |
| Plot | yes | `setPlot` (addon setting `include_overview`, currently on) |
| Tagline | yes | `setTagLine` |
| Community rating | yes | see encodings above |
| Critic rating | partial | `ListItem.UserRating` (0-100 scale bug) and `Property(RottenTomatoes_Rating)` |
| **Votes** | **no** | hardcoded `0` in both `setRating` calls |
| MPAA / certificate | yes | `setMpaa` from `OfficialRating` |
| Year, Premiered, DateAdded | yes | `setYear`, `setPremiered`, `setDateAdded` |
| Episode aired date | **probably no** | `setFirstAired` is **never called**; only `setPremiered`. Whether `ListItem.Aired` populates from that is Kodi-internal — unverified. |
| Genre | yes | `setGenres`. Note `Property(genres)` is only set in the dead Kodi-19 branch — don't use it. |
| Studio | yes | `setStudios`. Jellyfin folds network into Studios, so **there is no separate network field**. |
| Country, Tags | yes | from `ProductionLocations`, `TagItems` |
| **Cast / director / writer** | **currently no** | `setDirectors`/`setWriters`/`setCast` are called, but `People` is only requested when the addon setting `include_people` is true — it is **false** in `userdata/addon_data/plugin.video.jellycon/settings.xml:44`. Cast is also fetchable on demand via `mode=WIDGET_CONTENT_CAST`, which refetches and works regardless of the setting. |
| **Provider IDs (tmdb/imdb/tvdb)** | **no** | `ProviderIds` *is* fetched (`utils.py:389`) but used only for the local IMDb-250 map. No `setUniqueIDs`, no `setIMDBNumber`, no tmdb-id property anywhere. |
| Series status | yes | `setTvShowStatus` → `ListItem.Status` (Continuing/Ended) |
| **Next episode airing** | **no** | nothing. For `LocationType == "Virtual"` items the date + `AirTime` are string-concatenated into the item **label** (`:207-208`). No property. |
| Duration, resume, playcount | yes | plus `Property(TotalTime)`, `Property(complete_percentage)` |
| Season / episode numbers | yes | plus `Property(IsSpecial)`, `Property(NumEpisodes/TotalEpisodes/TotalSeasons)` |
| Stream details | yes | `addVideoStream`/`addAudioStream`/`addSubtitleStream` (setting `include_media`, on) |
| IMDb Top 250 rank | movies only | `Property(IMDB_Ranking)`, from a **static hardcoded map** in `mediadata.py`, not live |
| Jellyfin item id / type | yes | `Property(id)`, `Property(ItemType)`, `Property(series_id)` |
| Favourite | yes, hackily | `ListItem.Top250 == 1` — see encodings |

### Artwork — the strong area

The full dict goes to `setArt` (`get_art`, `:763-850`), so all keys are reachable
as `ListItem.Art(<key>)`: `thumb, fanart, poster, banner, clearlogo, clearart,
discart, landscape`, plus `tvshow.*` inheritance for episodes and `season.*` for
seasons.

Mapping: poster←`Primary`, fanart←`Backdrop` (with parent fallback),
clearlogo←`Logo`, clearart←`Art`, landscape←`Thumb`, banner←`Banner`,
discart←`Disc`.

**Caveat:** each resolves only if the artwork exists **on the Jellyfin server**.
JellyCon does no fanart.tv or TMDb fallback, so clearlogo/clearart/discart
coverage is whatever your library has — typically thinner than TMDbHelper +
fanart.tv gave.

## Discovery and lists

| Capability | Available | How |
| --- | --- | --- |
| Browse by genre / year / tag | yes | `mode=GENRES`; `type=show_movie_years`; `type=show_movie_tags` |
| A-Z lists | yes | `NameStartsWith` |
| Collection / set members | yes | BoxSets are folders with `mediatype='set'` |
| Person filmography | yes | `mode=NEW_SEARCH_PERSON&person_id=` → `PersonIds=` |
| Next Up | yes | `/Shows/NextUp` |
| Latest / recent / in-progress / random / favourites | yes | the `mode=WIDGET_CONTENT` family |
| Extras / special features | yes | context menu → `/Users/{u}/Items/{id}/SpecialFeatures` |
| Live TV | yes | `/LiveTv/Channels`, `/LiveTv/Programs/Recommended`, `/LiveTv/Recordings` |
| **Similar / "more like this"** | **no** | `/Items/{id}/Similar` exists in Jellyfin but is **never called** — `grep -rn Similar resources/lib/` returns nothing |
| Recommendations | partial | only a **global, randomised** widget (`/Movies/Recommendations`) — not per-item |
| **Browse by studio** | **no** | no `StudioIds` filter and no studio menu; search passes `IncludeStudios: False` |

## Verdict

JellyCon is authoritative for *your* library — watched state, resume points,
favourites, unwatched counts, real stream details, Next Up — and needs no API key.
Plot, tagline, ratings, genre, studio, MPAA, premiered and artwork are all
genuinely there.

It cannot replace TMDbHelper feature-for-feature as it stands. The gaps that
matter, in order: no provider IDs (so nothing downstream can identify an item, and
no handoff to any enrichment addon is even possible), no per-item similar, no
votes, no next-airing date, no real trailer URL, no studio browse, and
cast/director/writer switched off.

## Deferred fork work

Skin-only changes cannot close the gaps above. This is our fork, so all of it is
reachable. Ranked by value; lift into its own plan when picked up.

1. **`mode=SET_FAVORITE` route.** The reason the skin has no favourites toggle
   today. `mark_item_favorite` / `unmark_item_favorite` (`functions.py:244,257`)
   are reachable only via `mode=SHOW_MENU` → `show_menu()` (`:339`), which opens a
   modal rendered on JellyCon's *own bundled skin*, needs a second user selection,
   and ends in `Container.Refresh()` — which fires underneath an open
   DialogVideoInfo, invalidating its ListItem and resetting list position. A direct
   route reduces the skin side to ~4 lines.
2. **`setUniqueIDs` from `ProviderIds`.** Already fetched; used only for the
   IMDb-250 map. ~5 lines in `add_gui_item`. Highest-leverage single change —
   without it nothing downstream can identify an item.
3. **`/Items/{id}/Similar`.** Refills the Similar and Recommended rows.
4. **`include_people = true`.** A settings flip, but it adds `People` to every list
   request, which is why it defaults off. Measure the cost.
5. **Real vote counts** instead of hardcoded `0`.
6. **Critic-rating scale** — stop pushing 0-100 into a 1-10 field.
7. **Real trailer URLs** from `RemoteTrailers`. Prerequisite for ever re-enabling
   the skin's auto-trailer (see the `Timers.xml` warning in
   [tmdbhelper.md](tmdbhelper.md)).
8. **`StudioIds` browse.**
9. **Next-episode airing date** as a property rather than concatenated into a label.
10. **Stop abusing `setTop250(1)`** for favourites — it collides with real
    top-250 display and forces the skin to avoid `ListItem.Top250` entirely.
