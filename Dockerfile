FROM python:alpine

RUN apk update \
  && apk add \
    build-base \
    postgresql \
    postgresql-dev \
    libpq

RUN mkdir /usr/local/m3sync
WORKDIR /usr/local/m3sync
COPY ./requirements.txt .
COPY ./m3_sync.py .
RUN pip install -r requirements.txt && \
   adduser -D mm3sync && \
   touch /var/log/mm3sync.log && chown -R mm3sync /var/log/mm3sync.log
USER mm3sync
