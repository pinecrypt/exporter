FROM python
MAINTAINER Pinecrypt Labs <info@pinecrypt.com>
RUN pip install motor sanic
ADD exporter.py /exporter.py
CMD /exporter.py
