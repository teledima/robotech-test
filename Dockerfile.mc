FROM alpine:3.24

RUN wget https://dl.min.io/aistor/mc/release/linux-amd64/mc -O /usr/bin/mc
RUN chmod +x /usr/bin/mc

ENTRYPOINT [ "mc" ]
