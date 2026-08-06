# music-dl Discord Bot

A single-user, single-guild Discord bot that streams and downloads from your
`music-dl` library. It never talks to Tidal or the filesystem directly — every
resolve, playable URL, and download job goes through the backend's
`/api/bot/*` endpoints.

## What it does

- **Slash commands in one channel, for one user.** `djai`, `summon`, `leave`, `play`,
  `playlist`, `pause`, `resume`, `skip`, `queue`, `nowplaying`, `volume`,
  `repeat`, `download`.
- **DJAI remote panel.** On startup the bot refreshes the last control panel
  when it can. Running `/djai` posts a fresh remote panel in the channel.
  Buttons open search, summon the bot to the allowed user's current voice
  channel, playlist replace/add pickers, playback controls, queue view, and
  repeat controls. Only the allowed user can use them.
- **Playlist UX without IDs.** The playlist buttons show saved Tidal
  playlists. Selecting one from Playlists replaces the current queue, starts
  that playlist, and defaults repeat to `all`. Selecting one from Add Playlist
  appends it without clearing the current queue and also defaults repeat to
  `all`. `/playlist list`, `/playlist switch`, and `/playlist add` provide
  the same saved-playlist control from slash commands.
- **Voice playback** via `@discordjs/voice`, `libsodium-wrappers`, and
  `@discordjs/opus`. DAVE (v=8) voice protocol is supported through
  `@snazzah/davey`.
- **Never downloads on `/play`.** `/play` resolves and queues; `/download`
  is the only command that kicks off a download job.
- **Visible picker for free-text search.** Up to five numbered-button
  choices with a 30s timeout. Direct URLs and single matches skip the
  picker and queue immediately.
- **Authorization gate before every command.** Guild + channel + user
  must all match the values in the env file, or the command is rejected
  with an ephemeral reply.

## Requirements

- **Bun 1.2+** for install, tests, and the bot runtime.
- **ffmpeg** on `PATH` (voice resampling)
- A **Discord application + bot token** with `Connect` and `Speak`
  voice permissions in your guild
- A running **music-dl backend** (`music-dl gui`) that this bot can reach

## Setup

Bot setup is **GUI-only** via the music-dl DJAI panel and Bot Control API
(`/bot-control`).

```bash
music-dl gui
```

Open the DJAI view, enter the Discord bot token and allowed guild/channel/user
IDs, save the config, then use **Deploy Discord Bot**, **Restart**, or
**Shutdown** to manage the bot service.

After config is valid, the GUI owns the normal bot lifecycle. App startup
launches the bot in the background, records its PID in
`<config-dir>/discord-bot.pid`, reuses a still-live recorded bot after backend
restarts, and shuts the bot down when the app exits. You do not need a
separate terminal just to keep the bot alive.

The GUI writes two files. The config directory is resolved in this
precedence: `$MUSIC_DL_CONFIG_DIR` → `$XDG_CONFIG_HOME/music-dl` →
`~/.config/music-dl`. Backend (`path_config_base()`) and bot runtime
(`paths.ts`) implement this identically.

| File | Purpose | Mode |
| --- | --- | --- |
| `<config-dir>/discord-bot.env` | Bot runtime config (7 required vars) | 0600 |
| `<config-dir>/bot-shared-token` | Bearer token the backend validates against | 0600 |
| `<config-dir>/discord-bot.pid` | GUI-owned bot process marker | 0600 |

Override individual paths with `MUSIC_DL_BOT_ENV_PATH` and
`MUSIC_DL_BOT_TOKEN_PATH` if you need to (CI, container mounts). Override the
PID marker with `MUSIC_DL_BOT_PID_PATH`.

See [`../../tidaldl-py/docs/bot-onboarding.md`](../../tidaldl-py/docs/bot-onboarding.md)
for the full GUI setup flow.

## Running the bot

```bash
cd apps/discord-bot
bun run start     # runs src/boot.ts, which loads the env file and imports src/index.ts
```

The desktop GUI launches the same entrypoint directly with
`bun src/boot.ts` so its PID file tracks the long-running bot process.

`boot.ts` reads the env file from the canonical config path
(`getBotEnvPath()`). It does not read `.env` from the current directory.

On startup you should see:

```
Registered 13 slash commands.
Logged in as <bot-name>#<discriminator>.
```

The bot registers commands **per-guild** (not globally), so they appear
immediately in the allowed server.

## Environment variables

Every variable is **required** — the bot refuses to start with a clear
`Missing required configuration: ...` message if any are empty.

| Variable | Where to find it |
| --- | --- |
| `DISCORD_TOKEN` | Discord Developer Portal → your app → Bot → Reset Token |
| `DISCORD_APPLICATION_ID` | Developer Portal → General Information → Application ID |
| `ALLOWED_GUILD_ID` | Discord client → right-click your server → Copy Server ID (Developer Mode on) |
| `ALLOWED_CHANNEL_ID` | Right-click the text channel → Copy Channel ID |
| `ALLOWED_USER_ID` | Right-click your own name → Copy User ID |
| `MUSIC_DL_BASE_URL` | Where the backend listens, e.g. `http://127.0.0.1:8765` |
| `MUSIC_DL_BOT_TOKEN` | Matches the GUI-written `bot-shared-token` file |

