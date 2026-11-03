"""What kind of client signed in, from the User-Agent it sends: the Android app or a web browser.

The Android app sends "WealthVault-Android/<version> (<device>; Android <release>)". Versions before 0.3.18 send OkHttp's
default "okhttp/<n>", which is still recognised as the app (version unknown). Anything else is treated as the web.
No IP address is kept: it is personal data and would need its own privacy-policy line.
"""

import re
from typing import Dict, Optional

MAX_UA = 200

_APP = re.compile(r"^WealthVault-Android/(?P<version>[\w.\-]+)(?: \((?P<device>[^)]*)\))?")


def describe(user_agent: Optional[str]) -> Dict[str, str]:
    """platform ("app" or "web"), app_version, device and a trimmed user_agent; empty strings when unknown."""
    ua = (user_agent or "").strip()
    info = {"platform": "web", "app_version": "", "device": "", "user_agent": ua[:MAX_UA]}
    m = _APP.match(ua)
    if m:
        info.update(platform="app", app_version=m.group("version"), device=(m.group("device") or "")[:80])
    elif ua.lower().startswith("okhttp/"):
        info.update(platform="app")  # an app build from before the version was sent
    elif not ua:
        info["platform"] = "unknown"
    return info
