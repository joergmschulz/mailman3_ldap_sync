FROM python:alpine

RUN apk update \
  && apk add \
    build-base \
    postgresql \
    postgresql-dev \
    libpq

RUN mkdir /usr/src/app
WORKDIR /usr/src/app
COPY ./requirements.txt .
COPY ./m3_sync.py .
RUN pip install -r requirements.txt

