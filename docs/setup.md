# Setup

This guide goes from a fresh clone to talking to a coding agent from your Apple Watch.

Chums is distributed as source code only. There is no App Store, TestFlight or hosted service:

- you build the watch app in Xcode and sign it with your own Apple ID;
- the hub runs on your own Mac;
- Tailscale Funnel gives the hub a public HTTPS address, which is how the watch reaches it from any network.

The first setup takes about 20–30 minutes of your time, plus waiting: Xcode can take 10 minutes or more to prepare a
device the first time, and a new Funnel address can take up to half an hour to appear in public DNS. Step 5 starts that
wait early.

`bin/chums-doctor` checks every link of the chain (tools, sign-ins, hub, Funnel, Xcode, the watch) and prints the fix
for each failure. It changes nothing, so run it whenever something is unclear. Problems and their fixes are in
[troubleshooting.md](troubleshooting.md).

| Step | What | Who |
| --- | --- | --- |
| [1](#1-what-you-need) | What you need | |
| [2](#2-pick-your-agent) | Pick your agent: Claude Code, Codex, or both | |
| [3](#3-get-the-code-and-check-the-mac) | Get the code and check the Mac | Terminal |
| [4](#4-start-the-hub) | Start the hub | Terminal |
| [5](#5-put-the-hub-on-the-internet-tailscale-funnel) | Put the hub on the internet (Tailscale Funnel) | Terminal, browser |
| [6](#6-sign-in-to-xcode-with-your-apple-id) | Sign in to Xcode with your Apple ID | Xcode |
| [7](#7-connect-the-iphone-and-the-watch-to-xcode) | Connect the iPhone and the watch to Xcode | iPhone, watch, Xcode |
| [8](#8-turn-on-developer-mode) | Turn on Developer Mode on the iPhone and the watch | iPhone, watch |
| [9](#9-build-and-install-the-apps) | Build and install the apps | Terminal |
| [10](#10-start-the-agents) | Start the agents | Terminal, watch or iPhone |
| [11](#11-talk-to-it-from-the-watch) | Talk to it from the watch | Watch |

Optional, after that: [the watch app's settings](#the-watch-apps-settings), [the iPhone app](#the-iphone-app),
[keyring mode](#keyring-mode), [background agents](#background-agents), [the agents' voices](#the-agents-voices),
[the Simulator](#no-watch-the-simulator), [settings](#settings), [updating](#updating), [removing Chums](#removing-chums).

## 1. What you need

| What | Minimum | Why | How to get it |
| --- | --- | --- | --- |
| A Mac with Apple silicon | macOS 15.6 | Runs the hub, speech to text and the agents, and builds the app. Xcode 26 needs macOS 15.6 | System Settings › General › Software Update |
| An Apple Watch | watchOS 10 | Runs Chums. A Series 5 on watchOS 10.6.1 has been tested; see [older watches](older-watches.md) for compatibility and installation notes | iPhone: Watch app › General › Software Update |
| The iPhone the watch is paired with | iOS 26 | Xcode reaches the watch through it | Settings › General › Software Update |
| A USB cable for that iPhone | | The first time, Xcode finds a watch only through its iPhone connected by cable | |
| One Wi-Fi network for the Mac, the iPhone and the watch | | Xcode installs on the watch over the local network | |
| Xcode | 26.0 | Builds, signs and installs the watch app | [Mac App Store](https://apps.apple.com/app/xcode/id497799835), then open it once |
| An Apple ID signed in to Xcode | free or paid | Signs the app. See [Apple Developer account](#apple-developer-account) below | Xcode › Settings › Apple Accounts |
| Homebrew | | Installs the tools below | [brew.sh](https://brew.sh) |
| Node.js | 20.11 | Runs the hub and the Claude Code channel | `brew install node` |
| XcodeGen | | Generates the Xcode project from `app/project.yml` | `brew install xcodegen` |
| WhisperKit CLI and the Whisper base model (about 150 MB) | | Speech to text, on the Mac | `brew install whisperkit-cli`; `bin/chums-setup` downloads the model |
| ffmpeg | | Converts each clip from the watch or the iPhone to the WAV that WhisperKit reads, and takes the still of a video shown on the watch | `brew install ffmpeg` |
| uv (optional) | | Installs the agents' voices (Kokoro) in their own Python. Without it, the watch reads replies in its own voice | `brew install uv` |
| Tailscale's command-line tools (`tailscale` and `tailscaled`) | 1.52 | Give the hub a public HTTPS address with Funnel | `brew install tailscale` |
| A Tailscale account | the free Personal plan | Funnel is part of it | [login.tailscale.com/start](https://login.tailscale.com/start) |
| Claude Code, signed in | a current version (last checked: 2.1.280) | A Claude Code agent. Needs a Pro, Max, Team or Enterprise plan, or a Console API key | `curl -fsSL https://claude.ai/install.sh \| bash`, then run `claude` and `/login` |
| Codex CLI, signed in | 0.160 | A Codex agent. Signs in with ChatGPT or an API key | `npm install -g @openai/codex` (or `brew install --cask codex`), then `codex login` |
| python3, git, curl, expect | | The scripts in `bin/` and `tools/`; expect runs the background Claude Code agents | Come with macOS and Xcode |

You need Claude Code or Codex, not both: see step 2.

### Apple Developer account

Any Apple ID can sign Chums. Xcode gives every Apple ID a free **Personal Team**; the paid **Apple Developer Program**
removes its limits. Chums uses HealthKit (for keyring mode) and background modes, which both kinds of team can sign.

| | Free Personal Team | Apple Developer Program |
| --- | --- | --- |
| Cost | Free, with any Apple ID | $99 a year (or the local price) |
| How long an install works | 7 days. Then Chums doesn't open until you run `bin/chums-install` again | 1 year, the life of the provisioning profile |
| Devices | 3 registered devices | 100 per device type per membership year |
| Apps | 3 apps installed per device from free teams | No such limit |
| App IDs | 10 per 7 days. Each Chums bundle ID uses 4 (iPhone app, its widgets, watch app, watch widget) | No such limit |
| Sign up | Xcode › Settings › Apple Accounts › + › Apple ID | [developer.apple.com/programs](https://developer.apple.com/programs/enroll/) |

## 2. Pick your agent

Each agent in Chums is one coding session that the watch talks to, and every character is its own agent. An agent
runs on Claude Code or on Codex, and you can mix them. Every agent starts on Claude Code; you switch one to Codex from
the watch or the iPhone in step 10.

| | Claude Code | Codex |
| --- | --- | --- |
| Install and sign in | `curl -fsSL https://claude.ai/install.sh \| bash`, then `claude` and `/login` | `npm install -g @openai/codex`, then `codex login` |
| How it connects | The Chums channel and hooks, loaded by `bin/chums-claude` | The hub runs `codex app-server` for it and is its client |
| Where it runs | In the background (`bin/chums-agents install`), or in a terminal (`bin/chums-agents open <id>`) | Inside the hub, started with it |
| Where you see it on the Mac | Its terminal, and the Claude app (Remote Control) | A Codex terminal on the same thread: `bin/chums-codex <id>` |
| In `~/.chums/agents.json` | `"runtime": "claude"`, or no `runtime` | `"runtime": "codex"` |
| Notes | Channels are a research preview. Team and Enterprise plans: an Owner enables channels (and Remote Control) in the organization's Claude Code settings. Remote Control needs a claude.ai login; with an API key, set `"remoteControl": false` in `~/.chums/config.json` | OpenAI labels the app-server experimental; Chums was written against 0.160. If Codex's default model isn't on your plan, set `"model"` |

Changing an agent's soul by voice (its name, what it looks after, its voice) runs `claude -p` on the Mac, so that one
feature needs Claude Code even when all your agents are Codex agents. A change typed on the iPhone doesn't.

Details on Codex agents: [other-agents.md](other-agents.md).

**How to know it worked:** `claude auth status` prints `"loggedIn": true`, or `codex login status` prints
`Logged in`. `bin/chums-doctor` shows them under "2. Coding agents".

## 3. Get the code and check the Mac

```bash
git clone <this repository's URL> chums && cd chums
bin/chums-setup
```

`bin/chums-setup` checks macOS, Node.js, the coding agents, WhisperKit, ffmpeg, Tailscale, Xcode and XcodeGen, and prints
`MISSING` with an install command for each one that isn't there. It also installs the npm packages (`npm ci`),
downloads the Whisper base model (about 150 MB), and, when uv is installed, installs the agents' voices (Kokoro, about
1.5 GB: [the agents' voices](#the-agents-voices)). It is safe to run again; run it until it prints `Ready`.

**How to know it worked:** the last line is `Ready. Next: …`. `bin/chums-doctor` shows "1. This Mac" all `PASS`. The
later sections fail until their steps are done.

## 4. Start the hub

The hub is the Node.js program on your Mac that the watch and the agents talk to.

```bash
bin/chums-hub
```

The first start writes `~/.chums/config.json` (ports and two random tokens, see [SECURITY.md](../SECURITY.md)),
`~/.chums/agents.json` with one agent per character (every character on the watch is its own agent, on Claude Code),
and each agent's soul in `~/.chums/souls/`. It keeps running in that terminal; leave it open.

To run it in the background instead, started at login and restarted if it stops, first stop the hub in the terminal
(Ctrl-C), then:

```bash
bin/chums-setup --launchd       # LaunchAgents for the hub and Chums' tailscaled; hub log in ~/.chums/hub.log
```

As a LaunchAgent (`bin/chums-setup --launchd`), the hub runs under `caffeinate -s`, so the Mac stays awake while it
is on power; `bin/chums-hub` in a terminal doesn't. On battery, a sleeping Mac is offline for the watch.

**How to know it worked:** the hub prints `Chums hub on 127.0.0.1:7717`, `watch API for the tunnel on 127.0.0.1:7718`
and, a few seconds later, `whisper warm in … s`. `bin/chums-doctor` shows "4. The hub" with the hub and speech to text
`PASS` (the agents show as not running until step 10).

## 5. Put the hub on the internet (Tailscale Funnel)

watchOS doesn't support apps reaching an address on your home network
([TN3135](https://developer.apple.com/documentation/technotes/tn3135-low-level-networking-on-watchos)), so the watch
reaches the hub through a public HTTPS address. Tailscale Funnel provides it, without opening a port on your router.
Only the hub's watch side (`127.0.0.1:7718`, paths under `/v1/`, with the watch token) is published. Read
[SECURITY.md](../SECURITY.md) for what that exposes.

1. Create a Tailscale account at [login.tailscale.com/start](https://login.tailscale.com/start). The free Personal
   plan includes Funnel.
2. Install the command-line tools: `brew install tailscale`. Chums runs its own `tailscaled` under your user, without
   an admin password (userspace networking), with its state in `~/.chums/tailscale`. It doesn't use or change the
   Tailscale app if you have one; it joins your tailnet as a separate machine named `chums-hub`.
3. Run:

   ```bash
   bin/chums-tunnel
   ```

4. The first time, it prints a sign-in link (`https://login.tailscale.com/a/…`). Open it, sign in, and connect the
   machine.
5. If Funnel isn't on for your tailnet yet, it prints a second link (`https://login.tailscale.com/f/funnel?…`) and
   waits. Open it and approve. That turns on HTTPS certificates for the tailnet and adds the `funnel` node attribute to
   its access policy, the two things Funnel needs. (By hand: the admin console's DNS page › HTTPS Certificates, and
   Access controls › the `funnel` node attribute.)
6. It then publishes `127.0.0.1:7718` at `https://chums-hub.<your tailnet>.ts.net` and stores that URL as `publicURL`
   in `~/.chums/config.json`. The URL is built into the watch app in step 9.

Tailscale says a new Funnel name can take up to 10 minutes to appear in public DNS; it has taken about 25. The first
HTTPS request to the name also waits a few seconds while Tailscale gets its certificate. Go on with steps 6–8 meanwhile.

**How to know it worked:** check from outside the Mac's own network.

```bash
dig +short chums-hub.<your tailnet>.ts.net @1.1.1.1            # prints IP addresses once public DNS has the name
curl -s https://chums-hub.<your tailnet>.ts.net/v1/ping         # prints {"error":"unauthorized"} after about 1 s
```

`{"error":"unauthorized"}` is the hub refusing a request without the watch token, so Funnel reaches the hub. For a check
that doesn't go through the Mac at all, open the same `/v1/ping` URL in Safari on your iPhone with Wi-Fi off. Then
`bin/chums-doctor` shows "5. Tailscale Funnel" all `PASS`, including a request with the watch token through Funnel.

## 6. Sign in to Xcode with your Apple ID

1. Open Xcode once and let it install its components. Accept the license if it asks.
2. Xcode › Settings › Apple Accounts › + › Apple ID, and sign in. A free Apple ID gets a Personal Team (see
   [Apple Developer account](#apple-developer-account)).

`bin/chums-install` picks the team itself (`tools/pick-team.py`): a paid team if Xcode has one, else your Personal Team.
To choose one, add `"team": "<team ID>"` to `~/.chums/config.json` (or set `CHUMS_TEAM`). The team ID is the 10
characters shown for the team in Xcode › Settings › Apple Accounts.

**How to know it worked:** Xcode › Settings › Apple Accounts lists your Apple ID with a team under it.
`bin/chums-doctor` shows a `signing team` line under "6. Building the watch app".

## 7. Connect the iPhone and the watch to Xcode

Xcode reaches an Apple Watch only through its paired iPhone, and the first time only through an iPhone connected by
USB cable. After that, the iPhone and the watch stay known to Xcode, and installs go over Wi-Fi.

1. Open Xcode, then Window › Devices and Simulators.
2. Connect the iPhone to the Mac with a USB cable and unlock it.
3. On the iPhone, tap **Trust** on "Trust This Computer?" and enter its passcode.
4. The iPhone appears in Devices and Simulators. Xcode shows "Preparing iPhone for development" or copies symbols;
   this can take several minutes. Wait until it finishes.
5. Unlock the watch and keep it near the iPhone, on the same Wi-Fi network as the Mac. Wear it or put it on its
   charger, and keep it awake: a locked or sleeping watch drops the connection.
6. If the watch asks whether to trust this computer, tap **Trust**.
7. The watch appears in Devices and Simulators, under the iPhone or on its own. "Preparing Apple Watch for development"
   can take 10 minutes or more the first time. Keep the watch unlocked until it finishes.

**How to know it worked:** Devices and Simulators lists the watch without a warning, and `bin/chums-doctor` shows
`Apple Watch <name> (watchOS <version>)` under "7. The Apple Watch". If the watch doesn't appear, see
[troubleshooting.md](troubleshooting.md#the-watch-isnt-in-xcode).

For older watches that do not appear in Xcode, see [older-watch installation](older-watches.md). The phone can
transfer the embedded watch app even when direct installation through `devicectl` is unavailable.

## 8. Turn on Developer Mode

Both devices need Developer Mode. Each one restarts to turn it on.

**On the iPhone:**

1. Settings › Privacy & Security › Developer Mode (near the bottom). The switch appears after the iPhone has been
   connected to a Mac with Xcode (step 7).
2. Turn it on and tap **Restart**.
3. After the restart, unlock the iPhone, tap **Turn On** in the alert, and enter the passcode.

**On the watch:**

1. On the watch: Settings › Privacy & Security › Developer Mode. The switch appears after Xcode has seen the watch
   (step 7).
2. Turn it on. The watch asks to restart: restart it from that prompt. (Restarting it another way can make the switch
   disappear again.)
3. After the restart, unlock the watch and confirm **Turn On**.

If the watch's switch isn't there:

1. The switch appears once Xcode lists the watch. Connect the iPhone by USB, unlock both devices, tap **Trust** on the
   watch if it asks, and keep Window › Devices and Simulators open until the watch is listed. Then look again.
2. Still missing? `tools/watch_devmode.py reveal` asks the watch to show it, through the iPhone on USB. It needs
   [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) (GPL-3.0, not part of Chums) and both devices'
   UDIDs, which `xcrun xctrace list devices` shows:

   ```bash
   python3 -m venv ~/.chums/venv && ~/.chums/venv/bin/pip install pymobiledevice3
   CHUMS_PHONE_UDID=<iPhone UDID> CHUMS_WATCH_UDID=<watch UDID> ~/.chums/venv/bin/python tools/watch_devmode.py reveal
   ```

   Then turn the switch on as above, restarting from the watch's own prompt.

**How to know it worked:** `bin/chums-doctor` shows `Apple Watch <name> …: paired with this Mac, Developer Mode on`,
and lists the iPhone with `Developer Mode enabled`.

## 9. Build and install the apps

```bash
bin/chums-install
```

What it does:

1. Finds the watch with `xcrun devicectl list devices`, and stops with instructions if Xcode doesn't know one or its
   Developer Mode is off. It also finds the iPhone, for the iPhone app.
2. Writes `app/ChumsWatch/HubConfig.swift` from `~/.chums/config.json`: the public URL and the watch token
   (`tools/gen-config.sh`). The file is git-ignored; never commit it or share a built app, since the token can be read
   from it.
3. Picks the signing team (`tools/pick-team.py`): `"team"` in config.json or `CHUMS_TEAM` if set, else a paid team in
   Xcode, else your free Personal Team.
4. Picks the bundle ID: `"bundleId"` in config.json or `CHUMS_BUNDLE` if set, else `dev.chums.<team ID>` (the team
   ID in lowercase). A bundle ID belongs to the team that registered it first, so the default includes your team's
   ID. The iPhone app is `<bundle ID>`, its widgets `<bundle ID>.widgets`, the watch app `<bundle ID>.watchkitapp` and
   the watch's widget `<bundle ID>.watchkitapp.widget`.
5. Generates the Xcode project with XcodeGen and builds it in Release with automatic signing
   (`-allowProvisioningUpdates`). The first build takes a few minutes.
6. Installs the watch app with `xcrun devicectl device install app`. The wireless connection to the watch often drops
   the first attempt or two, so it tries up to 5 times. Keep the watch unlocked and awake.
7. Opens Chums on the watch.
8. Installs the iPhone app on the iPhone (skipped, with a note, when Xcode doesn't know the iPhone or its Developer
   Mode is off). The watch app is inside it, so it goes on after the watch has its copy.

Keep the bundle ID once Chums is installed: if it changes (another team, or the default changed), the next install is a
second copy of the app. To pin it, add the one you have to `~/.chums/config.json`:

```json
"bundleId": "dev.chums.abcde12345"
```

With a free Personal Team, the install stops working after 7 days; `bin/chums-install` prints the date. Run it again
before then.

If the build stops at "Your team has no devices from which to generate a provisioning profile", see
[troubleshooting.md](troubleshooting.md#your-team-has-no-devices).

**How to know it worked:** it prints `Chums is running on the watch.` and `Chums is installed on <your iPhone>.`, and
the watch shows a character, not "HUB OFFLINE" (it says "NOT RUNNING" until its agent starts in step 10).
`bin/chums-doctor` shows `the watch app (built …) has the hub's current token and address`.

## 10. Start the agents

Every character on the watch is its own agent. On its first start (step 4) the hub wrote eight to
`~/.chums/agents.json`, one per character: `noodle`, `stretch`, `peeps`, `squint`, `ray`, `tangle`, `crunch` and
`nana`. All start on Claude Code, each working in `~/.chums/agents/<id>` with access to your home folder. To give one
other folders, edit its `cwd` and `addDirs` ([Background agents](#background-agents)).

**Claude Code agents** run in the background, one LaunchAgent each. They run through a small Mac app, Chums.app,
which this builds, signed with your Apple Development certificate for the same team as the watch app, so it keeps its
permissions across rebuilds ([why](#permissions-on-the-mac)). Then:

```bash
bin/chums-agents install
```

A session's first start shows two screens: trust the folder, and confirm loading the development channel (channels
are a research preview, so Claude Code asks). `bin/chums-agents` answers both. Each agent takes about 200 MB of memory
while it waits; `bin/chums-agents stop <id>` stops one you don't use. Then grant the agents their permissions once, at
the Mac: [Permissions on the Mac](#permissions-on-the-mac).

**Codex agents.** Switch an agent to Codex on the watch (open the agents list, swipe the character's row left (Edit),
pick **Runs on: Codex**) or on its card in the iPhone app (**Runs on**). The hub stops its Claude Code session and runs
`codex app-server` for it instead; its soul stays, and each runtime keeps its own thread for when you switch back.
Codex has to be installed and signed in on the Mac. If you use only Codex, skip `bin/chums-agents install` and switch
the agents you want; the others show as not running, and `bin/chums-doctor` reports Claude Code as missing while any
agent is on it. An agent's model and other settings:
[other-agents.md](other-agents.md#agentsjson). To watch it work or type to it on the Mac: `bin/chums-codex <id>`
opens a Codex terminal on the same thread.

**One agent in a terminal.** `bin/chums-agents open <id>` takes a Claude Code agent's session into this terminal; it
goes back to the background when you quit. To start a new session for an agent in another folder, stop its
LaunchAgent (`bin/chums-agents stop <id>`), then:

```bash
cd ~/some/project && /path/to/chums/bin/chums-claude <id>
```

`<id>` is one of the ids above: the watch and the iPhone talk only to the agents in `agents.json`, and a session is an
agent's when its name is the agent's id. `bin/chums-claude` adds the Chums channel and hooks, keeps Remote Control on
(`"remoteControl": false` in `~/.chums/config.json` turns it off), keeps the project's own `.mcp.json`, and lets the session call `chums_reply` and read
the files you send from the iPhone (`~/.chums/uploads`) without asking. Its
first start shows the two screens above; answer them in the terminal.

To restart the hub: Ctrl-C and `bin/chums-hub` in its terminal, or
`launchctl kickstart -k gui/$UID/dev.chums.hub` when it runs as a LaunchAgent.

**How to know it worked:** `bin/chums-agents status` shows each Claude Code agent `running`. On the watch, tap the
faces at the top left: the agents are in the list, not marked "Not running on your Mac". `bin/chums-doctor` lists each
under "4. The hub" as `idle`.

## 11. Talk to it from the watch

1. The first time Chums opens, the watch asks for the microphone, for notifications, and for Health › Workouts:
   allow all three. Notifications bring approvals, questions and finished work when Chums isn't in front; Workouts is
   for [keyring mode](#keyring-mode).
2. Hold the screen anywhere, say what you want, and let go. Slide onto × before letting go to cancel. A clip stops by
   itself after 30 seconds.
3. The hub transcribes the clip on the Mac and sends it to the agent on screen (its face is at the top left, in front
   of the others'). Everything you say goes to that agent; to talk to another one, tap the faces and pick it in the
   list.
4. When the agent asks for permission, a card shows the request: hold the card to allow it, or tap × to deny it. You
   can also say "yes" or "no".
5. The agent answers in one short sentence, spoken on the watch and kept in the conversation (pull it up from the
   bottom).

**How to know it worked:** the character goes from listening to thinking to working to done, and you hear the reply.
The hub logs each clip: `utterance … stt=…ms: "what you said" -> order`.

## The watch app's settings

Tap the faces at the top left; Settings is below the agents list. In that list, press and hold a row, then drag it, to
change the order.

| Setting | Default | What it does |
| --- | --- | --- |
| Voice: read replies aloud | on | Off: replies are text and a tap on the wrist |
| Watch voice | | The watch's own voice, for replies the Mac doesn't voice ([the agents' voices](#the-agents-voices)). A tap plays a sample |
| Stay on while held | on | While you hold the watch facing you, the screen stays on, up to 10 minutes without a touch. Put down, it sleeps after 20 seconds |
| Keyring: stay on | on | [Keyring mode](#keyring-mode) |
| Demo: play every state | off | The character plays every state in turn |

## The iPhone app

`bin/chums-install` puts it on the iPhone in step 9. It has the same agents, conversations and voices as the watch,
through the same hub. It talks to the hub only while it is open: an agent that needs you while it is closed shows on
the widgets and the watch, not as an iPhone notification. Open Chums on the iPhone:

- The screen is for one agent. While its conversation is empty, it stands in the middle in a window the shape of the
  watch's screen, with its name and what it's doing below, and takes the same touches: tap to poke, stroke to pet,
  hold to talk. The crown on the window's side turns like the watch's Digital Crown: drag it up or down, or flick it.
  A two-finger twist on the window turns it too. Tilting or shaking the iPhone moves it, as on the watch.
- Once there's a conversation, the agent is its last row, at the left, and its newest line arrives right above it;
  it scrolls with the conversation. Its name is at the top. Beside it, two lines say what it's doing:
  - at work, the action (Thinking, Looking at your photo, Reading a file, Running tests, Running a command, Searching
    the web, Running a helper agent, Finishing up), then exactly what on and how long it has been at it: `npm test · 1:04`, `photo-1.jpg ·
    0:42`. A command shows alone, in the code face: `npm test` for the hub's "Bash npm test";
  - otherwise Needs you (with what it asks: "Asks to read photo-1.jpg"), Speaking (a tap stops it), Listening,
    Sending your photo, Stuck, Rate limited, Not running on your Mac, or Can't reach your Mac;
  - idle, nothing.

  A tap on the agent brings it to the middle, in front of the conversation; a tap outside it, or a drag down, puts it
  back. Press and hold it to open its card.
- The button at the top left shows the other agents' faces. A tap on it, or a swipe in from the left edge, opens all
  the agents in a panel; a tap outside it or a swipe left closes it. Each tile shows the agent's last line when it is
  idle, and what it's doing otherwise. A ring around its face: white working, amber needs you or rate limited, red
  stuck; a dimmed face isn't running. A tap talks to one. Press and hold a tile, then drag it, to change the order.
- The agent's card opens from a tap on its name at the top, from … on its tile, or from … beside its name when it's in
  front. Cards slide up from the bottom; drag one down to put it away. On the card:
  - **Runs on**: Claude Code or Codex. The hub stops the one and starts the other, as Runs on does on the watch
    ([step 10](#10-start-the-agents)). One that isn't installed on the Mac is dimmed.
  - **Model**: Claude Code's models (Fable, Opus, Sonnet, Haiku) or the ones Codex lists for your account, after
    Default (what Claude Code or Codex is set to use on the Mac). The agent restarts on the one you pick, on the same
    conversation; when it is working, the app asks first.
  - **Permissions**: how it asks before acting ([what it may do](#what-an-agent-may-do)).
  - **Voice**: the voice it reads its replies in ([the agents' voices](#the-agents-voices)). A tap plays a sample and
    picks it.
  - **Soul**: its name, what it does, what it hands off to which agent, how it talks, and notes. Tap one to edit it,
    then Save. A typed change is saved as you wrote it, with no model call. "Undo the last change" goes back
    one.
- Type a message, or talk: tap the microphone at the right of the box, talk, then ↑ to send or × to throw it away; or
  hold it while you talk and let go to send (slide left first to cancel). The first tap asks for the microphone; tap
  again to talk. A tap anywhere else puts the keyboard away.
- + at the left of the box adds photos (the camera or the library, up to 6 at a time) and files (up to 25 MB each); a
  tap or a scroll anywhere else closes it. They wait above the box, each with × to take it out, and go to the Mac
  with your next message, kept in `~/.chums/uploads`. The agent gets their paths and reads them without asking (Claude
  Code agents may read `~/.chums/uploads`), and a picture of each shows in the conversation: a page, a document, a PDF,
  text or code, a table, an image, or a still from a video.
- A reply to what you sent from the iPhone can be a few plain sentences (60 words at most), since the iPhone shows the
  text; a reply to the watch stays one short line.
- What an agent shows you opens on a card, live where the iPhone can: an HTML page it made runs (a chart you can
  drag across, tabs, animations), a web page loads, a PDF scrolls page by page, Markdown, text and tables scroll, a
  video plays, and Word, Excel, Pages, Keynote and other documents open in Quick Look. Anything else is its picture:
  pinch and drag to look closer, double-tap to zoom in or out. Drag the card down to close it; Share (top right) sends
  the original file, or the page's address.
- Press and hold a message to copy it; on the agent's, Mute replies stops reading replies aloud (and brings it back).
- When the agent asks for permission, a card shows the request with Allow and Deny. Saying "yes" or "no" answers it
  too.
- The dots at the top right open the app's settings: the connection to your Mac (the address, how fast it answers,
  and Check the connection), reading replies aloud, and haptics. After you've changed the agents' order, a button
  there puts it back.

A reply is spoken on the device you asked from: the iPhone speaks what you said on the iPhone, the watch what you said
on the watch. Both show every line.

Widgets (Home Screen: touch and hold, then Edit › Add Widget › Chums. Lock Screen: touch and hold, then Customize):

- **Agent** (small and medium; on the Lock Screen, circular, rectangular and inline): one agent, or, when none is
  picked (touch and hold the widget › Edit Widget), the agent last talked to from any device or shown in the app. The
  small one is the watch's screen for that agent, with a microphone in the corner that opens the app listening; when
  the agent asks for permission, ✕ and ✓ there answer it without opening the app. The medium one adds its name, what
  it's doing and its last line, with Talk, or Deny and Allow, below them. A tap anywhere else opens the agent.
- **Agents** (medium, up to 5 agents; large, up to 9): the agents, the ones that need you first. A tap opens that
  agent. The large one also shows the first open request, with ✕ and Allow.

The widgets refresh every 5 minutes while an agent needs you or is working, otherwise every 15 (iOS can space them
out more), and when the app changes agents, goes to the background, or sees the hub's state change.

The **Talk to Chums** control opens Chums listening to the agent on screen. Add it in Control Center, on the Lock
Screen, or to the Action Button (Settings › Action Button › Controls).

Siri and Shortcuts: "Ask Chums" (or "Ask <agent> in Chums") sends what you say to an agent and reads its next line
back. It waits up to 45 seconds; after that, the answer is in the app. "Talk to Chums" opens the app listening. In
the Shortcuts app they are the actions Ask an agent and Talk to an agent.

**How to know it worked:** the agent's state shows under its name in the middle (or beside it in the conversation),
not "Can't reach your Mac", and a typed message gets an answer spoken on the iPhone.

## Keyring mode

Chums can be carried on a keyring instead of worn. Keyring mode ("Keyring: stay on" in the watch app's settings, on by
default) keeps Chums in front and running: it runs a workout session, the one thing watchOS lets keep an app frontmost
when the screen dims. No workout is saved to Health or Fitness.

1. Allow Health › Workouts when Chums asks. watchOS asks once. If it was refused, see
   [troubleshooting.md](troubleshooting.md#keyring-mode-doesnt-stay-on).
2. On the watch: Settings › Passcode › Wrist Detection off, so it doesn't lock off a wrist.
3. Settings › General › Return to Clock › Chums › After 1 hour, and Return to App (When in Session) on.
4. Settings › Display & Brightness › Always On on. For a longer lit screen after a tap: Wake Duration › Wake for 70
   Seconds.
5. Add the Chums complication to the watch face, or Chums to the Smart Stack, to open it in one tap.

**How to know it worked:** the screen dims but stays in Chums, and `~/.chums/watch-events.log` on the Mac has
`keyring running`. A problem shows under the switch in the watch app's settings.

## Background agents

Every character is its own agent, with its own soul, session and conversation: a tap on it in the watch's list
talks to it. Each Claude Code agent is a session run in the background by a LaunchAgent:

```bash
bin/chums-agents install     # one LaunchAgent per Claude Code agent; run again after editing agents.json
bin/chums-agents status
bin/chums-agents open <id>   # take one into this terminal; it goes back to the background when you quit
bin/chums-agents stop|start|restart <id>
```

The hub writes one agent per character on its first start (its id is the character's: `noodle`, `squint`, `peeps`…),
each in `~/.chums/agents/<id>` with your home folder. Three get a job in their first soul (Noodle code, Squint your
Mac, Peeps design); the others do whatever you ask, and you shape each one's soul from the watch or the iPhone. Edit
`agents.json` to change their folders (`cwd`, `addDirs`) or tool instructions (`guide`), then run `install` again.
Codex agents (Runs on, on the watch or the iPhone) run inside the hub, not as LaunchAgents. Each Claude Code agent takes about 200 MB of memory while it
waits; `bin/chums-agents stop <id>` stops one you don't use.

On the watch, an agent's page (the agents list, swipe its row left, Edit) has tiles for what it runs on, its model,
its permissions and its voice; each opens a list. Its soul is the text under them, and at the bottom you hold the
button to change it by voice, or undo the last change.

### What an agent may do

Every agent starts the same: its folder and your home folder (`cwd` and `addDirs` in `agents.json`), the Chums tools,
and the right to read the files you send it from the iPhone. How it asks before acting is its **Permissions**, on its
card in the iPhone app or its page on the watch. Picking one restarts it, on the same conversation:

| Claude Code | What it does |
| --- | --- |
| Default | What your Claude Code settings say (`permissions.defaultMode` in `~/.claude/settings.json`) |
| Asks first | Anything it may not do on its own comes to the watch and the iPhone as Allow or Deny |
| Edits on its own | Changes files in its folders without asking; asks before commands |
| Decides on its own | Claude Code's auto mode: it acts, and refuses what looks risky without asking anyone |

| Codex | What it does |
| --- | --- |
| Asks first | Asks before running anything but simple reads |
| Asks when it needs to | Works in its folders and asks to go further (the default) |
| Never asks | Runs without asking, inside its sandbox |

When auto mode refuses an action, the conversation says so ("Auto mode refused: …") with **Ask first instead**, which
switches that agent to Asks first. Without it, a refusal only reaches you as the agent saying it's blocked. The setting
is `permissionMode` (Claude Code) or `approvalPolicy` (Codex) in `agents.json`; Claude Code gets it as
`--permission-mode`, which holds when the agent's session is resumed.

**How to know it worked:** `bin/chums-agents status` shows each one `running`, and the watch's agents list shows them.
Each agent's log: `~/.chums/agents/<id>.host.log`.

## Permissions on the Mac

An agent working while you're away must not stop on a macOS dialog. macOS asks the first time a program reads your
Desktop, Documents or Downloads, takes a screenshot, clicks in another app or controls one ("wants access to control
Safari"), and it asks again after every update of a program it doesn't know by a stable name.

So the hub and the background agents run through one small app, **Chums** (`~/Applications/Chums.app`, built from
`tools/mac-app` by `bin/chums-setup --launchd` and `bin/chums-agents install`). Everything they and their tools ask for
belongs to Chums, under that name and Noodle's icon, and stays granted when Claude Code, Codex or Node.js update.

It needs no paid developer account. Chums.app is signed with your Apple Development certificate for the team the apps
are signed with: `"team"` in `~/.chums/config.json` (or `CHUMS_TEAM`) if set, else the one `tools/pick-team.py` picks,
as `bin/chums-install` does. The free Personal Team has a certificate too, made by Xcode the first time it signs the
watch app ([step 9](#9-build-and-install-the-apps)).

With that certificate, macOS keeps the permissions across rebuilds of Chums.app. With no team found, or no
certificate yet, Chums.app is signed ad hoc: it works the same, but macOS ties the permissions to that one build. Once a certificate exists, the next `bin/chums-setup --launchd` or `bin/chums-agents install` signs Chums.app
with it; grant the permissions again then (they belong to the new signature). The same goes for a rebuild after
`tools/mac-app` changes in an update of Chums, when Chums.app is signed ad hoc.

Grant it once, at the Mac, after [step 10](#10-start-the-agents): open **Chums** from
`~/Applications` (or run `bin/chums-permissions`) and click **Allow All**. It goes one step at a time; what's already
allowed passes without a dialog:

1. **Your folders**: "Chums would like to access files in your Desktop folder", then Documents and Downloads. Click
   Allow on each. (Full Disk Access, the optional last row, covers these too.)
2. **Apps**: "Chums wants access to control Finder", then System Events, then each app in its list that is open right
   now (Safari, Mail, Calendar, Notes, Messages, Reminders, Music, Contacts, Terminal, Chrome), and Codex Computer Use
   when it's installed (Codex's helper, with no window). Click OK on each. Chums opens only apps with no window to ask;
   any other app that isn't open asks once, as Chums, the first time an agent uses it.
3. **Accessibility** (clicking and typing in other apps), then **Screen Recording** (screenshots): macOS shows an alert
   with an Open System Settings button, and Chums is already in the list there. Switch it on. The window sees the
   switch and goes on by itself. After Screen Recording (on macOS 15 and later "Screen & System Audio Recording"),
   macOS may offer to quit and reopen Chums: click Later. Then Chums takes one screenshot, the way the agents do, and
   macOS asks once more: "Chums is requesting to bypass the system private window picker". Click Allow.

At the end the agents start again, so one that was refused something before has everything. **Full Disk Access** is
optional (also Mail, Messages and Safari data, iCloud Drive, other disks): Open Settings shows the list and Chums in
Finder; drag Chums into the list. Entries named `expect`, `caffeinate`, `node`, `tailscaled` or `claude` left in those
lists from before can be removed.

**How to know it worked:** every row in Chums's window shows Allowed (Full Disk Access is optional).
`bin/chums-permissions check` and `bin/chums-doctor` show the same from Terminal. A Claude Code agent you start in a
terminal (`bin/chums-claude`) still asks as that terminal app.

## The agents' voices

Each agent reads its replies in its own voice, made on the Mac by Kokoro, an open speech model (82M parameters,
Apache-2.0) that runs on the Mac's GPU. Nothing goes to a server. `bin/chums-setup` installs it when
[uv](https://docs.astral.sh/uv/) is installed (`brew install uv`): its Python in `~/.chums/kokoro` (about 1.1 GB), and
the model and its voices in Hugging Face's cache, `~/.cache/huggingface` (about 0.35 GB). The hub starts it. It needs
Apple Silicon; on an Intel Mac, or until it's installed, the watch reads replies with its own voice.

To change an agent's voice: on the watch, swipe its row left in the agents list (Edit), then **Voice**; or on its card
in the iPhone app, **Voice**. A tap plays a sample and picks it. There are 28 English voices: 20 American, 8 British.

**How to know it worked:** `bin/chums-doctor` shows "the agents' voices (Kokoro) answer", and the hub log has a
`speech kokoro <voice> <ms>` line for each reply.

## No watch: the Simulator

```bash
bin/chums-sim
```

It builds the app for the watchOS Simulator (no signing, no Apple ID), creates a simulator named "Chums Watch" if
needed, and runs Chums in it. The hub has to have started once (`bin/chums-hub`). The Simulator app tries the public
URL first, if there is one, then the hub on `127.0.0.1:7717`. It needs the watchOS Simulator runtime
(`xcodebuild -downloadPlatform watchOS`, several GB). Launch arguments play every state (`-demo YES`) and show a
character whoever you talk to (`-testCharacter`, for that launch only):

```bash
xcrun simctl launch "Chums Watch" dev.chums.watchkitapp -demo YES -testCharacter squint
```

The app's ID is `dev.chums.watchkitapp`, or `<bundleId>.watchkitapp` when `~/.chums/config.json` sets `bundleId`.

Shut the simulator down when you're done (`xcrun simctl shutdown "Chums Watch"`): a simulator left running without a
window plays the watch's taps as sounds on the Mac.

## Settings

Each one is an environment variable, or a key in `~/.chums/config.json`, or the default.

| Variable | config.json | Default | What it sets |
| --- | --- | --- | --- |
| | `port` | `7717` | The hub's local port |
| | `publicPort` | `7718` | The watch API's port (what Funnel forwards to) |
| | `publicURL` | set by `bin/chums-tunnel` | The address built into the watch app |
| | `ownerName` | `the user` | What the agents call you, e.g. `"Sam"` |
| | `diagnostics` | `false` | `true`: the apps log their frame rate and memory to the hub every 30 s (for working on them; run `bin/chums-install` after) |
| `CHUMS_TEAM` | `team` | picked by `tools/pick-team.py` | Apple developer team for signing |
| `CHUMS_BUNDLE` | `bundleId` | `dev.chums.<team>` (device), `dev.chums` (Simulator) | The app's bundle ID |
| `CHUMS_LABEL_PREFIX` | `launchdPrefix` | `dev.chums` | LaunchAgent labels (`<prefix>.hub`, `<prefix>.tailscaled`, `<prefix>.agent.<id>`) |
| `CHUMS_NODE` | `node` | `node` on your PATH | The node binary LaunchAgents run |
| `CHUMS_WHISPER_MODEL` | | `~/Documents/huggingface/models/argmaxinc/whisperkit-coreml/openai_whisper-base` | Whisper model folder |
| `CHUMS_CLAUDE_BIN` | | `claude` in `~/.local/bin`, `~/.npm-global/bin` or PATH | The claude CLI for the soul editor |
| `CHUMS_NO_RC` | `remoteControl` | on | `"remoteControl": false` starts every Claude Code session without Remote Control (for an API key); `CHUMS_NO_RC=1` does it for the sessions started from that shell |
| | `tts` | `{ "engine": "kokoro" }` when installed | The voice replies are read in: `kokoro` (each agent's own), `say` (a macOS voice), `openai`, or `watch` |
| `DEVELOPER_DIR` | | `/Applications/Xcode.app/Contents/Developer` | The Xcode the scripts use |

Restart the hub after changing `config.json`. Run `bin/chums-install` again after changing `publicURL`, the tokens,
`team` or `bundleId`, since those are built into the watch app.

## Files Chums writes

| Path | What |
| --- | --- |
| `~/.chums/config.json` | Ports, tokens, public URL (mode 0600) |
| `~/.chums/agents.json`, `~/.chums/agents/` | The agents, their folders and logs |
| `~/.chums/souls/` | Each agent's soul, a git repository |
| `~/.chums/artifacts/` | The last 60 things sessions showed and you sent: their pictures, and for the iPhone the files as they were (up to 25 MB) and the pages the hub made of them |
| `~/.chums/uploads/` | The last 40 photos and files sent from the iPhone |
| `~/.chums/conversation.json` | The last 40 lines of each agent's conversation |
| `~/.chums/hub.log`, `~/.chums/watch-events.log` | The hub's log (under launchd), and what the watch and the iPhone report (a new file past 10 MB) |
| `~/.chums/watch-battery.csv` | The watch's battery level, a line every 5 minutes or 1% change |
| `~/.chums/agents/<id>.runtime.json` | A Codex agent's running `app-server` (its process and socket) |
| `~/.chums/bin/page-shot`, `pdf-shot`, `ql-shot` | What makes the pictures of pages, PDFs and other documents, compiled from `tools/page-shot.swift`, `tools/pdf-shot.swift` and `tools/ql-shot.swift` on first use |
| `/tmp/chums-<uid>/` | The Codex agents' sockets (only your user can open the folder) |
| `$TMPDIR/chums-speech/` | Spoken replies, as audio files, while they're recent |
| `~/.chums/tailscale/` | Chums' `tailscaled` state and log |
| `~/.chums/kokoro/` | The agents' voices: Kokoro's Python (`bin/chums-setup`) |
| `~/.cache/huggingface/hub/models--mlx-community--Kokoro-82M-bf16/` | Kokoro's model and voices (`bin/chums-setup`) |
| `~/Documents/huggingface/models/argmaxinc/whisperkit-coreml/openai_whisper-base/` | The Whisper model (`bin/chums-setup`; `CHUMS_WHISPER_MODEL` moves it) |
| `~/Library/LaunchAgents/dev.chums.*.plist` | The hub's and `tailscaled`'s (`bin/chums-setup --launchd`), and one per Claude Code agent (`bin/chums-agents install`) |
| `~/Applications/Chums.app` | The app the hub and the agents run through, so their permissions are Chums's ([permissions](#permissions-on-the-mac)) |
| `app/ChumsWatch/HubConfig.swift`, `channel/mcp.json`, `channel/hooks.json` | Generated in the checkout; git-ignored |

## Updating

```bash
git pull
bin/chums-setup          # new npm packages, if any
```

Then restart the hub, run `bin/chums-agents install` (it restarts the agents and rebuilds Chums.app when
`tools/mac-app` changed), and run `bin/chums-install` to update the watch and iPhone apps. `bin/chums-doctor` confirms
the chain.

## Removing Chums

1. Stop the hub.
2. For each LaunchAgent in `~/Library/LaunchAgents/dev.chums.*`: `launchctl bootout gui/$UID/<label>`, then delete
   the plist.
3. Take the watch API off the internet: `tailscale --socket ~/.chums/tailscale/tailscaled.sock funnel reset`, and
   remove the `chums-hub` machine in the Tailscale admin console.
4. Delete `~/.chums` and `~/Applications/Chums.app`, then remove Chums from System Settings › Privacy & Security
   (Full Disk Access, Screen & System Audio Recording, Accessibility, Automation).
5. Delete the models, if nothing else uses them: the Whisper model in `~/Documents/huggingface/models/argmaxinc`, and
   Kokoro's in `~/.cache/huggingface/hub/models--mlx-community--Kokoro-82M-bf16`.
6. Delete Chums from the watch: touch and hold the app list, tap Edit Apps, then the delete button on Chums. Or from
   the Mac: `xcrun devicectl device uninstall app --device "<watch name>" <bundle ID>.watchkitapp`.
7. Delete Chums from the iPhone: touch and hold its icon, then Remove App.
