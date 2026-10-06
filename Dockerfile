# The production server (server/app.py): our code on top of the base image from Dockerfile.base. Build: see server/deploy.sh.
ARG BASE
FROM ${BASE}
COPY engine engine
COPY server server
COPY skill/SKILL.md skill/SKILL.md
CMD ["python", "-m", "server.app"]
