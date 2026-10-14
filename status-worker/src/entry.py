import asyncio
import json
import time

from js import Object, fetch
from pyodide.ffi import to_js
from workers import WorkerEntrypoint, Response


PUBLIC_MAIN_SITE = "https://jacobhart.me/"
PUBLIC_MC_SITE = "https://mc.jacobhart.me/"
PUBLIC_STATUS_SITE = "https://status.jacobhart.me/"
PUBLIC_DYNMAP = "https://map.jacobhart.me/"

JAVA_API = (
    "https://api.mcsrvstat.us/3/"
    "stamina-xf.tun.ply.gg:1904"
)

BEDROCK_API = (
    "https://api.mcsrvstat.us/bedrock/3/"
    "147.185.221.213:20338"
)


def fetch_options(accept="*/*"):
    return to_js(
        {
            "headers": {
                "User-Agent": "JacobHartStatus/1.0",
                "Accept": accept,
            },
            "redirect": "follow",
        },
        dict_converter=Object.fromEntries,
    )


async def check_website(url):
    start = time.perf_counter()

    try:
        response = await fetch(
            url,
            fetch_options("text/html,*/*"),
        )

        elapsed = round(
            (time.perf_counter() - start) * 1000
        )

        return {
            "online": 200 <= response.status < 400,
            "ping": elapsed,
            "http_status": int(response.status),
        }

    except Exception as error:
        elapsed = round(
            (time.perf_counter() - start) * 1000
        )

        return {
            "online": False,
            "ping": elapsed,
            "error": str(error),
        }


async def check_minecraft(api_url):
    start = time.perf_counter()

    try:
        response = await fetch(
            api_url,
            fetch_options("application/json"),
        )

        if not response.ok:
            status = int(response.status)
            body = await response.text()

            raise RuntimeError(
                f"Status API returned HTTP {status}: "
                f"{body[:200]}"
            )

        # Read the response as text and parse it into a
        # regular Python dictionary.
        body = await response.text()
        data = json.loads(body)

        if not isinstance(data, dict):
            raise ValueError(
                "Status API returned unexpected JSON"
            )

        players = data.get("players") or {}

        if not isinstance(players, dict):
            players = {}

        version = data.get("version") or "Unknown"

        if isinstance(version, dict):
            version = version.get("name") or "Unknown"

        elapsed = round(
            (time.perf_counter() - start) * 1000
        )

        return {
            "online": bool(data.get("online", False)),
            "players": int(players.get("online") or 0),
            "max_players": int(players.get("max") or 0),
            "version": str(version),
            "ping": None,
            "api_response_ms": elapsed,
        }

    except Exception as error:
        return {
            "online": False,
            "players": 0,
            "max_players": 0,
            "version": "Unknown",
            "ping": None,
            "api_response_ms": round(
                (time.perf_counter() - start) * 1000
            ),
            "error": str(error),
        }


def add_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Cache-Control"] = "no-store"

    return response


class Default(WorkerEntrypoint):

    async def fetch(self, request):
        if request.method == "OPTIONS":
            return add_headers(Response(""))

        (
            java,
            bedrock,
            dynmap,
            main_site,
            minecraft_site,
            status_page,
        ) = await asyncio.gather(
            check_minecraft(JAVA_API),
            check_minecraft(BEDROCK_API),
            check_website(PUBLIC_DYNMAP),
            check_website(PUBLIC_MAIN_SITE),
            check_website(PUBLIC_MC_SITE),
            check_website(PUBLIC_STATUS_SITE),
        )

        dynmap["configured"] = True

        result = {
            "java": java,
            "bedrock": bedrock,
            "dynmap": dynmap,
            "main_site": main_site,
            "minecraft_site": minecraft_site,
            "status_page": status_page,
            "checked": int(time.time()),
        }

        return add_headers(Response.json(result))