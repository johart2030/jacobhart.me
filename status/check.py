#!/usr/bin/env python3

import json
import socket
import struct
import time
import urllib.request

JAVA_HOST = "stamina-xf.tun.ply.gg"
JAVA_PORT = 1904

BEDROCK_HOST = "147.185.221.213"
BEDROCK_PORT = 20338


def varint(value):
    data = b""

    while True:
        temp = value & 0x7F
        value >>= 7

        if value:
            temp |= 0x80

        data += bytes([temp])

        if not value:
            return data


def read_varint(sock):
    result = 0
    shift = 0

    while True:
        byte = sock.recv(1)

        if not byte:
            raise ConnectionError("Connection closed")

        byte = byte[0]
        result |= (byte & 0x7F) << shift

        if not (byte & 0x80):
            return result

        shift += 7

        if shift > 35:
            raise ValueError("Invalid VarInt")

def check_java():

    start = time.perf_counter()

    try:
        sock = socket.create_connection(
            (JAVA_HOST, JAVA_PORT),
            timeout=5
        )

        host_bytes = JAVA_HOST.encode("utf-8")

        # Minecraft Java handshake
        protocol_version = 774

        handshake_data = (
            varint(0x00) +
            varint(protocol_version) +
            varint(len(host_bytes)) +
            host_bytes +
            struct.pack(">H", JAVA_PORT) +
            varint(1)
        )

        handshake_packet = (
            varint(len(handshake_data)) +
            handshake_data
        )

        sock.sendall(handshake_packet)

        # Status request
        status_request = b"\x01\x00"
        sock.sendall(status_request)

        # Read response
        packet_length = read_varint(sock)

        packet_id = read_varint(sock)

        if packet_id != 0x00:
            raise ValueError(
                f"Unexpected packet ID: {packet_id}"
            )

        json_length = read_varint(sock)

        data = b""

        while len(data) < json_length:

            chunk = sock.recv(
                min(4096, json_length - len(data))
            )

            if not chunk:
                raise ConnectionError(
                    "Connection closed"
                )

            data += chunk

        sock.close()

        status = json.loads(
            data.decode("utf-8")
        )

        ping = round(
            (time.perf_counter() - start) * 1000
        )

        players = status.get("players", {})
        version = status.get("version", {})

        return {
            "online": True,
            "players": players.get("online", 0),
            "max_players": players.get("max", 0),
            "version": version.get(
                "name",
                "Unknown"
            ),
            "ping": ping
        }

    except Exception as e:

        return {
            "online": False,
            "players": 0,
            "max_players": 0,
            "version": "—",
            "ping": None,
            "error": str(e)
        }


def check_bedrock():

    start = time.perf_counter()

    try:

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

        sock.settimeout(5)

        timestamp = int(time.time() * 1000)

        packet = (
            b"\x01" +
            struct.pack(">Q", timestamp) +
            bytes.fromhex(
                "00ffff00fefefefefdfdfdfd12345678"
            ) +
            struct.pack(">Q", 0)
        )

        sock.sendto(
            packet,
            (BEDROCK_HOST, BEDROCK_PORT)
        )

        data, address = sock.recvfrom(2048)

        ping = round((time.perf_counter() - start) * 1000)

        sock.close()

        if not data:
            raise ConnectionError("Empty response")

        return {
            "online": True,
            "ping": ping,
            "address": str(address)
        }

    except Exception as e:

        return {
            "online": False,
            "ping": None,
            "error": str(e)
        }


def main():

    result = {
        "java": check_java(),
        "bedrock": check_bedrock(),
        "checked": int(time.time())
    }

    print(json.dumps(result))


if __name__ == "__main__":
    main()