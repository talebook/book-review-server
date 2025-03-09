FROM alpine

ARG GIT_VERSION=""
LABEL CODE_VERSION=$GIT_VERSION
LABEL Author="Rex <talebook@foxmail.com>"

RUN sed -i 's@dl-cdn.alpinelinux.org@mirrors.aliyun.com@g' /etc/apk/repositories
RUN apk add py3-pip python3 gettext curl bind-tools openssl
RUN apk add py3-tornado py3-beautifulsoup4 py3-chardet py3-sqlalchemy py3-pymysql py3-cryptography bash

WORKDIR /app/
COPY . /app/

EXPOSE 80/tcp
ENTRYPOINT /app/entrypoint.sh
