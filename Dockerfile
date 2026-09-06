# --- frontend build ---
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- runtime ---
FROM python:3.13-slim
WORKDIR /app

RUN pip install --no-cache-dir \
      "fastapi>=0.115" "uvicorn[standard]" "pydantic>=2"

# Only the runtime half of the package is installed. The generator needs
# split-words, wordfreq and spylls; the server needs none of them, because
# it holds no dictionary — just the precomputed corpus (spec section 4.2).
COPY wortissimo/__init__.py ./wortissimo/
COPY wortissimo/rules/ ./wortissimo/rules/
COPY wortissimo/server/ ./wortissimo/server/

# The corpus is a 2.5MB committed artifact rather than an image build step.
# Regenerating it here would mean a dictionary download plus ~500MB of RAM
# for CharSplit's ngram model, on a machine that also has to run the game.
COPY data/puzzles.sqlite ./data/puzzles.sqlite
COPY --from=web /web/dist ./web/dist

ENV WORTISSIMO_PUZZLES=/app/data/puzzles.sqlite \
    WORTISSIMO_GAMES=/app/data/games.sqlite \
    WORTISSIMO_STATIC=/app/web/dist \
    PYTHONUNBUFFERED=1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

CMD ["uvicorn", "wortissimo.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
