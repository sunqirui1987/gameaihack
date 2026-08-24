FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY configs ./configs
ENV GAMEAIHACK_CONFIGS=/app/configs
RUN pip install --no-cache-dir .
WORKDIR /data
ENTRYPOINT ["gameaihack"]
CMD ["--help"]