## Architecture

```
src/
├── boot.ts              Loads env from the canonical config path, then imports index.ts
├── index.ts             Discord client + slash registration + interaction dispatch
├── config.ts            parseConfig() — validates the 7 required env vars, fails fast
├── auth.ts              ensureAuthorized() — guild + channel + user gate
├── commands.ts          slash commands + download polling + batch reply serialization
├── musicDlClient.ts     Typed HTTP client for /api/bot/* (resolve, playable, download, status)
├── queue.ts             Pure queue state machine (no Discord deps) — append, advance, repeat modes
├── player.ts            VoiceManager (voice lifecycle, ghost-session cleanup) + Playback (queue ↔ audio player)
├── picker.ts            Up-to-5 numbered-button picker for free-text search disambiguation
├── errors.ts            Generic user-facing messages — internal details never leak to Discord
└── paths.ts             Canonical env + shared-token paths (must match backend precedence)
```

### Request flow for `/play <query>`

```
Discord interaction
  → commands.handlePlay
  → auth.ensureAuthorized          (guild + channel + user gate)
  → interaction.deferReply         (resolve can take > 3s)
  → musicDlClient.resolve(query)   → POST /api/bot/play/resolve
  → if kind=="choices" && >1       → picker.runPicker (30s timeout)
  → queue.append([...])
  → playback.playCurrent           (only if queue was empty)
     → musicDlClient.playable(id)  → POST /api/bot/playable
     → ffmpeg -vn → 48 kHz stereo PCM
     → createAudioResource(pcm, StreamType.Raw)
     → VoiceManager.player.play(resource)
```

No filesystem access, no Tidal API, no `ytdl`/remote resolution —
everything routes through the backend.

### Request flow for `/playlist`

```
/playlist list
  → /api/playlists
  → show saved playlists

/playlist switch name:<playlist>
  → /api/playlists → match name or ID → /api/playlists/{id}/tracks
  → queue.clear() + queue.append([...])
  → playback.playCurrent
  → repeat all

/playlist add name:<playlist>
  → /api/playlists → match name or ID → /api/playlists/{id}/tracks
  → queue.append([...])
  → playback.playCurrent only if queue was empty
  → repeat all
```

### DJAI remote flow

```
Bot startup
  → post or refresh one DJAI panel in ALLOWED_CHANNEL_ID
  → button/select/modal interactions
  → auth.ensureAuthorized          (guild + channel + user gate)
  → Summon                         → join allowed user's current voice channel
  → Search                         → modal → /api/bot/play/resolve → track picker
  → Playlists                      → /api/playlists → select → /api/playlists/{id}/tracks
  → queue.clear() + queue.append([...])
  → playlist selection starts immediately and sets repeat all by default
  → Add Playlist                   → /api/playlists → select → /api/playlists/{id}/tracks
  → queue.append([...])
  → repeat all
```

## Testing

```bash
bun test                      # all tests
bun test commands             # just commands.test.ts
bun run typecheck             # tsc --noEmit
```

Tests are dependency-injection-first: `VoiceManager`, `Playback`,
`MusicDlClient`, and every probe can be swapped. No tests touch a real
Discord gateway, a real filesystem, or the real user config directory.

## Troubleshooting

- **`Missing required configuration: ...` on startup** — the bot did
  not load a complete `discord-bot.env`. Open the DJAI panel in
  `music-dl gui` and save bot config via Bot Control, or check the file
  resolved by `MUSIC_DL_BOT_ENV_PATH`.
- **Commands do not appear in Discord** — commands are registered to
  `ALLOWED_GUILD_ID`, not globally. Confirm the guild ID and restart the
  bot; guild commands should appear immediately.
- **`/summon` cannot connect** — the bot needs `Connect` and `Speak`
  in the target voice channel. If permissions are correct, restart the
  bot to clear any stale Discord voice session from a previous process.
- **Voice protocol, encryption, or Opus errors** — run `bun install` in
  `apps/discord-bot` so `@discordjs/opus`, `libsodium-wrappers`, and
  `@snazzah/davey` dependencies are present.
- **Backend returns `401` to every bot request** — the bot and backend
  are using different shared tokens. `MUSIC_DL_BOT_TOKEN` takes
  precedence over the shared-token file. After manually recreating the token
  file, restart the Discord bot from the DJAI panel so it reloads
  `discord-bot.env`. Restart `music-dl gui` only when changing its
  `MUSIC_DL_BOT_TOKEN` process environment.

## Related docs

- [`../../tidaldl-py/docs/bot-onboarding.md`](../../tidaldl-py/docs/bot-onboarding.md) — GUI setup flow, Bot Control API, shared-token handoff
