# Daily Development Report

## 2026-06-02

### Summary

- `boilerplate/` 내부 Git repository를 repository root로 flatten했다.
- 기존 root의 standalone `src/axe_suite_rag/` MVP package와 관련 `tests/test_chunker.py`를 제거했다.
- `genai_platform/`, `services/`, `proto/`, `tests/`, Docker/Compose 설정을 root로 이동해 future development path를 단순화했다.
- root `main.py`를 `genai_platform.cli:main`을 호출하는 얇은 entry point로 정리했다.
- `prd.md`의 실행 경로를 nested directory 기준에서 repository root 기준으로 갱신하고 현재 architecture flow를 추가했다.
- flattened root repository에 맞게 GitHub Actions CI workflow를 갱신했다.
- CI에서 dependency sync, ruff lint/format, pytest, Docker Compose config, CLI smoke test를 수행하도록 정리했다.
- 실행 중인 Docker stack을 대상으로 SDK, Gateway, Data, Model, VectorDB 경로를 검증하는
  `examples/live_stack_smoke.py`를 추가하고 indexed document, question, retrieved response를 출력하도록 했다.

### Files Changed

- `main.py`
- `.gitignore`
- `README.md`
- `pyproject.toml`
- `uv.lock`
- `genai_platform/`
- `services/`
- `proto/`
- `tests/`
- `docker/`
- `docker-compose.yml`
- `prd.md`
- `daily-development-report.md`
- `.github/workflows/ci.yml`
- `tests/test_cli.py`
- `examples/live_stack_smoke.py`
- `README.md`

### Verification

- `uv sync --frozen --extra postgres`
- `uv run ruff check`
- `uv run pytest -q` (`222 passed, 43 skipped`)
- `docker compose config --quiet`
- `uv run python main.py --help`
- `uv run ruff format --check .`
- `uv run python examples/live_stack_smoke.py`

## 2026-05-29

### Summary

- 기술 리서치 성격의 문서를 `research/` 폴더로 이동했다.
- `research/README.md`를 추가해 리서치 문서 목록과 사용 순서를 정리했다.
- PRD와 parse/clean interface 설계서의 리서치 문서 링크를 새 경로로 갱신했다.
- OCR 후보에 `PaddleOCR-VL-1.6`과 `LocateAnything-3B`를 추가하고 역할, serving, 한국어 평가 포인트를 정리했다.

### Files Changed

- `research/`
- `documents-parse-clean-interface-design.md`
- `prd.md`
- `daily-development-report.md`

### Verification

- `rg --files -g '*.md'`
- `rg -n "rag-pipeline-research|vector-db-tuning-parameters|ocr-embedding-technical-research" . -g '*.md'`
- `rg -n "PaddleOCR-VL|LocateAnything" research daily-development-report.md`

## 2026-05-28

### Summary

- `boilerplate/`에 가져온 `designing_ai_systems_repo`를 data service 개발 중심 구조로 축소했다.
- Docker Compose 기본 구성을 `gateway`, `data`, `models`, `postgres` 4개 container로 정리했다.
- 세션, 툴, 가드레일, 워크플로, 관측, 실험 서비스와 관련 Dockerfile/proto/SDK client/test/example 파일을 제거했다.
- `models` service에 local embedding HTTP provider를 추가하고, optional `embedding-local` Compose profile을 추가했다.
- `data` service가 `GENAI_GATEWAY_URL`을 통해 Gateway 경유로 `models.Embed`를 호출하도록 연결했다.
- `axe-suite up`으로 stack을 띄울 수 있도록 CLI wrapper를 추가했다.
- `axe-suite up`은 기본 background 실행으로 두고 local embedding container 사용 여부를 묻도록 조정했다.
- local 검증 속도를 위해 Postgres 이미지를 로컬에 있는 `pgvector/pgvector:pg16`으로 고정했다.
- Apple Silicon에서 TEI image를 실행할 수 있도록 `embedding-local`에 `linux/amd64` platform을 명시했다.
- Python SDK가 Gateway를 통해 Data/Models와 통신하는지 검증하는 smoke test를 추가했다.
- Docker stack을 local embedding 포함으로 띄운 뒤 Python SDK로 live Gateway 통신 smoke test를 통과했다.
- 터미널에서 직접 질문할 수 있도록 `axe-suite ask` 명령을 추가했다.
- `axe-suite up`에서 VectorDB 후보를 선택하도록 CLI를 확장했다.
- LanceDB를 service-container 후보에서 제외하고 `Qdrant`, `Chroma`, `Milvus`, `Weaviate`,
  `pgvector`, `OpenSearch`, `Azure AI Search` 선택 구조로 조정했다.
- 외부 VectorDB 선택 시 Postgres가 metadata, ingest jobs, keyword-search text를 유지하고 선택된
  backend가 vector upsert/search를 맡는 `ExternalVectorStore` wrapper를 추가했다.
