# Model Service

The Model Service provides:

- chat completion through external providers such as OpenAI and Anthropic
- external embedding providers such as OpenAI embeddings
- optional local embedding provider through `LOCAL_EMBEDDING_URL`

## Local Embedding Provider

The local provider expects an HTTP embedding server, such as Hugging Face Text
Embeddings Inference, reachable at `LOCAL_EMBEDDING_URL`.

```bash
export LOCAL_EMBEDDING_URL=http://localhost:8081
export LOCAL_EMBEDDING_MODELS=sentence-transformers/all-MiniLM-L6-v2
uv run python -m services.models.main
```

With Docker Compose:

```bash
docker compose --profile local-embedding up --build
```
