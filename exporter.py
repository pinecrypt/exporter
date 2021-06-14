#!/usr/bin/env python

import aiohttp
import asyncio
import os
import re
from collections import Counter
from sanic import Sanic, response, exceptions

app = Sanic("exporter")

PREFIX = "pinecrypt_gateway_"
PROMETHEUS_BEARER_TOKEN = os.getenv("PROMETHEUS_BEARER_TOKEN")
if not PROMETHEUS_BEARER_TOKEN:
    raise ValueError("No PROMETHEUS_BEARER_TOKEN specified")


async def wrap(i):
    metrics_seen = set()
    async for name, tp, value, labels in i:
        if name not in metrics_seen:
            yield "# TYPE %s %s" % (PREFIX + name, tp)
            metrics_seen.add(name)
        yield "%s%s %d" % (
            PREFIX + name,
            ("{%s}" % ",".join(["%s=\"%s\"" % j for j in labels.items()]) if labels else ""),
            value)


async def exporter_stats():
    # Export number of open file handles
    yield "exporter_file_descriptors", "gauge", len(os.listdir("/proc/self/fd")), {}


async def openvpn_stats(port, service):
    last_seen = Counter()

    # Export OpenVPN status
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(b"status 2\n")
    await writer.drain()
    while True:
        line = await reader.readline()
        values = line.decode("ascii").strip().split(",")
        header = values[0]

        if header == "END":
            break
        elif header == "CLIENT_LIST":
            _, cn, remote, _, _, rxbytes, txbytes, _, since, _, cid, pid, cipher = values
            labels = {"cn": cn, "service": service}
            yield "client_connected_since", "gauge", int(since), labels

            labels["cipher"] = cipher
            yield "client_rx_bytes", "counter", int(rxbytes), labels
            yield "client_tx_bytes", "counter", int(txbytes), labels
        elif header == "ROUTING_TABLE":
            _, addr, cn, remote, _, last_ref = values
            last_seen[cn] = max(last_seen[cn], int(last_ref))

    writer.close()
    await writer.wait_closed()

    for key, value in last_seen.items():
        yield "client_last_seen", "gauge", value, {"cn": key, "service": service}


@app.route("/metrics")
async def view_export(request):
    if request.token != PROMETHEUS_BEARER_TOKEN:
        raise exceptions.Forbidden("Invalid bearer token")

    async def streaming_fn(response):
        for i in exporter_stats(), openvpn_stats(7505, "openvpn-udp"), openvpn_stats(7506, "openvpn-tcp"):
            async for line in wrap(i):
                await response.write(line + "\n")

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            for port in (4001, 5001, 8001, 9001):
                async with session.get("http://127.0.0.1:%d/metrics" % port) as upstream_response:
                    async for line in upstream_response.content:
                        if not re.match("(# (HELP|TYPE) )?(pinecrypt|goredns)_", line.decode("ascii")):
                            continue
                        await response.write(line)

    return response.stream(streaming_fn, content_type="text/plain")

app.run(port=3001)
