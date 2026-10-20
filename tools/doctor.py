"""Checks the whole Chums chain on this Mac and prints a pass/fail list, with the fix for each failure.

Run it as bin/chums-doctor. It is read-only: it starts, stops, changes and installs nothing (devicectl's list of
devices passes through a temporary file). What it does:
  - runs version and sign-in checks (`claude auth status`, `codex login status`, `xcodebuild -version`, ...);
  - reads ~/.chums/config.json and ~/.chums/agents.json;
  - asks the hub for /v1/ping and /v1/state on 127.0.0.1, and the Funnel URL for /v1/ping over HTTPS;
  - asks Chums' own tailscaled for its status, and Xcode (`xcrun devicectl list devices`) which devices it knows.
The tokens in ~/.chums/config.json go only to your own hub and your own Funnel URL, and are never printed.
Exit code: 0 when nothing failed, 1 otherwise. NO_COLOR=1 turns colours off.
"""
import ipaddress, json, os, platform, re, shutil, socket, subprocess, sys, tempfile, time
import urllib.error, urllib.request

if {'-h', '--help'} & set(sys.argv[1:]):
    print(__doc__.strip()); sys.exit(0)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser('~')
CHUMS = os.path.join(HOME, '.chums')
CONFIG = os.path.join(CHUMS, 'config.json')
AGENTS = os.path.join(CHUMS, 'agents.json')
TS_SOCK = os.path.join(CHUMS, 'tailscale', 'tailscaled.sock')
DEV = os.environ.get('DEVELOPER_DIR') or '/Applications/Xcode.app/Contents/Developer'
MODEL = os.environ.get('CHUMS_WHISPER_MODEL') or os.path.join(
    HOME, 'Documents/huggingface/models/argmaxinc/whisperkit-coreml/openai_whisper-base')
WHISPER_PORT = 50061
KOKORO_PORT = 50062
HUBCONFIG = os.path.join(ROOT, 'app/ChumsWatch/HubConfig.swift')
# where installers put the CLIs, for when they aren't on this shell's PATH
EXTRA_BIN = [os.path.join(HOME, '.local/bin'), os.path.join(HOME, '.npm-global/bin'), '/opt/homebrew/bin', '/usr/local/bin']

COLOR = sys.stdout.isatty() and not os.environ.get('NO_COLOR')
TAGS = {'PASS': '32', 'WARN': '33', 'FAIL': '31'}
count = {'PASS': 0, 'WARN': 0, 'FAIL': 0}


def report(kind, what, fix=None):
    count[kind] += 1
    tag = f'\033[{TAGS[kind]}m{kind}\033[0m' if COLOR else kind
    print(f'  {tag}  {what}')
    fixes = [fix] if isinstance(fix, str) else list(fix or [])
    for i, line in enumerate(fixes):
        print(('        fix: ' if i == 0 else '             ') + line)


def ok(what): report('PASS', what)
def warn(what, fix=None): report('WARN', what, fix)
def fail(what, fix=None): report('FAIL', what, fix)
def note(what): print(f'  --    {what}')


def section(title):
    print(f'\n{title}')


def run(cmd, timeout=20, stdin='', env=None):
    """(exit code, stdout, stderr); 127 when the command is missing, 124 on a timeout."""
    # the usual install folders go on PATH too, as the hub gives them to the agents it runs (npm CLIs need node)
    path = ':'.join([os.environ.get('PATH', '')] + EXTRA_BIN)
    try:
        p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout,
                           env=dict(os.environ, PATH=path, **(env or {})))
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError:
        return 127, '', f'{cmd[0]}: not found'
    except subprocess.TimeoutExpired:
        return 124, '', f'{cmd[0]}: no answer in {timeout} s'


def version(text):
    m = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', text or '')
    return tuple(int(x or 0) for x in m.groups()) if m else None


def vstr(v): return '.'.join(map(str, v[:2] if len(v) > 2 and v[2] == 0 else v))


def find(name, extra=()):
    """(path, on PATH?) for a command, looking in the usual install folders too."""
    p = shutil.which(name)
    if p: return p, True
    for d in list(extra) + EXTRA_BIN:
        c = os.path.join(d, name)
        if os.access(c, os.X_OK): return c, False
    return None, False


def read_json(path):
    with open(path, encoding='utf-8') as f: return json.load(f)


def http(url, token, timeout=4):
    """(status, parsed JSON or None, error) for a GET to the hub on this Mac. No proxies."""
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as r:
            body = r.read()
            try: return r.status, json.loads(body), None
            except ValueError: return r.status, None, None
    except urllib.error.HTTPError as e:
        return e.code, None, None
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
        return None, None, str(getattr(e, 'reason', e))


def port_open(port, host='localhost'):           # whisperkit-cli serve listens on ::1
    try:
        with socket.create_connection((host, port), timeout=1): return True
    except OSError: return False


def launchd_loaded(label):
    return run(['launchctl', 'print', f'gui/{os.getuid()}/{label}'], timeout=5)[0] == 0


