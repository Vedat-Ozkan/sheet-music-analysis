# The production server (server/app.py) with the AnalysisGNN draft model. Build: see server/deploy.sh.
FROM python:3.11-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

# The engine and server.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# The draft model, in its own environment as on the development machine (README, "Draft model").
COPY server/requirements-agnn.txt server/
RUN uv venv .venv-agnn --python /usr/local/bin/python3.11 \
 && VIRTUAL_ENV=/app/.venv-agnn uv pip install -r server/requirements-agnn.txt \
      --index-url https://pypi.org/simple \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      --find-links https://data.pyg.org/whl/torch-2.5.0+cpu.html \
      --index-strategy unsafe-best-match \
 && VIRTUAL_ENV=/app/.venv-agnn uv pip install setuptools wheel \
 && VIRTUAL_ENV=/app/.venv-agnn uv pip install --no-deps --no-build-isolation \
      "git+https://github.com/manoskary/graphmuse.git@acd464f0cf11c65bda38f0d32a31e078f7941d78" \
 && git clone https://github.com/manoskary/analysisgnn vendor/analysisgnn \
 && git -C vendor/analysisgnn checkout e115182fb29b74bdcb6bf3547ed427d967580947 \
 && rm -rf vendor/analysisgnn/.git \
 && VIRTUAL_ENV=/app/.venv-agnn uv pip install --no-deps vendor/analysisgnn

# Weights from the author's Hugging Face Space (card: license mit).
RUN mkdir -p artifacts/models \
 && curl -fL -o artifacts/models/model.ckpt https://huggingface.co/spaces/manoskary/analysisgnn/resolve/main/checkpoint/model.ckpt \
 && echo "53d106038fea6a5ab3d4c0a19617736dff5f0299deffaf240ebd484c11f91c67  artifacts/models/model.ckpt" | sha256sum -c

FROM python:3.11-slim
WORKDIR /app
COPY --from=build /app/.venv .venv
COPY --from=build /app/.venv-agnn .venv-agnn
COPY --from=build /app/artifacts artifacts
COPY engine engine
COPY server server
COPY skill/SKILL.md skill/SKILL.md
# GitPython (imported by the model code) only needs git for experiment logging, which the server does not use.
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 GIT_PYTHON_REFRESH=quiet
CMD ["python", "-m", "server.app"]
