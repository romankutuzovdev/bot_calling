"""One-shot: rewrite .env UTF-8 and test ElevenLabs via proxy (no bot restart needed for test)."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / ".env"
PROXY = "socks5://nr3E6AvS:mv5BSCY4@91.217.90.197:59552"


def main() -> int:
    key = ""
    if ENV.exists():
        raw = ENV.read_bytes()
        for enc in ("utf-8-sig", "utf-16", "utf-16-le", "cp1251"):
            try:
                text = raw.decode(enc)
                break
            except Exception:
                text = ""
        for line in text.splitlines():
            line = line.strip().lstrip("\ufeff")
            if line.startswith("ELEVENLABS_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    key = key or os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        print("ERROR: no ELEVENLABS_API_KEY in .env")
        return 1

    lines = [f"ELEVENLABS_API_KEY={key}", f"ELEVENLABS_PROXY={PROXY}"]
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {ENV} (utf-8, no BOM)")
    print(f"PROXY host: {PROXY.rsplit('@', 1)[-1]}")

    async def test() -> None:
        import httpx

        url = "https://api.elevenlabs.io/v1/voices"
        headers = {"xi-api-key": key, "Accept": "application/json"}
        for label, proxy in (
            ("socks5", PROXY),
            ("http", PROXY.replace("socks5://", "http://", 1)),
        ):
            print(f"\n--- try {label} ---")
            try:
                async with httpx.AsyncClient(proxy=proxy, timeout=30.0, follow_redirects=False) as c:
                    r = await c.get(url, headers=headers)
                body = r.content or b""
                print(f"status={r.status_code} bytes={len(body)} ct={r.headers.get('content-type')}")
                preview = body[:180].decode("utf-8", errors="replace")
                print(preview.replace("\n", " "))
                if r.status_code == 200 and b"voices" in body:
                    print("SUCCESS: proxy works for ElevenLabs")
                    return
            except Exception as exc:
                print(f"FAIL: {type(exc).__name__}: {exc}")
        print("\nBoth modes failed. Need another proxy (working EU/US HTTP or SOCKS).")

    asyncio.run(test())
    return 0


if __name__ == "__main__":
    sys.exit(main())
