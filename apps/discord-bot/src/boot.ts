/**
 * Bot runtime entrypoint — loads the wizard-written env file from its
 * canonical location, then hands off to the actual bot startup.
 *
 * Previously the `start` and `dev` scripts used `node --env-file=.env`,
 * which reads `.env` in the current working directory. That diverged
 * from the path the onboarding wizard writes to (see wizard/paths.ts:
 * `getBotEnvPath()` → `$MUSIC_DL_CONFIG_DIR/discord-bot.env` with
 * `$XDG_CONFIG_HOME/music-dl/discord-bot.env` and `~/.config/music-dl/
 * discord-bot.env` as fallbacks, plus a `$MUSIC_DL_BOT_ENV_PATH`
 * override). The wizard would write to the canonical path and the bot
 * would read from cwd — silently diverging state. Same failure mode as
 * the shared-token gap, closed the same way: a single authoritative
 * path, consulted by both writer and reader.
 */

import { existsSync, readFileSync } from "node:fs";

import { getBotEnvPath } from "./wizard/paths";

const envPath = getBotEnvPath();
if (existsSync(envPath)) {
  loadEnvFile(envPath);
}

await import("./index");

function loadEnvFile(path: string): void {
  const body = readFileSync(path, "utf8");
  for (const rawLine of body.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;

    const separator = line.indexOf("=");
    if (separator <= 0) continue;

    const key = line.slice(0, separator).trim();
    const rawValue = line.slice(separator + 1).trim();
    process.env[key] = parseEnvValue(rawValue);
  }
}

function parseEnvValue(value: string): string {
  if (value.length >= 2 && value.startsWith('"') && value.endsWith('"')) {
    return value
      .slice(1, -1)
      .replace(/\\(["\\])/g, "$1");
  }
  return value;
}
