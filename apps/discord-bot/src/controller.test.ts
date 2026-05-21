import { describe, expect, mock, test } from "bun:test";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import type { BotConfig } from "./config";
import { buildControllerPanel, handleControllerInteraction, postOrUpdateControllerPanel } from "./controller";
import type { MusicDlClient } from "./musicDlClient";
import { QueueState } from "./queue";
import type { Playback, VoiceManager } from "./player";
import type { CommandDeps } from "./commands";

function makeConfig(): BotConfig {
  return {
    discordToken: "t",
    discordApplicationId: "app",
    allowedGuildId: "g-ok",
    allowedChannelId: "c-ok",
    allowedUserId: "u-ok",
    musicDlBaseUrl: "http://backend",
    musicDlBotToken: "bot",
  };
}

function makeDeps(overrides: Partial<CommandDeps> = {}): CommandDeps {
  const client: Partial<MusicDlClient> = {
    playlists: mock(async () => [
      { id: "pl1", name: "Sunday Reset", num_tracks: 2 },
    ]),
    playlistItems: mock(async () => [
      {
        id: "tidal:1",
        title: "Track One",
        artist: "Artist One",
        source_type: "tidal" as const,
        local: false,
        duration: 100,
      },
      {
        id: "tidal:2",
        title: "Track Two",
        artist: "Artist Two",
        source_type: "tidal" as const,
        local: false,
        duration: 120,
      },
    ]),
  };
  const playback: Partial<Playback> = {
    playCurrent: mock(async () => null),
    pause: mock(() => true),
    resume: mock(() => true),
    skip: mock(async () => null),
    stop: mock(() => {}),
  };
  const voice: Partial<VoiceManager> = {
    join: mock(async () => ({}) as never),
  };

  return {
    config: makeConfig(),
    client: client as MusicDlClient,
    queue: new QueueState(),
    voice: voice as VoiceManager,
    playback: playback as Playback,
    logger: { error: () => {} },
    ...overrides,
  };
}

function makeSelectInteraction(value = "pl1") {
  const calls: unknown[] = [];
  return {
    guildId: "g-ok",
    channelId: "c-ok",
    user: { id: "u-ok" },
    isButton: () => false,
    isStringSelectMenu: () => true,
    isModalSubmit: () => false,
    customId: "djai:playlist",
    values: [value],
    deferUpdate: mock(async () => calls.push("deferUpdate")),
    followUp: mock(async (payload: unknown) => calls.push(payload)),
    _calls: calls,
  };
}

function makeAppendSelectInteraction(value = "pl1") {
  return {
    ...makeSelectInteraction(value),
    customId: "djai:playlist-add",
  };
}

function makeButtonInteraction(customId = "djai:queue") {
  const calls: unknown[] = [];
  return {
    guildId: "g-ok",
    channelId: "c-ok",
    user: { id: "u-ok" },
    member: { voice: { channel: { id: "v-ok", name: "La Radio", guild: { id: "g-ok" } } } },
    channel: { id: "c-ok", send: mock(async () => null) },
    isButton: () => true,
    isStringSelectMenu: () => false,
    isModalSubmit: () => false,
    customId,
    deferred: false,
    replied: false,
    reply: mock(async (payload: unknown) => calls.push(payload)),
    deferReply: mock(async (payload: unknown) => calls.push(payload)),
    editReply: mock(async (payload: unknown) => calls.push(payload)),
    followUp: mock(async (payload: unknown) => calls.push(payload)),
    _calls: calls,
  };
}

