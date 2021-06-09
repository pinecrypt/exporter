#!/usr/bin/env python

import asyncio
import os
from collections import Counter
from motor.motor_asyncio import AsyncIOMotorClient
from sanic import Sanic, response, exceptions

app = Sanic("exporter")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/default")
PROMETHEUS_BEARER_TOKEN = os.getenv("PROMETHEUS_BEARER_TOKEN")
if not PROMETHEUS_BEARER_TOKEN:
    raise ValueError("No PROMETHEUS_BEARER_TOKEN specified")


@app.listener("before_server_start")
async def setup_db(app, loop):
    app.ctx.db = AsyncIOMotorClient(MONGO_URI).get_default_database()


async def wrap(i, prefix="pinecrypt_gateway_"):
    metrics_seen = set()
    async for name, tp, value, labels in i:
        if name not in metrics_seen:
            yield "# TYPE %s %s" % (name, tp)
            metrics_seen.add(name)
        yield "%s%s %d" % (
            prefix + name,
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
    coll = app.ctx.db["certidude_certificates"]

    async def streaming_fn(response):
        for i in exporter_stats(), openvpn_stats(7505, "openvpn-udp"), openvpn_stats(7506, "openvpn-tcp"):
            async for line in wrap(i):
                await response.write(line + "\n")

    return response.stream(streaming_fn, content_type="text/plain")

app.run(port=3001)
