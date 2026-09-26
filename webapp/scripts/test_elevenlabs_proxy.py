"""Rewrite .env UTF-8 and test ElevenLabs via proxy.

  python webapp/scripts/test_elevenlabs_proxy.py "http://user:pass@host:port"
  python webapp/scripts/test_elevenlabs_proxy.py "socks5://user:pass@host:port"
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / ".env"


def _read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ENV.exists():
        return out
    raw = ENV.read_bytes()
    text = ""
    for enc in ("utf-8-sig", "utf-16", "utf-16-le", "cp1251"):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            continue
    for line in text.splitlines():
        line = line.strip().lstrip("\ufeff")
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main() -> int:
    data = _read_env()
    key = (data.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    proxy = (sys.argv[1] if len(sys.argv) > 1 else data.get("ELEVENLABS_PROXY") or "").strip()
    if not key:
        print("ERROR: no ELEVENLABS_API_KEY in .env")
        return 1
    if not proxy:
        print("ERROR: pass proxy as argv, e.g. http://user:pass@host:port")
        return 1

    lines = [f"ELEVENLABS_API_KEY={key}", f"ELEVENLABS_PROXY={proxy}"]
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    host = proxy.rsplit("@", 1)[-1] if "@" in proxy else proxy
    print(f"Wrote {ENV}")
    print(f"proxy host: {host}")

    async def test() -> None:
        import httpx

        url = "https://api.elevenlabs.io/v1/voices"
        headers = {"xi-api-key": key, "Accept": "application/json"}
        variants = [proxy]
        if proxy.startswith("socks5://"):
            variants.append("http://" + proxy[len("socks5://") :])
        elif proxy.startswith("http://"):
            variants.append("socks5://" + proxy[len("http://") :])

        for p in variants:
            label = p.split("://", 1)[0]
            print(f"\n--- try {label} ---")
            try:
                async with httpx.AsyncClient(proxy=p, timeout=30.0, follow_redirects=False) as c:
                    r = await c.get(url, headers=headers)
                body = r.content or b""
                print(f"status={r.status_code} bytes={len(body)} ct={r.headers.get('content-type')}")
                print(body[:180].decode("utf-8", errors="replace").replace("\n", " "))
                if r.status_code == 200 and b"voices" in body:
                    print("SUCCESS")
                    # keep working scheme in .env
                    ENV.write_text(
                        f"ELEVENLABS_API_KEY={key}\nELEVENLABS_PROXY={p}\n",
                        encoding="utf-8",
                        newline="\n",
                    )
                    print(f"Saved working proxy scheme: {label}")
                    return
            except Exception as exc:
                print(f"FAIL: {type(exc).__name__}: {exc}")
        print("\nBoth modes failed. Need another proxy.")

    asyncio.run(test())
    return 0


if __name__ == "__main__":
    sys.exit(main())