describe("DJAI controller panel", () => {
  test("panel exposes human playback controls", () => {
    const deps = makeDeps();
    const panel = buildControllerPanel(deps);

    expect(panel.content).toContain("DJAI");
    expect(panel.content).toContain("Repeat: all");
    const json = JSON.stringify(panel.components.map((row) => row.toJSON()));
    expect(json).toContain("Search");
    expect(json).toContain("Summon");
    expect(json).toContain("Playlists");
    expect(json).toContain("Add Playlist");
    expect(json).toContain("Play/Pause");
  });

  test("summon button joins the allowed user's current voice channel", async () => {
    const deps = makeDeps();
    const interaction = makeButtonInteraction("djai:summon");

    const handled = await handleControllerInteraction(interaction as never, deps);

    expect(handled).toBe(true);
    expect(deps.voice.join).toHaveBeenCalledWith(
      interaction.member.voice.channel,
      interaction.channel,
    );
    expect(JSON.stringify(interaction._calls)).toContain("Joined **La Radio**.");
  });

  test("summon button rejects when the allowed user is not in voice", async () => {
    const deps = makeDeps();
    const interaction = {
      ...makeButtonInteraction("djai:summon"),
      member: { voice: { channel: null } },
    };

    const handled = await handleControllerInteraction(interaction as never, deps);

    expect(handled).toBe(true);
    expect(deps.voice.join).not.toHaveBeenCalled();
    expect(JSON.stringify(interaction._calls)).toContain("Join a voice channel first");
  });

  test("playlist selection switches playlist and defaults repeat to all", async () => {
    const deps = makeDeps();
    deps.queue.setRepeat("off");

    const handled = await handleControllerInteraction(
      makeSelectInteraction() as never,
      deps,
    );

    expect(handled).toBe(true);
    expect(deps.queue.length).toBe(2);
    expect(deps.queue.current()?.id).toBe("tidal:1");
    expect(deps.queue.getRepeat()).toBe("all");
    expect((deps.playback.playCurrent as ReturnType<typeof mock>).mock.calls.length).toBe(1);
  });

  test("playlist selection replaces the old queue and restarts playback", async () => {
    const deps = makeDeps();
    deps.queue.append([{ id: "old", title: "Old Track" }]);

    const handled = await handleControllerInteraction(
      makeSelectInteraction() as never,
      deps,
    );

    expect(handled).toBe(true);
    expect(deps.queue.contents().map((item) => item.id)).toEqual(["tidal:1", "tidal:2"]);
    expect(deps.queue.current()?.id).toBe("tidal:1");
    expect((deps.playback.playCurrent as ReturnType<typeof mock>).mock.calls.length).toBe(1);
  });

  test("add playlist button opens append picker", async () => {
    const deps = makeDeps();
    const interaction = makeButtonInteraction("djai:playlists-add");

    const handled = await handleControllerInteraction(interaction as never, deps);

    expect(handled).toBe(true);
    expect(JSON.stringify(interaction._calls)).toContain("Pick playlist to add to queue");
    expect(JSON.stringify(interaction._calls)).toContain("djai:playlist-add");
  });

  test("playlist add selection appends without clearing current queue", async () => {
    const deps = makeDeps();
    deps.queue.append([{ id: "old", title: "Old Track" }]);

    const handled = await handleControllerInteraction(
      makeAppendSelectInteraction() as never,
      deps,
    );

    expect(handled).toBe(true);
    expect(deps.queue.contents().map((item) => item.id)).toEqual(["old", "tidal:1", "tidal:2"]);
    expect(deps.queue.current()?.id).toBe("old");
    expect(deps.queue.getRepeat()).toBe("all");
    expect((deps.playback.playCurrent as ReturnType<typeof mock>).mock.calls.length).toBe(0);
  });

  test("playlist add selection starts playback when queue was empty", async () => {
    const deps = makeDeps();
    const interaction = makeAppendSelectInteraction();

    const handled = await handleControllerInteraction(
      interaction as never,
      deps,
    );

    expect(handled).toBe(true);
    expect(deps.queue.contents().map((item) => item.id)).toEqual(["tidal:1", "tidal:2"]);
    expect((deps.playback.playCurrent as ReturnType<typeof mock>).mock.calls.length).toBe(1);
    expect(JSON.stringify(interaction._calls)).toContain("Added playlist to queue: 2 tracks.");
  });

  test("empty playlist selection does not clear the current queue", async () => {
    const deps = makeDeps({
      client: {
        playlists: mock(async () => []),
        playlistItems: mock(async () => []),
      } as never,
    });
    deps.queue.append([{ id: "old", title: "Old Track" }]);
    const interaction = makeSelectInteraction();

    const handled = await handleControllerInteraction(
      interaction as never,
      deps,
    );

    expect(handled).toBe(true);
    expect(deps.queue.contents().map((item) => item.id)).toEqual(["old"]);
    expect(deps.playback.playCurrent).not.toHaveBeenCalled();
    expect(JSON.stringify(interaction._calls)).toContain("No playable items in that playlist.");
  });

  test("playlist selection refreshes saved public panel, not the ephemeral picker", async () => {
    const postOrUpdate = mock(async () => {});
    const deps = makeDeps({
      controller: { postOrUpdate },
    });
    const interaction = {
      ...makeSelectInteraction(),
      message: {
        editable: true,
        edit: mock(async () => {
          throw new Error("wrong message");
        }),
      },
    };

    const handled = await handleControllerInteraction(interaction as never, deps);

    expect(handled).toBe(true);
    expect(postOrUpdate).toHaveBeenCalled();
    expect(interaction.message.edit).not.toHaveBeenCalled();
    expect(JSON.stringify(interaction._calls)).toContain("Switched playlist in repeat mode: 2 tracks.");
  });

  test("unauthorized control click is rejected", async () => {
    const deps = makeDeps();
    const interaction = makeSelectInteraction();
    interaction.user.id = "intruder";

    const handled = await handleControllerInteraction(interaction as never, deps);

    expect(handled).toBe(true);
    expect(deps.queue.length).toBe(0);
    expect((interaction.followUp as ReturnType<typeof mock>).mock.calls.length).toBe(1);
  });

  test("controller errors produce private failure instead of timing out", async () => {
    const deps = makeDeps({
      queue: {
        contents: () => {
          throw new Error("boom");
        },
      } as never,
    });
    const interaction = makeButtonInteraction();

    const handled = await handleControllerInteraction(interaction as never, deps);

    expect(handled).toBe(true);
    expect(JSON.stringify(interaction._calls)).toContain("DJAI remote action failed");
  });

  test("forceNew posts a fresh panel instead of editing old saved state", async () => {
    const deps = makeDeps();
    const dir = await mkdtemp(join(tmpdir(), "djai-panel-"));
    const path = join(dir, "panel.json");
    await writeFile(path, JSON.stringify({ channelId: "c-ok", messageId: "old-panel" }));
    const fetchPrevious = mock(async () => ({ edit: mock(async () => {}) }));
    const send = mock(async () => ({ id: "new-panel" }));
    const client = {
      channels: {
        fetch: mock(async () => ({
          type: 0,
          send,
          messages: { fetch: fetchPrevious },
        })),
      },
    };

    await postOrUpdateControllerPanel(client as never, deps, { forceNew: true }, path);

    expect(fetchPrevious).not.toHaveBeenCalled();
    expect(send).toHaveBeenCalled();
    expect(JSON.parse(await readFile(path, "utf8")).messageId).toBe("new-panel");
  });
});
