FROM python
MAINTAINER Pinecrypt Labs <info@pinecrypt.com>
RUN pip install sanic aiohttp
ADD exporter.py /exporter.py
CMD /exporter.py
