# API Gateway Service

The Gateway is the SDK entry point for the data-focused platform.

It exposes a gRPC server on port `50051` and forwards calls by reading the
`x-target-service` request metadata.

Supported targets:

- `models`
- `data`

## Run

```bash
export MODELS_SERVICE_ADDR=localhost:50053
export DATA_SERVICE_ADDR=localhost:50054
uv run python -m services.gateway.main
```
