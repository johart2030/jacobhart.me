#!/usr/bin/env python3

import json
import socket
import struct
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "0.0.0.0"
PORT = 4321

BASE_DIR = Path("/var/www/html/jacobhart.me/status")
MC_DIR = Path("/var/www/html/jacobhart.me/mc")
MAIN_DIR = Path("/var/www/html/jacobhart.me")

JAVA_HOST = "stamina-xf.tun.ply.gg"
JAVA_PORT = 1904

BEDROCK_HOST = "147.185.221.213"
BEDROCK_PORT = 20338

# These are the PUBLIC hostnames we are preparing.
# They do not have to be configured in Cloudflare yet.
PUBLIC_MAIN_SITE = "https://jacobhart.me/"
PUBLIC_MC_SITE = "https://mc.jacobhart.me/"
PUBLIC_STATUS_SITE = "https://status.jacobhart.me/"
PUBLIC_DYNMAP = "https://map.jacobhart.me/"


def check_public_website(url):
    start = time.perf_counter()

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "JacobHartStatus/1.0"
            }
        )

        with urllib.request.urlopen(request, timeout=10) as response:
            ping = round((time.perf_counter() - start) * 1000)

            return {
                "online": 200 <= response.status < 400,
                "ping": ping,
                "http_status": response.status
            }

    except Exception as e:
        ping = round((time.perf_counter() - start) * 1000)

        return {
            "online": False,
            "ping": ping,
            "error": str(e)
        }


def check_dynmap():
    result = check_public_website(PUBLIC_DYNMAP)

    result["configured"] = True

    return result


def check_status_page():
    return check_public_website(PUBLIC_STATUS_SITE)


def query_java(host, port):
    start = time.perf_counter()

    try:

        def write_varint(value):
            data = bytearray()

            while True:
                temp = value & 0x7F
                value >>= 7

                if value:
                    data.append(temp | 0x80)
                else:
                    data.append(temp)
                    return bytes(data)

        def read_varint(sock):
            value = 0
            shift = 0

            while True:
                byte = sock.recv(1)

                if not byte:
                    raise ConnectionError("Connection closed")

                byte = byte[0]

                value |= (byte & 0x7F) << shift

                if not (byte & 0x80):
                    return value

                shift += 7

                if shift > 35:
                    raise ValueError("Invalid VarInt")

        with socket.create_connection(
            (host, port),
            timeout=5
        ) as sock:

            host_bytes = host.encode("utf-8")

            packet = (
                write_varint(0)
                + write_varint(774)
                + write_varint(len(host_bytes))
                + host_bytes
                + struct.pack(">H", port)
                + write_varint(1)
            )

            sock.sendall(
                write_varint(len(packet))
                + packet
                + write_varint(1)
                + b"\x00"
            )

            packet_length = read_varint(sock)
            packet_id = read_varint(sock)

            if packet_id != 0:
                raise ValueError(
                    f"Unexpected Java status packet ID: {packet_id}"
                )

            json_length = read_varint(sock)
            response_data = b""

            while len(response_data) < json_length:
                chunk = sock.recv(json_length - len(response_data))

                if not chunk:
                    raise ConnectionError("Connection closed")

                response_data += chunk

            data = json.loads(response_data.decode("utf-8"))

            ping = round(
                (time.perf_counter() - start) * 1000
            )

            players = data.get("players", {})
            version = data.get("version", {})

            return {
                "online": True,
                "ping": ping,
                "players": players.get("online", 0),
                "max_players": players.get("max", 0),
                "version": version.get(
                    "name",
                    "Unknown"
                )
            }

    except Exception as e:

        ping = round(
            (time.perf_counter() - start) * 1000
        )

        return {
            "online": False,
            "ping": ping,
            "error": str(e)
        }


