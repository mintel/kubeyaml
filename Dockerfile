FROM six8/pyinstaller-alpine:latest as pyinstaller
WORKDIR /home/kubeyaml
COPY kubeyaml.py requirements.txt ./
RUN apk add yaml-dev && /pyinstaller/pyinstaller.sh --noconfirm --clean kubeyaml.py

FROM alpine:3.9

ENTRYPOINT ["/usr/lib/kubeyaml/kubeyaml"]
COPY --from=pyinstaller /home/kubeyaml/dist/kubeyaml /usr/lib/kubeyaml
