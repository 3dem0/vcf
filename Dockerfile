FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY bridge ./bridge
COPY tools/probe.py ./tools/probe.py

FROM runtime AS tests
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tools ./tools
COPY tests ./tests
COPY .env.example ./
RUN python -m pytest -q -p no:cacheprovider tests && touch /tests-passed

FROM runtime AS final
COPY --from=tests /tests-passed /app/.tests-passed
USER 1000:1000
EXPOSE 8443
CMD ["python", "-m", "bridge"]