# ------------------------------------------------------------------------------------------------------------------
cfg, agents, hub_up, team_kind = None, None, False, None
label_prefix = os.environ.get('CHUMS_LABEL_PREFIX')

print('Chums doctor: read-only checks of everything Chums needs. Nothing is changed.')
print(f'checkout: {ROOT}')

# ---------- the settings first: later checks depend on them ----------
config_problem = None
if os.path.isfile(CONFIG):
    try: cfg = read_json(CONFIG)
    except ValueError as e: config_problem = str(e)
agents_problem = None
if os.path.isfile(AGENTS):
    try: agents = read_json(AGENTS)
    except ValueError as e: agents_problem = str(e)
label_prefix = label_prefix or (cfg or {}).get('launchdPrefix') or 'dev.chums'
runtimes = [(a.get('runtime') or 'claude') for a in agents if isinstance(a, dict)] if isinstance(agents, list) else []
need_claude = not runtimes or 'claude' in runtimes
need_codex = 'codex' in runtimes

# ---------- 1. this Mac ----------
section('1. This Mac')
mac = version(platform.mac_ver()[0])
arm = run(['sysctl', '-n', 'hw.optional.arm64'], timeout=5)[1] == '1'
if mac and mac >= (15, 6):
    (ok if arm else warn)(f'macOS {vstr(mac)} on {"Apple silicon" if arm else "an Intel Mac"}'
                          + ('' if arm else ': Chums is made for Apple silicon Macs and is untested on Intel'))
else:
    fail(f'macOS {vstr(mac) if mac else "?"}: Xcode 26 needs macOS 15.6 or later', 'System Settings › General › Software Update')
ok(f'python3 {platform.python_version()}')

node = os.environ.get('CHUMS_NODE') or (cfg or {}).get('node') or find('node')[0]
if node and os.access(node, os.X_OK):
    nv = version(run([node, '-p', 'process.versions.node'], timeout=10)[1])
    if nv and nv >= (20, 11): ok(f'Node.js {vstr(nv)} ({node})')
    else: fail(f'Node.js {vstr(nv) if nv else "?"} is too old: Chums needs 20.11 or later', 'brew install node')
else:
    fail('Node.js is not installed (the hub and the channel run on it)', 'brew install node')

if all(os.path.isdir(os.path.join(ROOT, 'node_modules', p)) for p in ('@modelcontextprotocol/sdk', 'zod')):
    ok('npm packages installed')
else:
    fail('npm packages are not installed in this checkout', 'bin/chums-setup (it runs npm ci)')

wk = find('whisperkit-cli')[0]
if wk: ok(f'whisperkit-cli ({wk})')
else: fail('whisperkit-cli is not installed (speech to text on the Mac)', 'brew install whisperkit-cli')
if os.path.isfile(os.path.join(MODEL, 'config.json')) or os.path.isdir(os.path.join(MODEL, 'AudioEncoder.mlmodelc')):
    ok('Whisper base model downloaded')
else:
    fail(f'Whisper model not found at {MODEL}',
         ['bin/chums-setup downloads it (about 150 MB)', 'or set CHUMS_WHISPER_MODEL to the folder of a model you have'])

ff = find('ffmpeg')[0]
if ff: ok(f'ffmpeg ({ff})')
else: fail('ffmpeg is not installed (the hub converts each clip with it before transcribing)', 'brew install ffmpeg')

ts, ts_on_path = find('tailscale')
tsd = find('tailscaled')[0]
if ts and tsd:
    tv = version(run([ts, 'version'], timeout=10)[1])
    if tv and tv < (1, 52): fail(f'Tailscale {vstr(tv)} is too old: bin/chums-tunnel needs 1.52 or later', 'brew upgrade tailscale')
    else: ok(f'Tailscale {vstr(tv) if tv else ""} (tailscale and tailscaled)')
elif ts:
    fail('tailscaled is missing: Chums runs its own tailscaled, which the App Store and standalone Tailscale apps '
         "don't include", 'brew install tailscale')
else:
    fail('Tailscale is not installed (it puts the watch API on the internet)', 'brew install tailscale')

if os.access('/usr/bin/expect', os.X_OK): ok('expect (runs background Claude Code agents)')
else: warn('/usr/bin/expect is missing: only bin/chums-agents needs it')
if not find('brew')[0]: note('Homebrew is not installed; the install commands below use it (https://brew.sh)')