- Qdrant, Chroma, Milvus, Weaviate, OpenSearch REST adapter와 Azure AI Search SDK adapter를 추가했다.
- Docker Compose에 Qdrant, Chroma, Milvus, Weaviate, OpenSearch profile을 추가했다.
- Hybrid search를 backend capability 기준으로 정리했다. pgvector, OpenSearch, Azure AI Search,
  Weaviate는 native hybrid를 우선 사용하고 Qdrant, Chroma, Milvus는 vector search + Postgres
  keyword fallback을 사용한다.
- `README.md`, Gateway/Model/Shared README, `pyproject.toml`, `uv.lock`을 data-focused boilerplate에 맞게 갱신했다.
- VectorDB별 tuning parameter, 추천 default, 실험 range, use case를 정리한 문서를 추가했다.
- OCR/image/table 후보와 embedding model 후보별 tuning parameter, serving best practice, 한국어 케이스를 정리한 문서를 추가했다.

### Files Changed

- `boilerplate/`
- `research/vector-db-tuning-parameters.md`
- `research/ocr-embedding-technical-research.md`
- `prd.md`
- `daily-development-report.md`

### Verification

- `docker compose config --quiet`
- `axe-suite --help`
- `uv run pytest tests/test_cli.py -q`
- `uv run pytest tests/test_cli.py tests/test_external_vector_store.py -q`
- `uv run pytest tests/test_data_search.py tests/test_external_vector_store.py -q`
- `docker compose config --quiet`
- `docker compose --profile qdrant|chroma|milvus|weaviate|opensearch config --quiet`
- `uv run pytest -q`
- `uv run pytest tests/test_sdk_gateway_smoke.py -q`
- `axe-suite up --local-embedding`
- `axe-suite up --vector-db pgvector --local-embedding`
- `axe-suite ask "VectorDB 후보 중에 뭐가 제일 단순해?" --top-k 3`
- live Docker Gateway 대상 Python SDK smoke script
- `python3 -m compileall genai_platform services proto`
- `uv run ruff check genai_platform services proto`
- `uv run pytest tests/test_data_*.py tests/test_model_*.py tests/test_base_client_channel.py tests/test_retry_interceptor.py -q`
- documentation-only update

### Notes

- 기본 실행은 4개 container다.
- local embedding server는 `axe-suite up --local-embedding`으로 별도 활성화한다.

## 2026-05-27

### Summary

- GitHub `designing_ai_systems_repo/services/data` 폴더를 기준으로 `data-rag-arch-and-interface-design.md`를 추가했다.
- 기존 `basic-rag-arch-and-interface-design.md` 형식을 참고해 purpose, high-level architecture, pipeline별 interface, contract, responsibility summary를 정리했다.
- `DataService`, `IngestionPipeline`, `SearchOrchestrator`, `VectorStore`, `PgvectorStore` 간 module boundary를 실제 class/function 이름 기준으로 문서화했다.
- 각 interface가 반환하는 값을 이해하기 쉽도록 index, ingest job, parser, chunking, embedding, vector store, search, plugin registration example output을 추가했다.
- `prd.md` 관련 문서에 Data Service RAG architecture/interface 설계서를 추가했다.

### Files Changed

- `data-rag-arch-and-interface-design.md`
- `prd.md`
- `daily-development-report.md`

### Notes

- 이 문서는 로컬 MVP 구현 코드가 아니라 외부 GitHub `services/data` 폴더 구조를 분석한 설계 문서다.
- `__init__.py`는 빈 package marker라 interface 설계 대상에서 제외했다.

## 2026-05-27

### Summary

- `basic-rag-arch-and-interface-design.md`를 basic RAG architecture/interface 설계서로 확장했다.
- 두 main pipeline을 `Parsing & Store Embeddings`와 `Query & Answer`로 분리해 정리했다.
- `PDF -> ParsedDocument -> ChunkedDocument` 흐름을 먼저 설명하고, embedding/store/query/retrieve 인터페이스를 같은 형식으로 추가했다.
- 현재 scope에서 `RetrievalAnswer`는 LLM 생성 답변이 아니라 검색 결과 묶음임을 명확히 했다.
- `prd.md` 관련 문서에 basic RAG architecture/interface 설계서를 추가했다.

### Files Changed

- `basic-rag-arch-and-interface-design.md`
- `prd.md`
- `daily-development-report.md`

### Notes

- OCR, table extraction, image extraction, LLM answer generation은 계속 scope 밖으로 둔다.
- 현재 문서는 코드와 1:1 매칭보다 다음 architecture 개발을 위한 component boundary 정의에 초점을 둔다.

## 2026-05-22

### Summary

- PDF RAG 이해용 MVP 구현을 추가했다.
- `main.py`를 CLI entry point로 만들고, PDF ingest와 query 명령을 분리했다.
- PDF text 추출, text chunking, `all-MiniLM-L6-v2` embedding, ChromaDB local persistent 저장/검색 흐름을 구현했다.
- ChromaDB는 별도 server 없이 `PersistentClient`로 `./data/chroma`에 저장하도록 구성했다.
- chunk metadata에 source path, page number, chunk index를 저장해 검색 결과에서 출처를 확인할 수 있게 했다.
- `prd.md`에 이번 MVP 구현 범위와 실행 방식을 업데이트했다.
- 구현된 MVP를 기준으로 `pdf-rag-mvp-interface-design.md` 인터페이스 설계서를 추가했다.
- 설계서에는 CLI command, component map, data contract, ingest/query sequence, failure case를 정리했다.
- `prd.md` 관련 문서에 PDF RAG MVP 인터페이스 설계서를 추가했다.

