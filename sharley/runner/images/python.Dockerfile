# Runner image for the docker-api profile. Dependencies the implementer may use must be baked in:
# containers run with --network none.
FROM python:3.12-slim
RUN pip install --no-cache-dir pytest httpx fastapi "uvicorn[standard]" pydantic sqlalchemy pyjwt "passlib[bcrypt]" python-multipart
WORKDIR /app