# ---------- 2. the agents' CLIs ----------
section('2. Coding agents')
claude, claude_on_path = find('claude', [os.path.dirname(os.environ['CHUMS_CLAUDE_BIN'])] if os.environ.get('CHUMS_CLAUDE_BIN') else [])
if claude:
    cv = run([claude, '--version'], timeout=20)[1].split('\n')[0].replace(' (Claude Code)', '')
    # only when this version has `claude auth`: an older one would read "auth status" as a prompt
    auth = None
    if re.search(r'^\s+auth\b', run([claude, '--help'], timeout=20)[1], re.M):
        try: auth = json.loads(run([claude, 'auth', 'status', '--json'], timeout=30)[1])
        except ValueError: pass
    where = '' if claude_on_path else f' (at {claude}, not on PATH)'
    if auth is None:
        warn(f'Claude Code {cv}{where}: could not check its sign-in (claude auth status needs a newer Claude Code)',
             'claude update')
    elif auth.get('loggedIn'):
        method = auth.get('authMethod') or 'signed in'
        ok(f'Claude Code {cv}, signed in ({method}){where}')
        if method != 'claude.ai':
            note('Remote Control (the session also showing in the Claude app) needs a claude.ai login; '
                 'with an API key, set "remoteControl": false in ~/.chums/config.json')
    else:
        (fail if need_claude else warn)(f'Claude Code {cv} is installed but not signed in{where}',
                                         'run claude, then /login (a Pro, Max, Team or Enterprise plan, or a Console API key)')
    if not claude_on_path:
        warn(f'claude is not on PATH: bin/chums-claude runs "claude" from PATH', f'add {os.path.dirname(claude)} to PATH in ~/.zshrc')
elif need_claude:
    fail('Claude Code is not installed' + (' (agents.json has Claude Code agents)' if runtimes else ''),
         ['curl -fsSL https://claude.ai/install.sh | bash', 'then run claude and sign in'])
else:
    note('Claude Code is not installed: only Claude Code agents and changing a soul by voice need it')

codex_cmds = [a['command'][0] for a in agents if isinstance(a, dict) and a.get('runtime') == 'codex'
              and isinstance(a.get('command'), list) and a['command']] if isinstance(agents, list) else []
codex = codex_cmds[0] if codex_cmds and os.access(codex_cmds[0], os.X_OK) else find('codex')[0]
if codex:
    cxv = version(run([codex, '--version'], timeout=20)[1])
    # only when this version has `codex login status`: on an older one, `codex login` would start a sign-in
    has_status = re.search(r'^\s+status\b', run([codex, 'login', '--help'], timeout=20)[1], re.M)
    rc, out, err = run([codex, 'login', 'status'], timeout=20) if has_status else (1, '', 'no "codex login status" in this version')
    signed = rc == 0 and 'not logged in' not in (out + err).lower()
    label = f'Codex CLI {vstr(cxv)}' if cxv else f'Codex CLI ({codex}, its version unknown)'
    if cxv and cxv < (0, 160):
        warn(f'{label}: Chums was written against 0.160 (its app-server protocol changes between releases)',
             'npm install -g @openai/codex@latest (or brew upgrade --cask codex)')
    said = ((out or err).splitlines() or ['signed in'])[0]          # "Logged in using ChatGPT"
    if signed: ok(f'{label}, {said[0].lower()}{said[1:]}')
    else: (fail if need_codex else warn)(f'{label} is installed but not signed in', 'codex login')
elif need_codex:
    fail('Codex CLI is not installed (agents.json has Codex agents)', ['npm install -g @openai/codex (or brew install --cask codex)', 'then codex login'])
else:
    note('Codex CLI is not installed: only Codex agents ("runtime": "codex") need it')
if not claude and not codex:
    fail('No coding agent: Chums needs Claude Code, Codex, or both', 'docs/setup.md, "Pick your agent"')

# ---------- 3. Chums' settings ----------
section('3. Settings (~/.chums)')
if config_problem:
    fail(f'~/.chums/config.json is not valid JSON ({config_problem})',
         ['fix the file by hand, or move it away and start the hub (it writes a new one with new tokens;',
          'then run bin/chums-install again so the watch app gets the new token)'])
elif cfg is None:
    fail('~/.chums/config.json does not exist yet', 'start the hub once: bin/chums-hub (it writes the file with two new tokens)')
else:
    mode = os.stat(CONFIG).st_mode & 0o777
    if mode & 0o077: warn(f'~/.chums/config.json is readable by other users (mode {oct(mode)[2:]}); it holds the tokens', 'chmod 600 ~/.chums/config.json')
    dmode = os.stat(os.path.dirname(CONFIG)).st_mode & 0o777
    if dmode & 0o077: warn(f'~/.chums is open to other users (mode {oct(dmode)[2:]}); it holds your conversations and uploads', 'chmod 700 ~/.chums (the hub does it when it starts)')
    if cfg.get('token') and cfg.get('watchToken'): ok(f'~/.chums/config.json: ports {cfg.get("port", 7717)} and {cfg.get("publicPort", 7718)}, both tokens set (not shown)')
    else: fail('~/.chums/config.json is missing a token', ['restart the hub: it adds the missing token', 'then bin/chums-install, so the watch app gets it'])
    if cfg.get('publicURL'): ok(f'public URL {cfg["publicURL"]}')
    else: fail('no public URL yet: the watch reaches the hub only through it (the Simulator does not need it)', 'bin/chums-tunnel')
    if cfg.get('ownerName'): note(f'the agents call you {cfg["ownerName"]} (ownerName)')
    else: note('ownerName is not set: the agents call you "the user" (add "ownerName": "Sam" to config.json)')

