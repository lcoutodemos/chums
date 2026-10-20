# Older Apple Watches

The watch app and watch widget target watchOS 10 or later. The iPhone app still needs iOS 26 or later, and building
the apps still needs Xcode 26 or later. Older watches use material backgrounds in the conversation and agent
settings; watchOS 26 and iOS 26 keep Liquid Glass.

Check the watch's version in Settings > General > About before setting up the Mac. An Apple Watch Series 5 on
watchOS 10.6.1 has been installed and tested with voice capture, a Codex reply and a running keyring session.
Other older models and all display behaviors have not been verified. The existing private API used to extend
screen wake time is checked at runtime; compilation alone does not establish that it works on every watchOS version.

## When Xcode cannot discover the watch

The normal [setup](setup.md) is the first path. Keep the paired iPhone on USB and both devices unlocked.
Some older watches may not appear in `devicectl` even when the iPhone can communicate with them. In that case,
the iPhone's Watch app can install the watch app embedded in the signed iPhone package.

The optional `pymobiledevice3` fallback in setup.md can reveal Developer Mode through the iPhone. If you cannot
find the watch's UDID in Xcode, its `companion list --udid <iPhone UDID>` command lists the paired watch identifiers.
Use the helper's `reveal` action, enable Developer Mode on the watch, restart from its prompt, and confirm Turn On.
Revealing the switch does not enable Developer Mode or bypass the watch's Trust confirmation.

For installation through the iPhone:

1. Sign in to the Apple Account in Xcode and make sure the iPhone and watch are registered for development.
   If Xcode cannot register the watch, use the account's Devices page. A provisioning profile must include the
   actual watch's UDID; registering a device does not necessarily update an existing profile.
2. Run `tools/gen-config.sh` and generate the Xcode project with the same team and bundle identifiers used for
   your installation. The generated HubConfig.swift contains a token and must stay local.
3. Build the Chums scheme for the connected iPhone with automatic signing. Use a concrete iPhone destination
   if asking Xcode to register that phone: `-target` builds ignore `-destination`.
4. Install the signed Chums.app on the iPhone. In the iPhone's Watch app, find Chums under Available Apps and tap
   Install. Keep the devices near each other and unlocked until it completes.

If updating an existing installation stalls, turn Keyring: stay on off, leave Chums, then retry the transfer.
Turn keyring mode back on after the update completes. Verify the installed version on the watch rather than
assuming that an updated iPhone package has already updated its watch app.

## Signing checks

Build products contain the hub token. Keep them private and out of Git. Do not contribute provisioning profiles,
signing keys, certificates, device identifiers, generated configuration or signed app packages.

If signing reports "resource fork, Finder information, or similar detritus not allowed", use a private build
directory outside a synced Documents folder for both SYMROOT and OBJROOT.

If Xcode replaces cached profiles while the build is using them, let profile synchronization finish and retry
with the downloaded profiles. After changing profiles, use a clean signed build and verify every `.app` and
`.appex` individually with `codesign --verify --strict`. In testing, a top-level `--deep` check passed while a
nested watch widget had a stale signature for its embedded profile. The iPhone installed, but watch installation
returned to the Install button until the nested bundle was rebuilt and signed correctly.
