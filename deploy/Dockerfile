FROM python:3.12-slim
WORKDIR /srv
COPY pyproject.toml README.md ./
COPY sharley ./sharley
COPY agents ./agents
COPY evals ./evals
RUN pip install --no-cache-dir .
RUN useradd -m sharley && chown -R sharley /srv
USER sharley
ENV SHARLEY_HOME=/srv/data SHARLEY_OFFLINE=1
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s CMD python -c "import urllib.request as u;u.urlopen('http://127.0.0.1:8000/api/health',timeout=2)"
CMD ["uvicorn", "--factory", "sharley.api:build_app", "--host", "0.0.0.0", "--port", "8000"]