# agents.json
def looks():
    try: src = open(os.path.join(ROOT, 'hub/hub.mjs'), encoding='utf-8').read()
    except OSError: return set()
    m = re.search(r"^const LOOKS = \[([^\]]*)\]", src, re.M)
    return set(re.findall(r"'([a-z]+)'", m.group(1))) if m else set()

LOOKS = looks()
RUNTIMES = {'claude', 'codex', 'copilot', 'acp'}
if agents_problem:
    fail(f'~/.chums/agents.json is not valid JSON ({agents_problem})',
         ['fix it (tools/agents.example.json shows the shape), then restart the hub',
          'or move it away: the hub writes one agent per character on its next start'])
elif agents is None:
    warn('~/.chums/agents.json does not exist yet', 'start the hub once: it writes one agent per character')
elif not isinstance(agents, list):
    fail('~/.chums/agents.json must be a list of agents ([ {...}, {...} ])', 'see tools/agents.example.json')
else:
    problems, notes, seen = [], [], set()
    for i, a in enumerate(agents):
        if not isinstance(a, dict): problems.append(f'entry {i + 1} is not an object'); continue
        aid = a.get('id')
        if not isinstance(aid, str) or not aid:
            problems.append(f'entry {i + 1} has no "id"'); continue
        if not re.fullmatch(r'[a-z0-9-]+', aid):
            notes.append(f'{aid}: the watch opens a soul only for ids of lowercase letters, digits and dashes')
        if aid in seen: problems.append(f'{aid}: the id is used twice')
        seen.add(aid)
        rt = a.get('runtime') or 'claude'
        if rt not in RUNTIMES: problems.append(f'{aid}: unknown runtime {rt!r} (claude, codex; experimental: copilot, acp)')
        if LOOKS and aid not in LOOKS: notes.append(f'{aid}: every agent is a character, and its id is the character\'s ({", ".join(sorted(LOOKS))}); the watch doesn\'t list this one')
        cwd = a.get('cwd')
        if not isinstance(cwd, str) or not os.path.isabs(os.path.expanduser(cwd)): problems.append(f'{aid}: "cwd" must be an absolute folder path')
        elif not os.path.isdir(cwd) and not cwd.startswith(os.path.join(CHUMS, 'agents')):
            notes.append(f'{aid}: its folder {cwd} does not exist')
        for d in a.get('addDirs') or []:
            if not os.path.isdir(d): notes.append(f'{aid}: addDirs folder {d} does not exist')
        if rt == 'codex':
            if a.get('approvalPolicy') not in (None, 'untrusted', 'on-request', 'on-failure', 'never'):
                problems.append(f'{aid}: approvalPolicy {a["approvalPolicy"]!r} (untrusted, on-request, never)')
            if a.get('sandbox') not in (None, 'read-only', 'workspace-write', 'danger-full-access'):
                problems.append(f'{aid}: sandbox {a["sandbox"]!r} (read-only, workspace-write, danger-full-access)')
        if rt == 'acp' and not a.get('command'): problems.append(f'{aid}: an acp agent needs "command"')
        if rt == 'copilot' and not os.path.isdir(os.path.join(ROOT, 'node_modules/@github/copilot-sdk')):
            problems.append(f'{aid}: runtime copilot needs the Copilot SDK (npm install --no-save @github/copilot-sdk)')
    missing = sorted(LOOKS - seen) if LOOKS else []
    if missing: notes.append(f'no agent yet for {", ".join(missing)}: the hub adds one for each character when it starts')
    names = {'claude': 'Claude Code', 'codex': 'Codex', 'copilot': 'Copilot', 'acp': 'ACP'}
    summary = ', '.join(f'{a.get("id")} ({names.get(a.get("runtime") or "claude", a.get("runtime"))})' for a in agents if isinstance(a, dict))
    if problems: fail(f'~/.chums/agents.json: ' + '; '.join(problems), 'edit ~/.chums/agents.json (docs/other-agents.md lists the fields), then restart the hub')
    else: ok(f'~/.chums/agents.json: {len(agents)} agent{"s" * (len(agents) != 1)}: {summary}')
    for n in notes: warn(n)

# ---------- 4. the hub ----------
section('4. The hub')
hub_label = f'{label_prefix}.hub'
hub_launchd = os.path.isfile(os.path.join(HOME, 'Library/LaunchAgents', f'{hub_label}.plist'))
start_fix = (f'launchctl kickstart -k gui/{os.getuid()}/{hub_label}  (log: ~/.chums/hub.log)' if hub_launchd
             else 'bin/chums-hub  (or bin/chums-setup --launchd to run it at login)')
if not (cfg and cfg.get('token')):
    note('skipped: no config yet')