### Files Changed

- `pyproject.toml`
- `uv.lock`
- `.gitignore`
- `main.py`
- `src/axe_suite_rag/chunker.py`
- `src/axe_suite_rag/cli.py`
- `src/axe_suite_rag/embedder.py`
- `src/axe_suite_rag/pdf_reader.py`
- `src/axe_suite_rag/vector_store.py`
- `tests/test_chunker.py`
- `pdf-rag-mvp-interface-design.md`
- `prd.md`
- `daily-development-report.md`

### Notes

- 현재 구현은 OCR과 table 처리를 하지 않는다.
- scanned PDF는 텍스트 추출이 되지 않으면 실패하도록 둔다.
- 한국어 검색 품질은 실제 PDF sample로 별도 확인이 필요하다.

## 2026-05-14

### Summary

- `research/rag-pipeline-research.md`에 RAG pipeline 리서치를 정리했다.
- VectorDB/search backend 후보를 전용 VectorDB, 기존 DB 확장형, 검색엔진 기반으로 나누어 비교했다.
- Azure AI Search를 필수 비교 대상으로 추가했다.
- OpenAI embedding model과 OSS/open-weight embedding model 후보를 장단점과 배포 스펙 기준으로 정리했다.
- 첨부 문서 parsing 관점에서 HWP/HWPX, Word, PowerPoint, Excel, PDF, Markdown, HTML 처리 후보 라이브러리를 조사했다.
- 이미지와 표가 많은 문서 처리를 위해 OCR, image handling, table extraction 후보를 조사하고 Azure AI Document Intelligence를 필수 비교 후보로 추가했다.
- 이전 표현을 이미지 처리와 표 구조 추출의 별도 capability로 수정했다.
- VectorDB별 HNSW/IVF/search-time/build-time 튜닝 파라미터와 PoC 평가 계획을 정리했다.
- 지금까지의 요구사항을 `prd.md`로 정리했다.
- `prd.md` 상단 목적에 맞춰 Research PRD 성격, 의사결정 기준, PoC 검증 기준을 명확히 다듬었다.

### Files Changed

- `research/rag-pipeline-research.md`
- `prd.md`
- `daily-development-report.md`

### Notes

- 현재 단계는 구현이 아니라 요구사항/기술 리서치 정리 단계다.
- 실제 기술 선택은 sample corpus 기반 parsing quality, retrieval quality, cost, latency 평가 후 결정해야 한다.

## 2026-05-15

### Summary

- `prd.md`를 상세 리서치 문서가 아닌 리서치 요청 PRD로 간략화했다.
- 상세 후보 비교, 장단점, 튜닝 파라미터는 `research/rag-pipeline-research.md`에 두고 `prd.md`에서는 리서치 범위와 산출물만 정의하도록 정리했다.

### Files Changed

- `prd.md`
- `daily-development-report.md`

## 2026-05-18

### Summary

- `research/rag-pipeline-research.md`의 핵심 내용을 요약한 `research/rag-pipeline-research-summary.md`를 추가했다.
- RAG component 후보 간 기술 비교라는 목적이 드러나도록 parsing, OCR/image/table, embedding, VectorDB/search backend, tuning, evaluation을 요약했다.
- `research/rag-pipeline-research-summary.md`에 VectorDB/search backend 후보별 장단점 비교표를 추가했다.
- `research/rag-pipeline-research-summary.md`에 OpenAI 및 OSS/open-weight embedding model 후보별 세부 비교표를 추가했다.
- Markdown preview 호환성을 고려해 Mermaid workflow에서 HTML line break를 사용하지 않았다.
- `prd.md` 산출물 목록에 리서치 요약본을 추가했다.

### Files Changed

- `research/rag-pipeline-research-summary.md`
- `prd.md`
- `daily-development-report.md`

## 2026-05-20

### Summary

- `Documents -> Parse and clean` 흐름의 내부 인터페이스 설계서 `documents-parse-clean-interface-design.md`를 추가했다.
- parsing/cleaning 단계의 request/response, 표준 출력 schema, warning/error model, component contract를 정리했다.
- 인터페이스 설계서가 익숙하지 않아도 읽을 수 있도록 high-level to low-level 설명과 예시를 추가했다.
- API 설계와 인터페이스 설계의 차이를 RAG parsing 흐름 예시로 구분해 설명했다.
- `prd.md` 산출물 목록에 RAG 주요 흐름별 인터페이스 설계서를 추가했다.

### Files Changed

- `documents-parse-clean-interface-design.md`
- `prd.md`
- `daily-development-report.md`
