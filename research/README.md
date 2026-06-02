# Research Documents

이 폴더는 Axe Suite RAG 개발 전에 참고할 기술 리서치 자료를 모아둔 곳이다.
구현 코드나 interface 설계서가 아니라, 후보 기술 비교와 튜닝/운영 판단 기준을 정리한다.

## Documents

| 문서 | 내용 |
| --- | --- |
| [RAG Pipeline Research](rag-pipeline-research.md) | RAG parser, OCR, embedding, VectorDB 후보 전체 리서치 원문 |
| [RAG Pipeline Research Summary](rag-pipeline-research-summary.md) | 전체 리서치 요약본 |
| [VectorDB Tuning Parameters Guide](vector-db-tuning-parameters.md) | VectorDB별 튜닝 파라미터, default, range, use case |
| [OCR and Embedding Technical Research Guide](ocr-embedding-technical-research.md) | OCR/image/table 후보와 embedding model 후보별 튜닝, serving, 한국어 케이스 |

## How To Use

1. 기술 선택 전에는 summary를 먼저 읽는다.
2. VectorDB를 구현하거나 튜닝할 때는 VectorDB tuning guide를 본다.
3. OCR 또는 embedding model을 바꿀 때는 OCR/embedding guide를 본다.
4. 실제 구현 기준은 `prd.md`와 각 interface design 문서에 반영한다.