else:
    port, pport = cfg.get('port', 7717), cfg.get('publicPort', 7718)
    status, body, err = http(f'http://127.0.0.1:{port}/v1/ping', cfg['token'])
    if status == 200:
        hub_up = True
        ok(f'the hub answers on 127.0.0.1:{port}')
    elif status == 401:
        fail(f'something on 127.0.0.1:{port} refuses this config\'s token: a hub started with another config, or another program',
             [f'lsof -nP -iTCP:{port} -sTCP:LISTEN shows what it is', 'stop it, then start the hub again'])
    else:
        fail(f'the hub is not running (nothing answers on 127.0.0.1:{port})', start_fix)
    if hub_up:
        s2, _, _ = http(f'http://127.0.0.1:{pport}/v1/ping', cfg.get('watchToken', ''))
        if s2 == 200: ok(f'the watch side answers on 127.0.0.1:{pport} (what Funnel forwards to)')
        else: fail(f'the watch side on 127.0.0.1:{pport} does not answer ({s2 or "no connection"})', ['restart the hub', start_fix])
        if hub_launchd and launchd_loaded(hub_label): note(f'it runs as the LaunchAgent {hub_label}, log in ~/.chums/hub.log')
        else: note('it runs in a terminal and stops when that terminal closes (bin/chums-setup --launchd runs it at login)')
        if port_open(WHISPER_PORT): ok(f'speech to text (whisperkit-cli serve) listens on {WHISPER_PORT}')
        else: fail(f'speech to text is not running (nothing on port {WHISPER_PORT}); the hub starts it',
                   ['the hub log says why: "whisper model missing" (bin/chums-setup) or "whisper exited"',
                    'under launchd, whisperkit-cli must be in the PATH of the hub LaunchAgent: run bin/chums-setup --launchd again'])
        # the agents' voices (Kokoro), unless config says otherwise
        engine = (cfg.get('tts') or {}).get('engine') or ('kokoro' if os.access(os.path.join(CHUMS, 'kokoro/.venv/bin/python'), os.X_OK) else 'watch')
        if engine == 'kokoro':
            if port_open(KOKORO_PORT, '127.0.0.1'): ok(f"the agents' voices (Kokoro) answer on {KOKORO_PORT}")
            else: warn(f"the agents' voices (Kokoro) are not running (nothing on port {KOKORO_PORT}): the watch reads replies with its own voice",
                       ['the hub starts Kokoro: its log says why if it stopped ("kokoro exited")', 'reinstall it: bin/chums-setup'])
        elif engine == 'watch': note("the watch reads replies with its own voice (bin/chums-setup installs the agents' voices, Kokoro)")
        else: note(f'replies are voiced with {engine} (config "tts")')
        st, state, _ = http(f'http://127.0.0.1:{port}/v1/state?since=0', cfg['token'])
        if st == 200 and state:
            for a in state.get('agents', []):
                rt = {'claude': 'Claude Code', 'codex': 'Codex'}.get(a.get('runtime', 'claude'), a.get('runtime'))
                if a.get('status') != 'offline':
                    ok(f'agent {a.get("id")} ({a.get("name")}, {rt}) is {a.get("status")}')
                elif rt == 'Claude Code':
                    warn(f'agent {a.get("id")} ({a.get("name")}, Claude Code) is not running: the watch shows it as "Not running on your Mac"',
                         [f'bin/chums-agents install (all) or bin/chums-agents start {a.get("id")}',
                          f'its log: ~/.chums/agents/{a.get("id")}.host.log'])
                else:
                    warn(f'agent {a.get("id")} ({a.get("name")}, {rt}) is not running in the hub',
                         [f'its log: ~/.chums/agents/{a.get("id")}.host.log', 'restart the hub after fixing agents.json'])
            ids = {a.get('id') for a in state.get('agents', [])}
            for s in state.get('sessions', []):
                if s.get('name') not in ids: note(f'session {s.get("name")} is connected (not in agents.json)')

# permissions: the hub and the agents run through Chums.app, so every permission they need is Chums's (read-only here)
chums_app = os.path.join(os.environ.get('CHUMS_MAC_APP') or os.path.join(HOME, 'Applications/Chums.app'), 'Contents/MacOS')
la_dir = os.path.join(HOME, 'Library/LaunchAgents')
plists = [os.path.join(la_dir, f) for f in sorted(os.listdir(la_dir)) if f.startswith((f'{label_prefix}.hub.', f'{label_prefix}.tailscaled.', f'{label_prefix}.agent.'))] if os.path.isdir(la_dir) else []
if plists:
    import plistlib
    old = [os.path.basename(p) for p in plists
           if (plistlib.load(open(p, 'rb')).get('ProgramArguments') or [''])[0] != os.path.join(chums_app, 'Chums')]
    if old: warn(f'{", ".join(old)} still start{"s" * (len(old) == 1)} outside Chums.app: macOS asks for permissions as expect, caffeinate, node or tailscaled, again after each update',
                 'bin/chums-setup --launchd and bin/chums-agents install (they restart the hub and the agents), then open Chums')
    else: ok('the hub, tailscaled and the agents run as Chums (one app for every permission)')
    if os.access(os.path.join(chums_app, 'Chums'), os.X_OK):
        got = {w: run([os.path.join(chums_app, 'Chums'), '--check', w])[0] == 0 for w in ('screen', 'accessibility')}
        names = {'screen': 'Screen Recording', 'accessibility': 'Accessibility'}
        missing = [names[w] for w, g in got.items() if not g]
        if missing: warn(f'Chums doesn\'t have {" or ".join(missing)} yet: an agent can stop on a dialog on this Mac',
                         'open Chums (~/Applications) and click Allow All, once, at the Mac  (bin/chums-permissions opens it)')
        else: ok('Chums has Screen Recording and Accessibility (its window shows the rest)')