def query_bedrock(host, port):
    start = time.perf_counter()

    try:

        magic = bytes.fromhex(
            "00ffff00fefefefefdfdfdfd12345678"
        )

        timestamp = int(
            time.time() * 1000
        )

        packet = (
            b"\x01"
            + struct.pack(">Q", timestamp)
            + magic
            + struct.pack(">Q", 0)
        )

        with socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        ) as sock:

            sock.settimeout(5)

            sock.sendto(
                packet,
                (host, port)
            )

            data, _ = sock.recvfrom(4096)

        ping = round(
            (time.perf_counter() - start) * 1000
        )

        if len(data) < 35:
            raise ValueError(
                "Invalid Bedrock response"
            )

        motd = data[35:].decode(
            "utf-8",
            errors="replace"
        )

        parts = motd.split(";")

        return {
            "online": True,
            "ping": ping,
            "motd": (
                parts[1]
                if len(parts) > 1
                else "Minecraft Bedrock"
            ),
            "players": (
                int(parts[4])
                if len(parts) > 4
                and parts[4].isdigit()
                else 0
            ),
            "max_players": (
                int(parts[5])
                if len(parts) > 5
                and parts[5].isdigit()
                else 0
            ),
            "version": (
                parts[3]
                if len(parts) > 3
                else "Unknown"
            )
        }

    except Exception as e:

        ping = round(
            (time.perf_counter() - start) * 1000
        )

        return {
            "online": False,
            "ping": ping,
            "error": str(e)
        }


def get_status():

    return {
        "java": query_java(
            JAVA_HOST,
            JAVA_PORT
        ),

        "bedrock": query_bedrock(
            BEDROCK_HOST,
            BEDROCK_PORT
        ),

        "dynmap": check_dynmap(),

        "main_site": check_public_website(
            PUBLIC_MAIN_SITE
        ),

        "minecraft_site": check_public_website(
            PUBLIC_MC_SITE
        ),

        "status_page": check_status_page(),

        "checked": int(time.time())
    }


class Handler(BaseHTTPRequestHandler):

    def send_file(
        self,
        path,
        content_type
    ):

        if not path.exists() or not path.is_file():
            self.send_error(404)
            return

        data = path.read_bytes()

        self.send_response(200)

        self.send_header(
            "Content-Type",
            content_type
        )

        self.send_header(
            "Content-Length",
            str(len(data))
        )

        self.end_headers()

        self.wfile.write(data)

    def do_GET(self):

        # ------------------------------
        # STATUS API
        # ------------------------------

        if self.path == "/api/status":

            data = json.dumps(
                get_status()
            ).encode("utf-8")

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "application/json"
            )

            self.send_header(
                "Cache-Control",
                "no-store"
            )

            self.send_header(
                "Content-Length",
                str(len(data))
            )

            self.end_headers()

            self.wfile.write(data)

            return

        # ------------------------------
        # DETERMINE HOSTNAME
        # ------------------------------

        hostname = (
            self.headers
            .get("Host", "")
            .split(":")[0]
            .lower()
        )

        path = self.path.split(
            "?",
            1
        )[0]

        # ------------------------------
        # STATUS.JACOBHART.ME
        # ------------------------------

        if hostname in (
            "status.jacobhart.me",
            "impact-vacation-shareholders-democrats.trycloudflare.com"
        ):

            if path in (
                "/",
                "/index.html"
            ):

                self.send_file(
                    BASE_DIR / "index.html",
                    "text/html; charset=utf-8"
                )

                return

        # ------------------------------
        # MC.JACOBHART.ME
        # ------------------------------

        if hostname == "mc.jacobhart.me":

            if path in (
                "/",
                "/index.html"
            ):

                self.send_file(
                    MC_DIR / "index.html",
                    "text/html; charset=utf-8"
                )

                return

        # ------------------------------
        # JACOBHART.ME
        # ------------------------------

        if hostname in (
            "jacobhart.me",
            "www.jacobhart.me"
        ):

            if path in (
                "/",
                "/index.html"
            ):

                self.send_file(
                    MAIN_DIR / "index.html",
                    "text/html; charset=utf-8"
                )

                return

        # ------------------------------
        # EVERYTHING ELSE
        # ------------------------------

        self.send_error(404)

    def log_message(
        self,
        format,
        *args
    ):

        print(
            "%s - %s"
            % (
                self.address_string(),
                format % args
            )
        )


if __name__ == "__main__":

    print(
        f"Starting JacobHart web/status server "
        f"on {HOST}:{PORT}"
    )

    print(
        "Prepared hostnames:"
    )

    print(
        "  jacobhart.me"
    )

    print(
        "  mc.jacobhart.me"
    )

    print(
        "  status.jacobhart.me"
    )

    print(
        "  map.jacobhart.me "
        "(checked as an external Dynmap URL)"
    )

    server = ThreadingHTTPServer(
        (HOST, PORT),
        Handler
    )

    server.serve_forever()