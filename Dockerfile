# The production server (server/app.py): our code on top of the base image from Dockerfile.base. Build: see server/deploy.sh.
ARG BASE
FROM ${BASE}
COPY engine engine
COPY server server
COPY skill/SKILL.md skill/SKILL.md
RUN .venv-agnn/bin/python engine/models/analysisgnn_runner.py --list-files /app/artifacts/models/model.ckpt engine/models/model-files.txt
RUN python -m server.app --list-files
CMD ["python", "-m", "server.app"]