# ---------- 5. Tailscale Funnel ----------
section('5. Tailscale Funnel (the watch\'s way to the hub)')
host = None
if not (ts and tsd):
    note('skipped: Tailscale is not installed')
else:
    rc, out, err = run([ts, f'--socket={TS_SOCK}', 'status', '--json'], timeout=10)
    try: tstat = json.loads(out) if rc == 0 or out.startswith('{') else None
    except ValueError: tstat = None
    if not os.path.exists(TS_SOCK) or tstat is None:
        fail("Chums' tailscaled is not running", ['bin/chums-tunnel starts it',
             'bin/chums-setup --launchd also runs it at login'])
    else:
        state_ = tstat.get('BackendState')
        selfn = tstat.get('Self') or {}
        host = (selfn.get('DNSName') or '').rstrip('.') or None
        if state_ == 'Running':
            ok(f'signed in to Tailscale as {host}')
        elif state_ == 'NeedsLogin':
            fail('tailscaled is not signed in to Tailscale', 'bin/chums-tunnel, then open the sign-in link it prints')
            host = None
        else:
            fail(f'tailscaled is {state_}', 'bin/chums-tunnel')
            host = None
        caps = set((selfn.get('CapMap') or {}).keys()) | set(selfn.get('Capabilities') or [])
        if host:
            if 'https' in caps and 'funnel' in caps: ok('the tailnet allows HTTPS certificates and Funnel for this machine')
            else: fail('the tailnet does not allow ' + ' and '.join(x for x, c in (('HTTPS certificates', 'https'), ('Funnel', 'funnel')) if c not in caps),
                       ['bin/chums-tunnel prints a link that turns both on; open it and approve',
                        'or in the Tailscale admin console: DNS › HTTPS Certificates, and Access controls › the funnel node attribute'])
            rc, out, _ = run([ts, f'--socket={TS_SOCK}', 'funnel', 'status', '--json'], timeout=10)
            try: fs_ = json.loads(out) if out else {}
            except ValueError: fs_ = {}
            want = f'http://127.0.0.1:{(cfg or {}).get("publicPort", 7718)}'
            proxy = (((fs_.get('Web') or {}).get(f'{host}:443') or {}).get('Handlers') or {}).get('/', {}).get('Proxy')
            if (fs_.get('AllowFunnel') or {}).get(f'{host}:443') and proxy == want:
                ok(f'Funnel is on: https://{host} goes to {want}')
            elif proxy and proxy != want:
                fail(f'Funnel forwards https://{host} to {proxy}, not to the hub\'s watch side ({want})', 'bin/chums-tunnel')
            else:
                fail('Funnel is off for this machine', 'bin/chums-tunnel')
            if cfg and cfg.get('publicURL') and cfg['publicURL'].rstrip('/') != f'https://{host}':
                fail(f'config.json has publicURL {cfg["publicURL"]}, but this machine is https://{host}',
                     ['bin/chums-tunnel (it stores the right URL)', 'then bin/chums-install (the URL is built into the watch app)'])

# the public address, as the watch sees it: public DNS, then HTTPS through Funnel
url = (cfg or {}).get('publicURL') or (f'https://{host}' if host else None)
if url and cfg and cfg.get('watchToken'):
    name = re.sub(r'^https?://', '', url).split('/')[0].split(':')[0]
    ips = []
    if shutil.which('dig'):
        for server in ('1.1.1.1', '8.8.8.8'):
            rc, out, _ = run(['dig', '+short', '+time=3', '+tries=1', 'A', name, f'@{server}'], timeout=10)
            ips = [l for l in out.split('\n') if re.fullmatch(r'[\d.]+', l)]
            if ips: break
    if ips:
        ok(f'{name} resolves in public DNS ({", ".join(ips[:2])})')
    else:
        fail(f'{name} does not resolve in public DNS yet',
             ['a new Funnel name takes a while: Tailscale says up to 10 minutes; it has taken about 25',
              'run bin/chums-doctor again later; nothing else to do'])
    # the answer's body isn't kept (read-only: nothing written, not even a temporary file)
    t0 = time.time()
    rc, out, err = run(['curl', '-sS', '--max-time', '15', '-o', '/dev/null', '-w', '%{http_code} %{remote_ip}',
                        '-H', '@-', f'{url.rstrip("/")}/v1/ping'],
                       timeout=25, stdin=f'Authorization: Bearer {cfg["watchToken"]}\n')
    took = time.time() - t0
    parts = out.split()
    code = parts[0] if parts else None
    remote = parts[1] if len(parts) > 1 else ''
    tailnet = False
    try: tailnet = ipaddress.ip_address(remote) in ipaddress.ip_network('100.64.0.0/10') or remote.startswith('fd7a:115c:a1e0')
    except ValueError: pass
    if rc == 0 and code == '200':
        if tailnet:
            warn(f'{url}/v1/ping answers, but over your tailnet ({remote}), not through the internet',
                 'check from a phone on cellular: open the URL + /v1/ping; {"error":"unauthorized"} means Funnel works')
        else:
            ok(f'{url}/v1/ping answers through Funnel from the internet with the watch token ({took:.1f} s)')
    elif rc == 0 and code == '401':
        fail(f'{url} reaches a hub that refuses this config\'s watch token',
             ['the hub behind Funnel was started with another config: restart the hub', start_fix])
    elif rc == 0 and code in ('502', '503', '504'):
        fail(f'Funnel answers but the hub behind it does not (HTTP {code})', start_fix)
    elif rc == 6:
        fail(f'{url}: the name does not resolve from this Mac yet (see the DNS line above)',
             'if public DNS already resolves it, flush this Mac\'s cache: sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder')
    elif rc != 127:
        fail(f'{url}/v1/ping failed: {err or f"HTTP {code}"}',
             ['tailscale --socket ~/.chums/tailscale/tailscaled.sock funnel status shows what Funnel serves',
              'the first HTTPS request to a new name waits while Tailscale gets its certificate; try again in a minute'])
