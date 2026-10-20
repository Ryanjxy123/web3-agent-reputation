"""Operator proxy discovery for provider traffic; never reads Agent metadata or executes PAC."""

from dataclasses import dataclass
import os
from urllib import request as urllib_request
from urllib.parse import urlsplit


@dataclass(frozen=True, repr=False)
class ProxyRoute:
    url: str | None
    source: str

    @property
    def kind(self) -> str:
        return urlsplit(self.url).scheme if self.url else "direct"

    def diagnostics(self) -> dict:
        parsed = urlsplit(self.url) if self.url else None
        return {"source": self.source, "kind": self.kind,
                "auth": parsed is not None and (parsed.username is not None or parsed.password is not None)}


def _validate_proxy(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if (not value or any(char.isspace() or ord(char) < 33 or ord(char) == 127 for char in value) or "\\" in value
                or parsed.scheme not in {"http", "https", "socks5"} or not parsed.hostname
                or "%" in parsed.hostname or parsed.port == 0
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or "?" in value or "#" in value):
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Provider proxy must be an http, https or socks5 URL without path, query or fragment; remote DNS modes are unsupported") from None
    return value


def _system_proxies() -> dict[str, str]:
    # NO_PROXY alone makes getproxies() hide OS settings on Windows/macOS.
    read = (getattr(urllib_request, "getproxies_registry", None)
            or getattr(urllib_request, "getproxies_macosx_sysconf", None)
            or urllib_request.getproxies)
    return read()


def _system_bypass(host: str) -> bool:
    bypass = (getattr(urllib_request, "proxy_bypass_registry", None)
              or getattr(urllib_request, "proxy_bypass_macosx_sysconf", None))
    return bool(bypass(host)) if bypass is not None else False


def select_proxy(target_url: str, explicit: str | None = None, *,
                 override_variable: str = "REPUTATION_LLM_PROXY") -> ProxyRoute:
    """Selected provider override > legacy CLI > standard environment > OS > direct.

    HTTPS uses HTTPS_PROXY then ALL_PROXY, as in httpx. NO_PROXY applies to
    every proxy route; OS bypass rules additionally apply to OS routes only.
    A dedicated override/CLI value of ``direct`` forces a direct connection.
    """
    try:
        target = urlsplit(target_url)
        if (target.scheme != "https" or not target.hostname or target.username is not None
                or target.password is not None or target.port not in (None, 443)):
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Provider proxy selection requires a valid HTTPS origin on port 443") from None
    hostname = target.hostname
    authority = (f"[{hostname}]" if ":" in hostname else hostname) + ":443"
    environment = urllib_request.getproxies_environment()
    override = os.environ.get(override_variable)
    if override is not None and override != "":
        candidate, source = override, "llm-env" if override_variable == "REPUTATION_LLM_PROXY" else "operator-env"
    elif explicit is not None:
        candidate, source = explicit, "explicit"
    else:
        configured = any(environment.get(key) for key in ("http", "https", "all"))
        if configured:
            candidate = environment.get("https") or environment.get("all")
            source = "env"
        else:
            try:
                system = _system_proxies()
                candidate = system.get("https") or system.get("all")
            except (OSError, TypeError, ValueError):
                raise ValueError("System proxy configuration could not be read; set the provider proxy explicitly") from None
            source = "system" if candidate else "direct"
    if candidate == "direct":
        return ProxyRoute(None, source)
    if candidate is None:
        return ProxyRoute(None, source)
    proxy = _validate_proxy(candidate)
    if urllib_request.proxy_bypass_environment(authority, environment):
        return ProxyRoute(None, "override-bypass" if source in {"llm-env", "operator-env", "explicit"} else source)
    if source == "system":
        try:
            if _system_bypass(authority):
                return ProxyRoute(None, source)
        except (OSError, TypeError, ValueError):
            raise ValueError("System proxy bypass configuration could not be read; set the provider proxy explicitly") from None
    return ProxyRoute(proxy, source)
