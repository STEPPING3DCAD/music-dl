/**
 * Bot runtime entrypoint — loads the GUI-written env file from its
 * canonical location, then hands off to the actual bot startup.
 */

import { existsSync, readFileSync } from "node:fs";

import { getBotEnvPath } from "./paths";

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