elif cfg:
    note('skipped the internet check: no public URL yet')

# ---------- 6. building the watch app ----------
section('6. Building the watch app (Xcode, signing)')
xcode_ok = False
if os.path.isdir(DEV):
    rc, out, _ = run(['xcodebuild', '-version'], timeout=30, env={'DEVELOPER_DIR': DEV})
    xv = version(out)
    if rc == 0 and xv and xv >= (26, 0):
        xcode_ok = True
        ok(f'{out.splitlines()[0]} ({DEV.split("/Contents")[0]})')
    else:
        fail(f'Xcode 26 or later is needed (found: {out.splitlines()[0] if out else "none"})', 'install Xcode from the App Store, or set DEVELOPER_DIR')
else:
    fail(f'Xcode not found at {DEV.split("/Contents")[0]}', ['install Xcode 26 from the App Store and open it once',
         'or set DEVELOPER_DIR to the Xcode you use (…/Xcode.app/Contents/Developer)'])
if xcode_ok:
    if run(['xcodebuild', '-license', 'check'], timeout=30, env={'DEVELOPER_DIR': DEV})[0] != 0:
        fail("Xcode's license has not been accepted", 'open Xcode once, or: sudo xcodebuild -license accept')
    if run(['xcodebuild', '-checkFirstLaunchStatus'], timeout=30, env={'DEVELOPER_DIR': DEV})[0] != 0:
        fail("Xcode hasn't finished its first launch (it installs components then)", 'open Xcode once, or: sudo xcodebuild -runFirstLaunch')
    sdk = version(run(['xcrun', '--sdk', 'watchos', '--show-sdk-version'], timeout=30, env={'DEVELOPER_DIR': DEV})[1])
    if sdk and sdk >= (26, 0): ok(f'watchOS {vstr(sdk)} SDK')
    else: fail('the watchOS SDK is missing from Xcode', 'Xcode › Settings › Components: get watchOS')
    sel = run(['xcode-select', '-p'], timeout=5)[1]
    if sel and not sel.startswith(DEV.split('/Contents')[0]):
        note(f'xcode-select points at {sel}; Chums\' scripts use DEVELOPER_DIR={DEV}. To run xcrun devicectl yourself: '
             f'sudo xcode-select -s {DEV.split("/Contents")[0]}')
    rc, out, _ = run(['xcrun', 'simctl', 'list', 'runtimes', '-j'], timeout=30, env={'DEVELOPER_DIR': DEV})
    try: sims = [r for r in json.loads(out)['runtimes'] if r.get('platform') == 'watchOS' and r.get('isAvailable')]
    except (ValueError, KeyError): sims = []
    if sims: ok(f'watchOS Simulator {sims[-1].get("version", "")} (for bin/chums-sim)')
    else: note('no watchOS Simulator runtime: only bin/chums-sim needs it (xcodebuild -downloadPlatform watchOS, several GB)')
if find('xcodegen')[0]: ok('xcodegen')
else: fail('xcodegen is not installed (it makes the Xcode project)', 'brew install xcodegen')

team = os.environ.get('CHUMS_TEAM') or (cfg or {}).get('team')
if team:
    source = 'CHUMS_TEAM' if os.environ.get('CHUMS_TEAM') else '"team" in config.json'
    ok(f'signing team {team} (set by {source})')
