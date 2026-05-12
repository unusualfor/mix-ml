# Stage 1 — install dependencies
FROM registry.access.redhat.com/ubi9/python-311 AS deps

WORKDIR /build
COPY pyproject.toml .
RUN mkdir -p app && touch app/__init__.py && \
    python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir .

# Stage 2 — runtime
FROM registry.access.redhat.com/ubi9/python-311

COPY --from=deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /opt/app-root/src
COPY app/ app/

USER 1001
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
