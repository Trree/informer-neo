FROM python:3.12-alpine
RUN apk update && apk upgrade && \
    apk add --no-cache \
    gcc \
    musl-dev \
    git \
    alpine-sdk \
    bash \
    python3 \
    libffi-dev \
    openssl-dev \
    mariadb-dev \
    mariadb-connector-c-dev
COPY app /usr/local/app
WORKDIR /usr/local/app
RUN pip3 install -r requirements.txt
