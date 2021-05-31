#!/usr/bin/env python

import os
from motor.motor_asyncio import AsyncIOMotorClient
from sanic import Sanic, response

app = Sanic("exporter")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/default")

@app.listener('before_server_start')
async def setup_db(app, loop):
    app.ctx.db = AsyncIOMotorClient(MONGO_URI).get_default_database()

@app.route("/metrics")
async def view_export(request):
    coll = app.ctx.db["certidude_certificates"]
    async def streaming_fn(response):
        await response.write("# HELP pinecrypt_remote_last_seen Remote client last seen\n")
        await response.write("# TYPE pinecrypt_remote_last_seen gauge\n")
        async for doc in coll.find({"status":"signed", "last_seen":{"$exists":True}}, {"common_name":1, "last_seen":1}):
            await response.write("pinecrypt_remote_last_seen{cn=\"%s\"} %d\n" % (
                doc["common_name"], doc["last_seen"].timestamp()))
    return response.stream(streaming_fn, content_type='text/plain')

app.run(port=3001)