else:
    rc, out, err = run([sys.executable, os.path.join(ROOT, 'tools/pick-team.py')], timeout=30)
    team, team_kind = (out.strip() or None), ('free' if 'free' in err else 'paid')
    if not team:
        fail('Xcode has no Apple ID that can sign apps', ['Xcode › Settings › Apple Accounts › + › Apple ID, and sign in',
             'any Apple ID works: it gets a free Personal Team'])
    elif team_kind == 'free':
        warn(f'signing team {team} is a free Personal Team: installs expire after 7 days, 3 apps per device, 10 App IDs per 7 days',
             'run bin/chums-install again within 7 days, or join the Apple Developer Program ($99 a year, installs last a year)')
    else:
        ok(f'signing team {team} (a paid team in Xcode)')
bundle = os.environ.get('CHUMS_BUNDLE') or (cfg or {}).get('bundleId')
if bundle: note(f'bundle ID {bundle}: the watch app is {bundle}.watchkitapp')
elif team: note(f'bundle ID dev.chums.{team.lower()} (from the team). To keep it if you change teams, add "bundleId" to ~/.chums/config.json')

if os.path.isfile(HUBCONFIG):
    src = open(HUBCONFIG, encoding='utf-8').read()
    m_tok = re.search(r'static let token = "([^"]*)"', src)
    m_hosts = re.search(r'static let hosts = (\[[^\]]*\])', src)
    m_build = re.search(r'static let build = "([^"]*)"', src)
    try: hosts = json.loads(m_hosts.group(1)) if m_hosts else []
    except ValueError: hosts = []
    built = f'built {m_build.group(1)}' if m_build else 'last build'
    if cfg and m_tok and m_tok.group(1) != cfg.get('watchToken'):
        fail(f'the watch app ({built}) has an older watch token than the hub (the watch shows "Hub refused the token")', 'bin/chums-install')
    elif cfg and cfg.get('publicURL') and cfg['publicURL'] not in hosts:
        fail(f'the watch app ({built}) has another hub address than {cfg["publicURL"]}', 'bin/chums-install')
    elif cfg:
        ok(f'the watch app ({built}) has the hub\'s current token and address')
else:
    note('the watch app has not been built from this checkout yet (bin/chums-install builds it)')

# ---------- 7. the watch ----------
section('7. The Apple Watch (as Xcode sees it)')
if not xcode_ok:
    note('skipped: Xcode is needed to see devices')
else:
    devices, rc, out, err = None, 1, '', ''
    try:                                                     # devicectl writes its list only to a file
        with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
            rc, out, err = run(['xcrun', 'devicectl', 'list', 'devices', '--json-output', tmp.name], timeout=60, env={'DEVELOPER_DIR': DEV})
            try: devices = json.load(open(tmp.name))['result']['devices']
            except (ValueError, KeyError, OSError): devices = None
    except OSError as e: err = f'no temporary file for its list: {e}'
    if devices is None:
        fail(f'xcrun devicectl could not list devices ({(err or out).splitlines()[-1] if (err or out) else rc})', 'open Xcode once and try again')
    else:
        def props(d):
            hp, dp, cp = d.get('hardwareProperties', {}), d.get('deviceProperties', {}), d.get('connectionProperties', {})
            return hp.get('platform'), dp.get('name', '?'), version(dp.get('osVersionNumber')), dp.get('developerModeStatus'), cp.get('pairingState')
        watches = [d for d in devices if d.get('hardwareProperties', {}).get('platform') == 'watchOS']
        phones = [d for d in devices if d.get('hardwareProperties', {}).get('deviceType') == 'iPhone']
        for d in phones:
            _, n, v, dm, pair = props(d)
            note(f'iPhone {n} (iOS {vstr(v) if v else "?"}): {pair or "?"}, Developer Mode {dm or "?"}')
        if not watches:
            fail('Xcode does not know any Apple Watch yet',
                 ['connect the paired iPhone with a USB cable, unlock it and tap Trust',
                  'keep the watch unlocked and near the iPhone, on the same Wi-Fi as the Mac',
                  'open Xcode › Window › Devices and Simulators and wait for the watch (docs/setup.md, step 7)'])
        for d in watches:
            _, n, v, dm, pair = props(d)
            what = f'Apple Watch {n} (watchOS {vstr(v) if v else "?"})'
            if v and v < (10, 0): fail(f'{what}: Chums needs watchOS 10', 'on the iPhone: Watch app › General › Software Update')
            elif pair != 'paired': fail(f'{what} is not paired with this Mac ({pair})', 'Xcode › Window › Devices and Simulators, with the iPhone on USB and the watch unlocked')
            elif dm != 'enabled': fail(f'{what}: Developer Mode is {dm or "off"}',
                                     ['on the watch: Settings › Privacy & Security › Developer Mode, then restart it and confirm',
                                      'switch missing? docs/setup.md, step 8'])
            else: ok(f'{what}: paired with this Mac, Developer Mode on')

# ---------- summary ----------
print(f'\n{count["PASS"]} passed, {count["WARN"]} warning{"s" * (count["WARN"] != 1)}, {count["FAIL"]} failed.')
if count['FAIL']:
    print('Fix the first FAIL first: later checks often fail because of it. More in docs/troubleshooting.md.')
sys.exit(1 if count['FAIL'] else 0)
