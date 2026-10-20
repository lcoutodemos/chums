"""Reveal (and optionally enable) Developer Mode on an Apple Watch reached through its paired iPhone.

Route: Mac --usbmux--> iPhone --companion_proxy port forward--> watch lockdownd (62078).
Usage: CHUMS_PHONE_UDID=… CHUMS_WATCH_UDID=… python3 watch_devmode.py [status|reveal|enable]
Needs: pip install pymobiledevice3
"""
import asyncio
import os
import sys

from pymobiledevice3 import usbmux
from pymobiledevice3.exceptions import NotPairedError
from pymobiledevice3.lockdown import UsbmuxLockdownClient, create_using_usbmux
from pymobiledevice3.service_connection import ServiceConnection
from pymobiledevice3.services.amfi import AmfiService

# The iPhone's and the watch's UDIDs (find them with: xcrun xctrace list devices). Set both, e.g.
#   CHUMS_PHONE_UDID=00008XXX-... CHUMS_WATCH_UDID=00008XXX-... python3 tools/watch_devmode.py reveal
PHONE = os.environ.get("CHUMS_PHONE_UDID", "")
WATCH = os.environ.get("CHUMS_WATCH_UDID", "")
if not (PHONE and WATCH):
    sys.exit("Set CHUMS_PHONE_UDID and CHUMS_WATCH_UDID (from: xcrun xctrace list devices). The iPhone must be on USB.")
LOCKDOWN_PORT = 62078

_keepalive = []  # companion_proxy connections must stay open for their forwards to live


async def forward(phone, gizmo_port: int) -> ServiceConnection:
    svc = await phone.start_lockdown_service("com.apple.companion_proxy")
    resp = await svc.send_recv_plist({
        "Command": "StartForwardingServicePort",
        "GizmoRemotePortNumber": gizmo_port,
        "IsServiceLowPriority": False,
        "PreferWifi": False,
    })
    local = resp.get("CompanionProxyServicePort")
    if local is None:
        raise RuntimeError(f"forward of watch port {gizmo_port} failed: {resp}")
    _keepalive.append(svc)
    return await ServiceConnection.create_using_usbmux(PHONE, local)


def watch_client_class(phone):
    class WatchLockdown(UsbmuxLockdownClient):
        async def create_service_connection(self, port: int) -> ServiceConnection:
            return await forward(phone, port)

    return WatchLockdown


async def main(action: str) -> None:
    phone = await create_using_usbmux(PHONE, connection_type="USB")
    print("phone:", phone.all_values.get("DeviceName"), phone.all_values.get("ProductVersion"))

    async with await usbmux.create_mux() as mux:
        try:
            pair_record = await mux.get_pair_record(WATCH)
        except NotPairedError:
            # A first connection has no saved record. Let autopair ask the watch to trust this Mac.
            pair_record = None
        system_buid = await mux.get_buid()

    conn = await forward(phone, LOCKDOWN_PORT)
    cls = watch_client_class(phone)
    watch = await cls.create(conn, identifier=WATCH, pair_record=pair_record, system_buid=system_buid,
                             autopair=True, pair_timeout=90)
    v = watch.all_values
    print("watch:", v.get("DeviceName"), v.get("ProductType"), "watchOS", v.get("ProductVersion"))
    status = await watch.get_value("com.apple.security.mac.amfi", "DeveloperModeStatus")
    print("DeveloperModeStatus:", status)

    amfi = AmfiService(watch)
    if action == "reveal":
        await amfi.reveal_developer_mode_option_in_ui()
        print("reveal: OK - Developer Mode toggle should now show in Settings > Privacy & Security")
    elif action == "accept":
        await amfi.enable_developer_mode_post_restart()
        print("accept: OK")
    elif action == "enable":
        await amfi.enable_developer_mode(enable_post_restart=False)
        print("enable: sent - watch will restart and ask to confirm")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "status"))
