FROM python
RUN pip install motor sanic
ADD exporter.py /exporter.py
CMD /exporter.py
