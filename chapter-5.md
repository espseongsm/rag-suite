chapter five
The Data Service: teaching AI what your organization knows
This chapter covers
Designing the Data Service to give teams searchable knowledge indexes without building their own parsing, chunking, and embedding pipelines
Organizing knowledge into isolated indexes so teams configure retrieval independently
Building an ingestion pipeline that detects file formats, extracts text, and chunks documents into searchable pieces
Generating embeddings through the Model Service to reuse provider abstraction, fallback logic, and cost tracking
Abstracting vector storage and search to support multiple backends, with a complete pgvector implementation
Supporting hybrid retrieval by extending the vector store interface with optional keyword search
Exposing the Data Service through the gRPC contract and platform SDK
An AI assistant that remembers your conversation but doesn't know your company's policies, products, or procedures is still going to make things up. It will hallucinate confidently about return windows, invent product features, and cite policies that don't exist. Conversational memory, which we built in Chapter 4, is only half the story. The other half is grounding: connecting AI applications to organizational knowledge so that responses reflect reality rather than plausible guesses.

The Data Service provides this grounding. It gives teams a way to turn documents such as company policies, product documentation, support articles, technical manuals, and internal wikis into searchable knowledge without each team building its own parsing, chunking, embedding, and storage pipeline. The platform lets teams create isolated knowledge indexes, choose how their documents get chunked and embedded, and search across them without worrying about the infrastructure underneath.

The retrieval problem here is fundamentally different from what we solved in Chapter 4. Conversation history is structured: messages with roles, stored in sequence, looked up by ID. Organizational knowledge is unstructured. A 50-page PDF about insurance policies doesn't have row IDs or foreign keys. An HTML support article doesn't slot into a relational schema. And instead of looking up a record by its identifier, we need to find the paragraphs most relevant to a question phrased in natural language. The question "can I return opened electronics?" needs to match a paragraph buried on page 12 of a return policy document, even though the paragraph might use completely different words. This is a semantic matching problem, and it requires platform infrastructure that looks nothing like what we've built so far.

In Chapter 2, we previewed what the developer experience should look like:

1
2
3
4
5
relevant_info = platform.data.search(
    query=question,
    index="patient_procedures"
)

Behind that simple call lies a sophisticated pipeline: documents broken into meaningful pieces, those pieces converted into mathematical representations that capture their meaning, a storage system optimized for finding similar representations quickly, and a search operation that combines semantic understanding with metadata filtering. We will build all of it in this chapter.

livebook features:
highlight, annotate, and bookmark
  
You can automatically highlight a piece of text simply by selecting it. Create a note by clicking anywhere on the page and start typing.
Disable quick notes and highlights?
5.1From documents to searchable knowledge
Before we write any code, let's understand the problem from first principles. Suppose an organization has a document describing its return policy. Somewhere on page 3, there's a paragraph explaining that electronics can be returned within 30 days with a receipt and original packaging, subject to a 15% restocking fee for opened items. A customer asks: "What happens if I want to return a laptop I already opened?" How does a system connect that question to that specific paragraph?

The naive approach would be keyword matching: search the document for words like "return," "laptop," and "opened." But the paragraph might use "electronics" instead of "laptop" and "original packaging" instead of "opened." Keyword matching is brittle because language is flexible. People express the same idea in many different ways.

The approach that works is semantic search: comparing the meaning of the question against the meaning of document passages, regardless of the specific words used. This requires several steps, each solving a distinct problem.

The document is too large to compare directly. You can't meaningfully compare a short question against a 50-page document. The comparison needs to happen at a more granular level, between the question and individual passages that each cover a focused topic. This means breaking documents into smaller pieces, which we'll call chunks. The quality of these chunks matters enormously. A chunk that splits a sentence in half, or merges two unrelated paragraphs, produces poor search results. We need chunking strategies that preserve semantic coherence.
String matching misses meaning; embeddings don't. String matching can check whether two strings are identical, but it can't assess whether two sentences are about the same thing. To enable semantic comparison, we need to convert text into numerical representations that capture meaning. These representations are called embeddings: dense vectors (arrays of numbers) where similar meanings produce similar vectors. The sentence "return a laptop I opened" and the phrase "electronics returns, restocking fee for opened items" should produce vectors that are close together in this numerical space, even though they share almost no words. Modern embedding models, trained on massive text corpora, achieve this remarkably well. The storage systems designed to hold these vectors and retrieve them by similarity are commonly called vector stores or vector databases.
Finding similar vectors needs to be fast. At small scale, you could compare a query vector against every stored vector directly. But with millions of vectors, brute-force comparison becomes impractical. Production vector stores use approximate nearest-neighbor algorithms that navigate mathematical structures to quickly narrow down candidates, finding results in milliseconds without exhaustive comparison.
Search results need context. Returning a raw chunk of text isn't enough. Workflows need to know which document the chunk came from (for citations), how confident the match is (for thresholding), and any structured attributes about the document, its metadata (for filtering). Consider a search for "how to reset a device." Both a customer-facing troubleshooting guide and an internal engineering runbook might describe the same reset procedure, making them semantically almost identical. But a customer support workflow needs only the customer-facing version. Metadata filtering (say, audience: "customer" vs audience: "internal") narrows results to the right domain in ways that semantic similarity alone cannot.
Figure 5.1 shows a complete semantic search pipeline.

Figure 5.1 The retrieval pipeline from document to search result. A source document enters the ingestion pipeline, where it is parsed into clean text and then broken into semantically coherent chunks. Each chunk is passed through an embedding model to produce a dense vector representation. The vectors, along with the original chunk text and metadata, are stored in a vector database. At query time, the user's question follows the same embedding process to produce a query vector, which is compared against stored vectors using similarity search. The top matching chunks are returned with their source attribution, relevance scores, and metadata, ready to be injected into the model's context as grounding information.

This pipeline is what the Data Service implements. We'll work through it piece by piece. First, we need an organizational unit that groups related knowledge together and keeps unrelated knowledge apart: indexes. Then we need to get documents into those indexes through an ingestion pipeline that handles diverse file formats. The ingestion pipeline breaks documents into chunks using configurable strategies and converts those chunks into embeddings through the Model Service. The embeddings are stored in a vector store abstraction that supports multiple backends. At query time, search operations find the most relevant chunks through similarity matching and metadata filtering, optionally combining vector and keyword search for hybrid retrieval. Finally, we formalize all of this into the gRPC contract and SDK client and connect it with the Session Service and Model Service so that workflows can retrieve relevant knowledge and feed it directly into the model's context, a pattern famously known as retrieval-augmented generation (RAG).

livebook features:
discuss
  
Ask a question, share an example, or respond to another reader. Start a thread by selecting any piece of text and clicking the discussion icon.
5.2Indexes: organizing knowledge
Before we can ingest documents or run searches, we need an organizational unit: something that groups related knowledge together and keeps unrelated knowledge apart. In the Data Service, this unit is an index.

An index is a named, isolated collection of documents with its own embedding configuration and search behavior. Just as sessions in Chapter 4 each maintain their own independent conversation history, each index maintains its own independent body of knowledge. A team might create one index for product documentation, another for HR policies, another for engineering runbooks.

5.2.1Why isolation matters
Consider a platform serving multiple teams. The support team maintains an index of troubleshooting guides. The legal team maintains an index of compliance documents. When a support workflow searches for "how to reset a device," it should search the troubleshooting index, not the compliance index. When a legal workflow searches for "data retention requirements," it should search compliance documents, not troubleshooting guides. Figure 5.2 shows this isolation in practice.

Figure 5.2 Index isolation in the Data Service. Two teams (Support and Legal) each maintain their own index. Each index has its own embedding model configuration, chunking strategy, and document collection. Searches are scoped to a specific index, ensuring that a support query never returns legal documents and vice versa. The Data Service manages all indexes through a unified interface while enforcing isolation boundaries.

This isolation is more than just filtering convenience. Different indexes can use different embedding models. A legal team working with dense regulatory text might benefit from an embedding model trained on legal corpora. A product team documenting API endpoints might prefer a model optimized for technical content. The platform supports this by making embedding configuration an index-level setting rather than a global one.

TIP
The platform can also act as a gatekeeper for embedding model selection. Some models are significantly more expensive per token than others, and some route data to external APIs that may not be approved for sensitive internal documents. By maintaining an allowed list of embedding models, the platform can reject index creation requests that specify unapproved models, catching cost or compliance issues at configuration time rather than after documents have been ingested.

Different indexes can also use different chunking strategies. A knowledge base of short FAQ entries, each just a question and a two-sentence answer, would be mangled by a chunker that tries to combine multiple entries into 512-token blocks. Each FAQ entry is already a self-contained unit and should stay that way. Meanwhile, a collection of 100-page technical manuals needs aggressive chunking to break dense content into retrievable pieces, ideally respecting section boundaries so that a chunk about "authentication" doesn't bleed into a chunk about "rate limiting." Making these decisions per-index gives teams the flexibility to optimize for their specific content without affecting other teams.

5.2.2Index configuration
When creating an index, the platform needs to know a few things: what to call it, which embedding model to use, and how to chunk documents that get ingested into it. Listing 5.1 shows what an index configuration looks like.

Listing 5.1 Index configuration dataclass
1
2
3
4
5
6
7
8
9
10
@dataclass
class IndexConfig:
    name: str
    embedding_model: str =
➥"text-embedding-3-small"
    embedding_dimensions: int = 1536
    chunking_strategy: str = "fixed"
    chunk_size: int = 512
    chunk_overlap: int = 50
    metadata_schema: Optional[Dict] = None
The name field in listing 5.1 uniquely identifies the index. The embedding_model and embedding_dimensions fields specify how text will be converted to vectors. These must be set at creation time and can't change later, because changing the embedding model would invalidate every vector already stored. Vectors from different models exist in different mathematical spaces and can't be compared meaningfully, so mixing them in a single index silently corrupts search results. The platform should reject any attempt to change an existing index's embedding model.

That doesn't mean teams are stuck with their initial choice forever. To switch embedding models, you create a new index configured with the new model, re-ingest your documents into it, and run validation queries to verify that retrieval quality meets expectations. Once validated, you swap traffic from the old index to the new one. The old index stays around as a rollback option until the team is confident in the migration. The index abstraction is what makes this possible. Because each index encapsulates its own embedding configuration, two indexes using different models can coexist without interfering with each other.

The chunking_strategy, chunk_size, and chunk_overlap fields control how ingested documents get broken into chunks. We'll explore these parameters in detail in section 5.3. The metadata_schema field optionally constrains what metadata can be attached to documents when they're ingested. Without it, metadata keys are free-form, and nothing stops one team from tagging documents with dept while another uses department for the same concept. When a workflow later filters search results by department, it silently misses every document tagged with dept. A schema catches these inconsistencies at ingestion time rather than letting them corrupt search results.

5.2.3Index operations
The platform needs to support creating, listing, and deleting indexes. These are straightforward lifecycle operations. Listing 5.2 shows the abstract interface.

Listing 5.2 Index management operations
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
class DataService:

    def create_index(self, config: 
➥IndexConfig) -> Index:
        """Create a new index with the specified configuration."""
        pass

    def list_indexes(self) -> List[Index]:
        """Return all indexes the caller has access to."""
        pass
 
    def delete_index
➥(self, index_name: str) -> bool:
        """Delete an index and all its documents, chunks, and vectors."""
        pass

    def get_index(self, index_name: str) -> Index:
        """Retrieve index metadata and configuration."""
        pass
The Index object returned by the operations in listing 5.2 carries the configuration information like document count, total chunks, creation timestamp, and a timestamp to indicate when documents were last ingested. Listing 5.3 shows what this looks like.

Listing 5.3 Index dataclass
1
2
3
4
5
6
7
8
9
@dataclass
class Index:
    name: str
    config: IndexConfig
    owner: str = ""
    document_count: int = 0
    total_chunks: int = 0
    created_at: datetime = None
    last_ingested_at: Optional[datetime] = None
The last_ingested_at field matters because ingestion is rarely a one-time event. Many teams run ingestion on a schedule, pulling updated documents from a content management system or syncing a shared drive nightly. This timestamp lets teams quickly verify that their pipeline is running and their index is current, without inspecting individual documents.

TIP
Name your indexes with a clear convention that includes the team or domain: support-troubleshooting, legal-compliance. When the platform grows to dozens of indexes, discoverable names prevent confusion about what each index contains.

Creating an index doesn't involve any documents. It sets up the empty container: a name, an embedding configuration, a chunking strategy, and the underlying storage structures. Think of it like creating a database table before inserting any rows. The index sits ready to receive documents through the ingestion pipeline, which we'll build in the next section. This separation is deliberate. Index creation is a one-time setup step. Ingestion is an ongoing operation that might run on a schedule or be triggered by document updates.

In a multi-team platform, access control on indexes is a first-class concern, not an afterthought. The legal team shouldn't be able to delete the support team's index, and a rogue ingestion job shouldn't be able to write documents into an index it doesn't own. The owner field on the Index dataclass provides the foundation. A production implementation would check the caller's identity against the index owner before allowing delete operations. For now, the ownership metadata is in place; the enforcement layer is a straightforward addition once the platform has an authentication mechanism.

livebook features:
settings
  
Update your profile, view your dashboard, tweak the text size, or turn on dark mode.
5.3Ingestion pipeline: from raw files to vectors
With indexes established as the organizational unit, we need a way to get documents into them. The ingestion pipeline takes a source file, extracts its text content, breaks it into chunks, generates embeddings for each chunk, and stores everything in the vector store. This section walks through the entire pipeline: parsing documents into clean text, chunking that text into retrievable pieces, and converting those pieces into the vector representations that power semantic search.

5.3.1The challenge of diverse formats
Organizations don't store their knowledge in one tidy format. Policies live in PDFs. Product documentation is in Markdown. Support articles are HTML pages. Internal procedures might be Word documents. The ingestion pipeline needs to handle all of these, extracting clean, structured text regardless of the source format.

This is a harder problem than it might seem. PDFs are notoriously difficult to parse because the format is designed for visual rendering, not text extraction. A two-column layout might interleave text from both columns. Tables might lose their structure. Headers and footers repeat on every page. Word documents embed formatting, comments, and revision history alongside the actual content. HTML pages include navigation elements, advertisements, and boilerplate alongside the article text.

Without a shared ingestion pipeline, every team building a RAG application has to solve these parsing problems independently. The support team writes their own PDF extractor. The legal team writes theirs. Neither team wanted to spend their time on PDF parsing in the first place. A platform-level ingestion pipeline solves this once: a single, well-tested set of parsers that every team benefits from. When someone fixes the two-column PDF bug, every index that ingests PDFs gets the fix.

That said, the platform shouldn't be a black box. Some teams will have documents with unusual formatting or domain-specific structure that the default parsers don't handle well. The pipeline should be extensible, allowing teams to register custom parsers for specialized formats while still using the platform's chunking, embedding, and storage infrastructure. The default path handles 90% of cases. The extension points handle the rest.

5.3.2Pipeline architecture
The ingestion pipeline processes documents through a sequence of stages, each with a clear responsibility. The output of one stage feeds directly into the next, and the pipeline as a whole transforms a raw file into a set of embedded, searchable chunks.

The first stage is format detection: examining the file to determine whether it's a PDF, a Word document, HTML, Markdown, or plain text. Once the format is known, the pipeline routes the file to the appropriate parser. The parser extracts clean text while preserving structural information like headings, paragraphs, and section boundaries. This structural information isn't just nice to have; it feeds directly into the structure-aware chunking strategy we'll build later in this section.

After text extraction, the pipeline captures metadata. Some metadata comes from the document itself: filename, page count, word count, detected language. Other metadata is supplied by the caller at ingestion time: department, document type, author, version, tags. This metadata travels with every chunk derived from the document and becomes the foundation for filtered search.

Finally, the extracted text is broken into chunks according to the index's configured strategy, each chunk is embedded through the Model Service, and the chunks, embeddings, and metadata are stored in the vector store. Figure 5.3 shows this complete flow.

Figure 5.3 The document ingestion pipeline. A source file enters the pipeline and passes through five stages: (1) Format Detection identifies the file type (PDF, DOCX, HTML, Markdown, TXT). (2) Text Extraction uses format-specific parsers to produce clean text while preserving structural information like headings and paragraphs. (3) Metadata Extraction captures both automatic metadata (filename, page count, word count, ingestion timestamp) and user-supplied metadata (department, document type, author, tags). (4) Chunking splits the extracted text into semantically coherent pieces according to the index's configured strategy. (5) Embedding converts each chunk into a dense vector through the Model Service. The output is a set of vectors with their original text and metadata, ready for storage in the vector store.

5.3.3Format detection and text extraction
The first two stages, format detection and text extraction, work together. The pipeline identifies what kind of file it's looking at, then hands it to a parser that knows how to extract text from that specific format.

The parser's job is to produce an ExtractedDocument: the clean text plus structural information about how the document is organized. Listing 5.4 shows the data model and parser interface.

Listing 5.4 Document parser interface and extracted document model
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict

@dataclass
class DocumentSection:
    content: str
    heading: Optional[str] = None
    level: int = 0
    page_number: Optional[int] = None

@dataclass
class ExtractedDocument:
    sections: List[DocumentSection]
    metadata: Dict[str, str]

    @property
    def text(self) -> str:
        return "\n\n".join(s.content for s in self.sections)

class DocumentParser(ABC):
    @abstractmethod
    def parse(self, file_bytes:
➥bytes) -> ExtractedDocument:
        """Extract text and structure from a document."""
        pass
The ExtractedDocument captures the document's structure: which sections exist, what their headings are, and how they're nested. The full text is derived from sections on demand rather than stored separately. Structure-aware chunking works directly with the sections, while fixed-size chunking calls the text property to get the content as a single string. For plain text files with no structural markers, the parser returns a single section with no heading. A PDF about insurance policies might produce sections like "Coverage Types," "Filing a Claim," and "Exclusions," each with their heading text and hierarchy level. A Markdown file makes this even easier since headings are explicit in the syntax.

Each file format gets its own parser implementation. A PDFParser uses libraries like PyMuPDF or pdfplumber to handle multi-column layouts, tables, and repeated headers. A MarkdownParser has an easier job since Markdown's heading levels, paragraph breaks, and code blocks are already explicit in the syntax. An HTMLParser needs to strip away navigation, sidebars, and boilerplate to find the actual article content. Each parser is a subclass of DocumentParser, implementing the same parse method and returning the same ExtractedDocument structure as seen in listing 5.4.

The format detection itself is straightforward. The pipeline inspects file headers first to verify actual file content, then falls back to file extensions for formats without reliable magic byte signatures. Listing 5.5 shows the routing logic.

Listing 5.5 Format detection and parser routing
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
class IngestionPipeline:
    def __init__(self):
        self.parsers = {
            "pdf": PDFParser(),
            "docx": DocxParser(),
            "html": HTMLParser(),
            "md": MarkdownParser(),
            "txt": PlainTextParser(),
        }

    def detect_format(self, filename: str, file_bytes: bytes) -> str:
        if file_bytes[:5] == b"%PDF-":
            return "pdf"
        if file_bytes[:4] == b"PK\x03\x04":
            return "docx"
        # ... other magic byte checks for supported formats
 
        extension = filename.rsplit(".", 1)[-1].lower()
        if extension in self.parsers:
            return extension
 
        return "txt"
 
    def extract(self, filename: str, file_bytes: bytes) -> ExtractedDocument:
        format_type = self.detect_format(filename, file_bytes)
        parser = self.parsers[format_type]
        return parser.parse(file_bytes)
The parsers dictionary is the extension point for new formats. Adding support for a new format means implementing one DocumentParser subclass and registering it here. The rest of the pipeline that includes chunking, embedding, and storage, works unchanged. To make this extensibility a first-class feature of the platform rather than something that requires modifying pipeline internals, teams should be able to register custom parsers through the SDK. Listing 5.6 shows what this looks like:

Listing 5.6 Registering a custom parser through the SDK
1
2
3
4
5
6
7
8
9
10
class ConfluenceParser(DocumentParser):
    def parse(self, file_bytes: bytes) -> ExtractedDocument:
        # Parse Confluence export format
        ...

platform.data.register_parser(
    format="confluence",
    parser=ConfluenceParser(),
    version="1.0.0",
)
A team that needs to ingest Confluence pages or Notion exports can write a parser for that format and plug it in without modifying any other part of the system. Versioning tracks which parser version was used for each ingestion, so if a parser changes, teams know which documents need to be re-ingested with the updated logic.

What about ingesting images, audio and video?
This chapter focuses on text-based ingestion, and for good reason: text is the most common form of organizational knowledge, and the retrieval pipeline is already complex enough without adding modalities. But a mature AI platform will eventually need to handle more than text. Product catalogs contain images. Training materials include videos.

The parser registration mechanism we built earlier is what makes this tractable. A team can register a parser that transcribes audio to text using a speech-to-text model, or one that runs OCR on scanned documents, and the rest of the pipeline, chunking, embedding, storage, and search, works unchanged. This "convert to text first" approach works surprisingly well for many use cases.

True multi-modal RAG, where an image is embedded directly as an image and compared against text queries in a shared embedding space, is a more ambitious undertaking. It requires multi-modal embedding models that can map both text and images into the same vector space, along with different storage considerations for larger and higher-dimensional vectors. The vector store abstraction we'll build later can hold embeddings from any source, so the architecture doesn't preclude this. But the full implementation is beyond the scope of this chapter.

5.3.4Metadata: the filtering foundation
Every document carries metadata: attributes that describe it beyond its text content. Some metadata is extracted automatically during parsing (filename, page count, word count, ingestion timestamp). Other metadata is supplied by the caller when ingesting (department, document type, author, version, tags).

Consider a search for 'how to reset a device.' Vector search alone can't distinguish between a customer-facing troubleshooting guide and an internal engineering runbook when both describe the same procedure. Metadata filtering makes that distinction possible. A workflow filters by audience: "customer" and never sees the internal document.

But metadata serves purposes beyond filtering. It enables source attribution in responses ("According to the Customer Service Policy, updated January 2025..."). It supports freshness-based ranking, where more recently ingested documents are weighted higher. It allows teams to audit what's in their index without reading every chunk. Listing 5.6 shows the metadata model.

Listing 5.7 Document metadata model
1
2
3
4
5
6
7
8
9
10
11
@dataclass
class DocumentMetadata:
    document_id: str
    index_name: str
    filename: str
    ingested_at: datetime
    page_count: Optional[int] = None
    word_count: Optional[int] = None
    custom_metadata: Dict[str, str] = field(
        default_factory=dict
    )
The custom_metadata field is intentionally a flat dictionary of string key-value pairs. This keeps it simple to store, index, and filter across different vector store backends.

TIP
Establish metadata conventions early. If one team tags documents with dept=engineering and another uses department=eng, filtering becomes unreliable. The optional metadata_schema in index configuration can enforce consistency by validating keys and values at ingestion time.

5.3.5Chunking: breaking text into retrievable pieces
With clean text extracted and metadata captured, the next stage is chunking: breaking the extracted text into pieces sized for meaningful retrieval. This is where the quality of your retrieval system is won or lost. A chunk that's too large dilutes the specific information a query needs with surrounding noise. A chunk that's too small loses context that makes the information meaningful. A chunk that splits a sentence in half produces results that are confusing at best and misleading at worst.

The platform should support multiple chunking strategies because different content types benefit from different approaches. This is why chunking parameters are part of the index configuration: the choice is made once when the index is created and applied consistently to every document ingested into it.

First, we need a data model for what a chunk is. A chunk is a piece of text extracted from a document, along with enough context to trace it back to its source. Listing 5.8 defines it.

Listing 5.8 Chunk dataclass
1
2
3
4
5
6
7
8
9
@dataclass
class Chunk:
    text: str
    heading: Optional[str] = None
    start_offset: int = 0
    end_offset: int = 0
    metadata: Dict[str, str] = field(
        default_factory=dict
    )
The most important field in the Chunk dataclass is text: this is what gets embedded into a vector and what gets returned to the caller during search. The heading field captures which section of the document this chunk came from, if the parser was able to extract that structure. Structure-aware chunking populates this; fixed-size chunking leaves it empty. The start_offset and end_offset track where in the original document this chunk's text appears, which is useful if a workflow wants to link back to the source or highlight the relevant passage. Finally, the metadata field carries per-chunk information like the section name, which can be used for more granular filtering during search.

To make different types of chunking strategies pluggable, the platform should define a common interface that all strategies implement. Listing 5.9 shows this interface.

Listing 5.9 Chunking strategy interface
1
2
3
4
5
6
7
8
9
10
class ChunkingStrategy(ABC):
    @abstractmethod
    def chunk(
        self,
        document: ExtractedDocument,
        chunk_size: int = 512,
        chunk_overlap: int = 50
    ) -> List[Chunk]:
        """Break a document into chunks for embedding and retrieval."""
        pass
The chunking strategy interface in listing 5.9 is deliberately simple. Every strategy receives an ExtractedDocument, the same structure our parsers produce in listing 5.4, along with the chunk_size and chunk_overlap configured on the index. It returns a list of Chunk objects. Because the input and output types are the same regardless of strategy, the ingestion pipeline can swap strategies based on the index configuration without any changes to the rest of the code.

Teams can register a chunking strategy through the SDK, following the same pattern as parser registration, as shown in Listing 5.10.

Listing 5.10 Registering a custom chunking strategy through the SDK
1
2
3
4
5
platform.data.register_chunking_strategy(
    name="faq",
    strategy=FAQChunkingStrategy(),
    version="1.0.0",
)
There are many ways to chunk a document, and the research community continues to develop new ones. We don't need to support every approach. Instead, we'll make the most used chunking strategies readily available on the platform and rely on the registration mechanism above for anything beyond those defaults. The following three strategies — fixed-size chunking, recursive splitting, and structure-aware chunking — cover the vast majority of production use cases.

Fixed-size chunking
The simplest built-in strategy is fixed-size chunking. It splits text into chunks of a fixed token count with configurable overlap between consecutive chunks. A token is the smallest unit of text that an embedding model processes. Depending on the model's tokenizer, a common word like "returning" might be a single token, while a less common word like "restocking" might be split into two tokens. Chunking in terms of tokens rather than characters ensures chunks align with the embedding model's input expectations. Listing 5.11 shows the implementation.

Listing 5.11 Fixed-size chunking implementation
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
def chunk_fixed_size(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50
) -> List[Chunk]:

    tokens = tokenize(text)
    chunks = []
    start = 0
 
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
 
        chunk_text = detokenize(chunk_tokens)
        chunks.append(Chunk(
            text=chunk_text,
            start_offset=start,
            end_offset=end
        ))
 
        start += chunk_size - chunk_overlap
 
    return chunks
The overlap parameter in listing 5.11 deserves an explanation. Without overlap, information that falls right at a chunk boundary gets split across two chunks. If a sentence starts at the end of chunk 1 and finishes at the beginning of chunk 2, neither chunk contains the complete thought. Overlap duplicates a window of tokens between consecutive chunks, so boundary information appears intact in at least one chunk. An overlap of 50 tokens (roughly 2-3 sentences) catches most boundary cases without excessive duplication. Figure 5.4 shows this in action.

Figure 5.4 Fixed-size chunking with and without overlap. A document is split into three chunks at rigid token boundaries, shown as stacked bars aligned to a token ruler. In the top panel (without overlap), hard cuts at exact token positions split a sentence about defective item returns across two chunks, leaving neither with the complete thought. In the bottom panel (with 50-token overlap), each consecutive pair of chunks shares a window of tokens, shown as the highlighted region where bars overlap. The boundary sentence now appears intact in Chunk 2, making it fully searchable. The overlap costs a small amount of duplicated storage but ensures that information at every boundary is preserved in at least one chunk.

Fixed-size chunking works reasonably well when topic boundaries happen to align with the chunk boundaries. But the strategy is oblivious to content. It doesn't know or care where paragraphs end, where topics shift, or whether it just cut a sentence in half. For many documents, this is good enough. For documents where precision matters, we need more sophisticated strategies.

Recursive splitting
Recursive splitting is a step up from fixed-size chunking and the most widely used chunking strategy in practice. LangChain's Recursive Character Text Splitter uses this approach as its default. Instead of splitting text at rigid token boundaries, it tries a hierarchy of natural separators: first paragraph breaks, then line breaks, then spaces, and finally individual characters. At each level, it checks whether the resulting pieces fit within the chunk size. If a piece is still too large, the algorithm recurses to the next separator in the hierarchy. The key insight is the fallback behavior. A document with clear paragraph breaks gets split at paragraph boundaries, producing clean, readable chunks. A dense paragraph that exceeds the chunk size falls back to splitting at sentence boundaries, then word boundaries. The chunk never lands in the middle of a word unless the document contains extremely long tokens. Figure 5.5 shows this in action.

Figure 5.5 Recursive splitting in action. A document is first split at paragraph boundaries (\n\n), producing four pieces. Three fit within the chunk size and become final chunks. The fourth exceeds the limit, so the algorithm recurses and splits it at line breaks (\n), producing two pieces that both fit. The diagram shows the hierarchy of separators tried at each level, with the final chunks highlighted.

Recursive splitting doesn't require parsed document structure, which makes it useful for content where the parser couldn't extract clean headings and sections: messy PDFs, plain text exports, legacy documents. It's the platform's default because it works for the widest range of content without any special preparation.

Structure-aware chunking
Structure-aware chunking takes a different approach. Many documents have explicit structural markers like headings, subheadings, and section breaks, and this strategy uses them to create chunks that respect the document's own organization. A section titled "Return Policy for Electronics" is a meaningful unit. Rather than splitting it in half, structure-aware chunking keeps it as one chunk if it fits within the token limit, or falls back to fixed-size chunking within the section if it doesn't. Each chunk prepends the section heading to its text before embedding, so a chunk from the "Restocking Fees" section includes those words even if the paragraph itself only discusses percentages and conditions. This means a query about restocking fees matches the right chunk even when the text within it never uses those exact words. The tradeoff is that this strategy requires the parser to have extracted heading structure successfully. It works best with well-organized documents like manuals, policies, and technical documentation.

Choosing the right strategy
Chunking strategy has a direct, measurable impact on retrieval quality. In evaluations across production RAG systems, the difference between good and bad chunking can swing answer accuracy by 10-20 percentage points. This is why chunking parameters are an index-level configuration rather than an afterthought. When teams create a new index, they should consider the nature of their content and choose accordingly. The platform defaults to recursive splitting because it works for the widest range of content, but teams with well-structured documents should consider structure-aware chunking.

Emerging approaches for chunking
The three strategies above are well-established and cover most production use cases. But newer and more sophisticated approaches are worth knowing about.

Semantic chunking uses embeddings themselves to detect topic boundaries. It embeds every sentence in a document, then walks through them comparing consecutive embeddings. When similarity drops sharply, a new chunk begins. This produces high-quality chunks for unstructured content like transcripts and email threads, but it requires embedding every sentence just to decide where to split, making it significantly more expensive at ingestion time.

Contextual retrieval, introduced by Anthropic in 2024, enriches each chunk after splitting by using an LLM to prepend a brief summary of the chunk's context within the full document. This helps chunks that would otherwise lack context ("The policy was revised in March") carry enough information to be useful in isolation ("This section of the Employee Benefits Handbook discusses parental leave. The policy was revised in March").

Late chunking flips the order of operations. In the standard pipeline, you split the document into chunks first and then embed each chunk independently, which means each chunk's embedding only reflects the text inside that chunk. Late chunking passes the entire document through a long-context embedding model first, producing token-level embeddings where every token's representation is informed by the full document. Only then does it split into chunks and average the token embeddings within each chunk to produce chunk-level vectors. The result is that a chunk containing "The policy was revised in March" carries an embedding that reflects the surrounding context about which policy and what the revision changed, even though that context lives in other chunks.

These techniques add computational cost at ingestion time but can meaningfully improve retrieval quality for documents where context matters. The ChunkingStrategy interface and registration mechanism we built make it straightforward to add any of these as custom strategies without changing the core pipeline.

5.3.6Generating embeddings
With chunks created, the final stage of the ingestion pipeline converts each chunk into a vector representation. We introduced embeddings conceptually in section 5.1: dense vectors where similar meanings produce similar numbers. Now we need to generate them.

The platform makes embedding model selection an index-level configuration because the model must remain consistent within an index. All chunks in an index must be embedded with the same model, so their vectors are comparable. But the platform doesn't dictate which model to use. Teams choose the model that fits their content, and the platform handles versioning, provider abstraction, and cost tracking.

Embedding models vary in dimensionality: the number of floating-point values in each vector. Higher dimensions can capture more nuanced semantic relationships but require more storage and make similarity computations slower. Some models offer configurable dimensions, letting teams tradeoff between retrieval quality and efficiency. This is another reason embedding model selection belongs in the index configuration: the choice affects storage costs and search latency across every document ingested into that index.

The model service connection
The Data Service doesn't call embedding providers directly. It goes through the Model Service we built in Chapter 3. This is an important architectural decision.

In Chapter 3, we built the Model Service around chat completions: the chat() and chat_stream() methods that send prompts to LLM providers and return generated text. Embedding generation is a different operation with a different shape. Chat completions take messages and return text. Embedding generation takes text and returns vectors. But the infrastructure concerns are identical: provider abstraction, cost tracking, retry logic, and routing through the API Gateway. Rather than building a separate service for embeddings, we extend the Model Service with an embed() method that follows the same patterns.

The provider abstraction from Chapter 3 applies directly. If a team starts with OpenAI's embedding model and later wants to switch to a self-hosted model, the change happens in the model configuration. The Data Service code doesn't change. Cost tracking works automatically: every embedding call flows through the Model Service's metrics, so organizations get visibility into their embedding costs alongside their inference costs. When a large ingestion job runs, the token usage is captured by the same metrics tracking that records chat completion costs. And retry logic applies: if the embedding provider has a brief outage mid-ingestion, the Model Service's retry configuration handles recovery without the Data Service implementing its own. Listing 5.12 shows how the Data Service generates embeddings through the Model Service.

Listing 5.12 Embedding generation through the Model Service
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
class EmbeddingGenerator:
    def __init__(self, model_client):
        self.model_client = model_client

    def embed_chunks(
        self,
        chunks: List[Chunk],
        model: str = "text-embedding-3-small",
        batch_size: int = 100
    ) -> List[List[float]]:
 
        all_embeddings = []
 
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [chunk.text for chunk in batch]
 
            response = self.model_client.embed(
                texts=texts,
                model=model
            )
            all_embeddings.extend(response.embeddings)
 
        return all_embeddings
 
    def embed_query(
        self, query: str, model: str
    ) -> List[float]:
        response = self.model_client.embed(
            texts=[query],
            model=model
        )
        return response.embeddings[0]
Batching is important for ingestion performance. Instead of making one API call per chunk, we group chunks into batches. Most embedding providers support batch requests, processing multiple texts in a single API call. A batch size of 100 is a reasonable default; the optimal size depends on the provider's rate limits and the average chunk length.

NOTE
The same embedding model must be used for chunks and queries. If you embed chunks with text-embedding-3-small but embed queries with text-embedding-3-large, the vectors exist in different mathematical spaces and similarity scores are meaningless. The Data Service enforces this by reading the embedding model from the index configuration for both ingestion and search.

5.3.7Document lifecycle
Ingestion isn't a one-time event. Policies get updated. Documentation is revised. Support articles are rewritten. The platform needs to handle document updates gracefully.

The simplest approach is replace-on-reingest: when a document with the same identifier is ingested again, the platform deletes all existing chunks and vectors for that document and processes the new version from scratch. This avoids the complexity of computing diffs between document versions and ensures the index always reflects the latest content. It's more work than a diff-based approach (re-embedding unchanged sections is wasteful), but the simplicity is worth it. Diff-based updates introduce subtle bugs when section boundaries shift, and the cost of re-embedding a single document is typically small. Listing 5.13 shows the ingestion method that ties the entire pipeline together.

Listing 5.13 Document ingestion
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
def ingest_document(
    self,
    index_name: str,
    filename: str,
    file_bytes: bytes,
    metadata: Dict[str, str] = None,
    document_id: str = None
) -> IngestedDocument:

    index = self.get_index(index_name)
    document_id = document_id or generate_document_id(filename)
 
    self.vector_store.delete_by_document(
        index_name, document_id
    )
 
    extracted = self.pipeline.extract(filename, file_bytes)
 
    chunks = self.chunker.chunk(
        extracted,
        strategy=index.config.chunking_strategy,
        chunk_size=index.config.chunk_size,
        chunk_overlap=index.config.chunk_overlap
    )
 
    embeddings = self.embedding_generator.embed_chunks(
        chunks,
        model=index.config.embedding_model
    )
 
    self.vector_store.insert(
        index_name, document_id, chunks, embeddings, metadata
    )
 
    return IngestedDocument(
        document_id=document_id,
        chunk_count=len(chunks),
        index_name=index_name
    )
This method is the entry point for everything we've built in this section. It orchestrates format detection, text extraction, chunking, embedding generation, and storage in a single call. The caller provides a file and optional metadata; the platform handles the rest.

The optional document_id parameter in listing 5.13 is important. If the caller provides a stable identifier for a document, re-ingesting the same document replaces the old version first. If they don't, the platform generates one from the filename, which works for initial ingestion.

Safe re-ingestion in production
The replace-on-reingest pattern deletes old chunks before inserting new ones. If the pipeline deletes the old chunks but then fails partway through, say the embedding API returns an error or storage runs out of space, the document is gone from the index with nothing to replace it. The ingestion operation should be atomic: either the entire sequence of delete, chunk, embed, and insert succeeds, or none of it takes effect. Wrapping these steps in a database transaction ensures that a failure at any stage rolls the index back to its previous state rather than leaving a gap.

Atomicity handles individual documents, but bulk re-ingestion introduces a different problem. If a team updates their parser and needs to re-ingest a thousand documents, each document swaps cleanly, but the process might take hours. During that window the index is in a mixed state: some documents reflect the new parser, others are still on the old version. If that inconsistency is unacceptable, ingest the full set into a new index, verify the results, and swap traffic over once everything is complete.

5.3.8Document management
With documents flowing into indexes through the ingestion pipeline, teams will quickly need to answer practical questions: which documents are in this index? Did that quarterly report actually get ingested, or did the job fail? A policy document was retracted last week and needs to be removed. How many chunks did that 200-page manual produce?

Without dedicated operations for this, the only way to answer these questions is to query the vector store directly, which breaks the abstraction the platform is supposed to provide. Listing 5.14 adds document management operations to the Data Service.

Listing 5.14 Document management operations
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
class DataService:
    # ... index operations from Listing 5.2 ...

    def list_documents(
        self, index_name: str
    ) -> List[DocumentMetadata]:
        """List all documents in an index."""
        pass
 
    def get_document(
        self, index_name: str, document_id: str
    ) -> DocumentMetadata:
        """Retrieve a document's metadata and chunk count."""
        pass
 
    def delete_document(
        self, index_name: str, document_id: str
    ) -> bool:
        """Delete a document and all its chunks and vectors."""
        pass
The service exposes three document management operations, as seen in listing 5.14. list_documents returns metadata for every document in an index: source URI, ingestion timestamp, chunk count, and any caller-supplied metadata, giving teams a complete view of what the index holds. get_document retrieves the same information for a single document by ID, which is the faster path when you already know which document you're checking. delete_document performs a cascading delete, removing the document record, all its associated chunks, and the corresponding vectors from the vector store in a single call. Keeping these three steps atomic matters: a partial delete that removes the document record but leaves orphaned vectors behind would corrupt search results silently.

These operations are useful for both application developers and the teams managing indexes. An application might display which documents are in a knowledge base or let users remove outdated content. The platform team needs this visibility to verify ingestion, debug issues, and keep indexes healthy.

5.3.9Asynchronous ingestion
The ingest_document method in listing 5.13 is synchronous: the caller waits while the pipeline parses, chunks, embeds, and stores. That works for small documents, but a 2000-page PDF can take minutes to parse, chunk, and embed. A team ingesting thousands of documents at once could be waiting hours for the entire batch to finish, blocking whatever workflow triggered the ingestion in the first place.

The platform should accept ingestion requests, return a job ID for each one immediately, and process the documents in the background. Teams can poll for status to track progress across the batch. Listing 5.15 shows the interface and the job tracking dataclass.

The caller submits a file and gets back a job ID immediately. The job tracks progress through four states: "queued" when the request is accepted, "processing" once the pipeline starts working on it, "completed" when all chunks and embeddings are stored successfully, and "failed" if any stage encounters an error. The progress field updates as stages complete, giving teams visibility into where a long-running ingestion stands. On success, the job's document_id links to the newly ingested document in the index. On failure, the error field captures what went wrong so the team can fix the issue and retry. Because each call returns instantly, submitting a thousand documents is fast: each call returns a job ID in milliseconds, and the platform processes them all in the background. Figure 5.6 illustrates this flow.

Figure 5.6 Asynchronous ingestion flow. A caller submits a document to the Data Service's ingest method and receives a job_id with status "queued" immediately. The platform processes the document in the background through the same stages as synchronous ingestion: format detection, text extraction, chunking, embedding, and storage. The job's status transitions from "queued" to "processing" as work begins, and its progress field updates as each stage completes. The job reaches "completed" with a document_id once all chunks and vectors are stored, or "failed" with an error message if any stage encounters a problem. The caller can poll get_ingest_status at any point to check the job's current state.

Listing 5.15 Asynchronous ingestion interface
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
@dataclass
class IngestJob:
    job_id: str
    status: str
    document_id: Optional[str] = None
    progress: float = 0.0
    error: Optional[str] = None

class DataService:
    # ... other operations ...

    def ingest(
        self,
        index_name: str,
        filename: str,
        file_bytes: bytes,
        metadata: Optional[Dict[str, str]] = None
    ) -> IngestJob:
        """Accept a document for ingestion and return immediately."""
        pass
 
    def get_ingest_status(
        self, job_id: str
    ) -> IngestJob:
        """Check the status of an ingestion job."""
        pass
With the ingestion pipeline complete, the platform handles the journey from raw file to embedded vectors. Teams bring their documents, and the platform takes care of parsing, chunking, and embedding. But those vectors need somewhere to live, and teams need a way to search them. Next, we will build that infrastructure: storing vectors efficiently and retrieving them at query time.

livebook features:
highlight, annotate, and bookmark
  
You can automatically highlight a piece of text simply by selecting it. Create a note by clicking anywhere on the page and start typing.
Disable quick notes and highlights?
5.4Vector storage and search
With chunks created and embeddings generated, we need somewhere to store them. The ingestion pipeline from listing 5.12 ends with a call to self.vector_store.insert(), but we haven't built that vector store yet. That's the job of this section.

The platform's role here is to provide a storage abstraction that supports different vector database backends behind a consistent interface. Teams can choose the backend that fits their scale and performance needs, and the rest of the Data Service works the same regardless. In Chapter 4, we built exactly this pattern for sessions: define an abstract base class, implement it for PostgreSQL, and leave the door open for alternative backends. We follow the same approach here, though the operations look nothing alike. Session storage deals with sequential messages looked up by ID. Vector storage deals with arrays of floating-point numbers searched by similarity. The underlying mechanics are new but the abstraction pattern is the same.

5.4.1Vector store interface
The Data Service needs its vector store to handle two jobs: storing vectors during ingestion and searching them at query time. We'll define the write and read sides of this interface separately, starting with storage.

Write operations
During ingestion, the pipeline needs to insert chunks with their embeddings. It also needs to delete chunks, both for individual documents when their content is updated and for entire indexes when they're removed. Listing 5.16 defines these write operations.

Listing 5.16 VectorStore abstract base class: write operations
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
class VectorStore(ABC):

    @abstractmethod
    def insert(
        self,
        index_name: str,
        document_id: str,
        chunks: List[Chunk],
        embeddings: List[List[float]],
        metadata: Dict[str, str]
    ) -> int:
        """Insert chunks with embeddings. Returns count inserted."""
        pass
 
    @abstractmethod
    def delete_by_document(
        self, index_name: str, document_id: str
    ) -> int:
        """Delete all chunks for a document. Returns count deleted."""
        pass
 
    @abstractmethod
    def delete_index
➥(self, index_name: str) -> int:
        """Delete all data for an index. Returns count deleted."""
        pass
The insert method takes chunks and their corresponding embeddings and stores them together. The backend is responsible for generating a unique ID for each chunk and persisting everything in a way that makes it searchable. The method also takes the index_name and document_id, which together scopes every chunk to a specific document within a specific index. This scoping is what makes the delete methods possible: delete_by_document can find and remove all chunks for a given document because they share the same document_id, and delete_index can wipe an entire index because all its chunks share the same index_name. Both delete methods return a count of how many chunks were removed, which is useful for logging and verification during re-ingestion.

TIP
Not every team member should be able to delete documents or indexes. Deletion is destructive, and an accidental delete_index call can wipe an entire knowledge base. The owner field on each index provides a foundation for restricting delete operations to authorized callers. A production implementation should check the caller's identity against the index owner before allowing any destructive action.

One design choice worth noting: the insert method returns an integer count of chunks inserted rather than the chunks themselves. This keeps the interface lightweight. The caller already has the chunks in memory; what it needs to know is whether the backend stored them all successfully.

Read operations
The other side of the interface is search. A workflow provides a query vector, and the vector store finds the chunks whose embeddings are most similar to it. Listing 5.17 defines the search method and the SearchResult it returns.

Listing 5.17 VectorStore abstract base class: search operation and result model
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
@dataclass
class SearchResult:
    chunk_id: str
    document_id: str
    text: str
    score: float
    metadata: Dict[str, str]

class VectorStore(ABC):
    # ... write operations from Listing 5.12 ...

    @abstractmethod
    def search(
        self,
        index_name: str,
        query_embedding: List[float],
        top_k: int = 5,
        metadata_filters: Optional[Dict[str, str]] = None,
        score_threshold: Optional[float] = None
    ) -> List[SearchResult]:
        """Find chunks most similar to the query embedding."""
        pass
The search method takes a query vector, compares it against stored vectors within the specified index, and returns the top-k most similar chunks ranked by score. The top_k parameter controls how many results come back. A customer support bot might request 3 highly relevant chunks, while a research tool might request 10 to cast a wider net.

The metadata_filters parameter lets callers narrow the search to only relevant chunks. If a workflow passes metadata_filters={"department": "legal"}, only chunks from legal department documents are considered in the results.

The score_threshold parameter sets a quality floor. Results with a similarity score below this value are discarded, even if they would otherwise rank in the top-k. This prevents low-quality chunks from reaching the model's context, where they would waste tokens and potentially confuse the response.

Each search result includes the chunk text, a similarity score between 0 and 1, the document ID it came from, and the metadata attached to it. This gives the calling workflow everything it needs: text to inject as context, a score to decide if the result is worth using, and source information for citations. The interface says nothing about how vectors are indexed internally or how similarity is computed. Those details differ across backends. The Data Service calls search() and gets back ranked results.

5.4.2Choosing a vector store backend
Vector storage is a newer landscape than traditional databases, and the options are still settling. They fall into two broad categories: extensions that add vector operations to existing databases, and purpose-built vector databases designed from the ground up for similarity search.

pgvector is the most widely used extension. It adds vector column types, similarity operators, and indexing to PostgreSQL. If you're already running PostgreSQL for sessions (as we built in Chapter 4), pgvector lets you store and search vectors without introducing new infrastructure. Vectors live in the same database, backed up and monitored the same way. For collections up to roughly 10 million vectors, pgvector performs well with proper indexing and memory configuration.

Purpose-built vector databases use storage engines and query planners optimized specifically for high-dimensional similarity search, and they generally scale further before performance degrades. Some require you to manage the infrastructure yourself, while others like Pinecone are fully managed and require no operational effort at all. The tradeoff varies: with self-hosted options you're taking on deployment and monitoring complexity, while with managed services you're potentially accepting vendor lock-in and usage-based pricing that can grow quickly at scale.

Table 5.1 summarizes four widely adopted options and what sets each one apart.

Table 5.1 Vector store backend comparison

pgvector
Pinecone
Weaviate
Elasticsearch
What it is
PostgreSQL extension
Fully managed cloud service
Open-source vector database
Distributed search engine with native vector support
Best for
Adding vector search with minimal infrastructure overhead
Fast time-to-production with fully managed infrastructure
Combining vector and keyword search in a single query
Adding semantic search alongside existing full-text search
Scale ceiling
~10M vectors before performance degrades
Billions of vectors
Hundreds of millions of vectors
Billions of vectors with proper cluster sizing
Self-hosting
Yes
Bring-your-own-cloud available on AWS, GCP and Azure
Yes
Yes
Key tradeoff
Requires PostgreSQL expertise for production workloads; no built-in hybrid search
Higher cost at scale; bring-your-own-cloud requires dedicated plan
More complex to operate than pgvector; typically requires Kubernetes for production at scale
Already a complex system to operate; adding vector workloads increases memory and compute requirements on top of existing search infrastructure
We'll implement the pgvector backend because it runs on infrastructure teams likely already have, and the patterns transfer directly to other backends. If a team later outgrows pgvector, they can implement a new VectorStore subclass, swap it in, and the Data Service works unchanged.

5.4.3The pgvector implementation
With the storage interface defined, we can build a concrete implementation. We'll translate VectorStore into SQL that uses pgvector's vector types and similarity operators. The specific queries are PostgreSQL-specific, but the structure of the implementation (how we map interface methods to database operations) applies to any backend.

The database schema
Before we write any Python, we need a table to hold chunks. A single table handles everything. Each row represents one chunk: its text, its embedding vector, the metadata from the original document, and pointers that tie it back to its source document and index. Listing 5.18 shows the table definition.

Listing 5.18 PostgreSQL schema for vector storage with pgvector
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chunks (
    chunk_id VARCHAR(255) PRIMARY KEY,
    document_id VARCHAR(255) NOT NULL,
    index_name VARCHAR(255) NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(1536),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chunks_document ON chunks(document_id);
CREATE INDEX idx_chunks_index ON chunks(index_name);
CREATE INDEX idx_chunks_metadata
➥ON chunks USING gin (metadata);

CREATE INDEX idx_chunks_embedding ON chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
The first line in listing 5.18 enables the pgvector extension. Without it, PostgreSQL doesn't know what a vector column is.

The embedding column is where the actual vectors live: 1,536 floating-point numbers for each chunk, matching the dimensions of the embedding model we configured in listing 5.1. Different models produce different dimensions: OpenAI's text-embedding-3-small outputs 1536, while Cohere's embed-english-v3.0 outputs 1024. This value must match the model your index uses. If you switch embedding models, you'll need to update the column definition and re-embed all your chunks The chunk_text column stores the original text alongside the vector so that a search can return readable content directly without a separate lookup. And the metadata column uses JSONB, so we can filter on key-value pairs like department or document_type without changing the schema.

The document_id and index_name columns serve the lifecycle operations from section 5.3. When a document is re-ingested, the pipeline deletes all rows matching that document ID before inserting new ones. When an index is removed, all rows with that index name go with it. The standard indexes on these columns, created by the CREATE INDEX statements in listing 5.18, let PostgreSQL find matching rows quickly without scanning the entire table. Without them, deletions would slow down noticeably as the table grows to millions of rows.

Without a specialized index on the embedding column, PostgreSQL would compare the query vector against every stored vector one by one. That's fine for development and small collections, but it slows down as the table grows past tens of thousands of chunks. pgvector offers two index types that speed this up by avoiding the brute-force comparison.

IVFFlat (Inverted File Flat), shown in listing 5.18, groups similar vectors into clusters during index creation. When a query comes in, PostgreSQL first figures out which clusters are closest to the query vector and then only searches within those clusters instead of the entire table. The tradeoff is that results are approximate: if the best match happens to land in a cluster the search didn't check, it gets missed. In practice, the accuracy loss is small, and the speed gain is dramatic. The lists parameter controls how many clusters the index creates. More clusters mean faster search but higher chance of missing a result. A value of 100 is a reasonable starting point for collections up to a few million vectors. The important caveat is that IVFFlat needs representative data to form good clusters, so create it after your first batch of documents has been ingested rather than on an empty table.

HNSW (Hierarchical Navigable Small World) takes a different approach. It builds a layered graph where each vector is connected to its nearby neighbors. Searching starts at the top layer with coarse, long-range connections and works down through increasingly fine-grained layers until it reaches the most similar vectors. HNSW can be built on an empty table and generally produces higher-quality results than IVFFlat, but it uses more memory and takes longer to build.

The Search Method
The search method is where pgvector does its real work. Rather than loading vectors into Python and comparing them in application code, we push the similarity computation into the database. PostgreSQL compares the query vector against stored vectors, applies metadata filters, ranks the results, and returns the top matches, all in a single query. Listing 5.19 shows the implementation.

Listing 5.19 pgvectorStore search implementation
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
class PgvectorStore(VectorStore):

    def __init__(self, connection_string: str):
        self.conn = psycopg2.connect(connection_string)
 
    def search(
        self,
        index_name: str,
        query_embedding: List[float],
        top_k: int = 5,
        metadata_filters: Optional[Dict[str, str]] = None,
        score_threshold: Optional[float] = None
    ) -> List[SearchResult]:
 
        query = """
            SELECT chunk_id, document_id, chunk_text, metadata,
                   1 - (embedding <=> %s::vector) AS score
            FROM chunks
            WHERE index_name = %s
        """
        params = [query_embedding, index_name]
 
        if metadata_filters:
            for key, value in metadata_filters.items():
                query += " AND metadata->>%s = %s"
                params.extend([key, value])
 
        if score_threshold:
            query += " AND 1 - (embedding <=> %s::vector) >= %s"
            params.extend
➥([query_embedding, score_threshold])

        query += " ORDER BY embedding <=> %s::vector LIMIT %s"
        params.extend([query_embedding, top_k])
 
        cursor = self.conn.cursor()
        cursor.execute(query, params)
 
        return [
            SearchResult(
                chunk_id=row[0], document_id=row[1],
                text=row[2], metadata=row[3], score=row[4]
            )
            for row in cursor.fetchall()
        ]
The <=> operator is pgvector's cosine distance operator: it measures how far apart two vectors are, where 0 means identical and larger values mean less similar. We subtract from 1 in the SELECT clause to flip this into a similarity score, because the rest of our code thinks in terms of "how similar is this?" (higher is better) rather than "how far apart are these?" (lower is better). When a workflow later checks whether a result's score exceeds a threshold, it's asking whether the chunk is similar enough to be worth including in the model's context.

The WHERE clause is how the index_name parameter from the method signature gets enforced at the SQL level: it ensures PostgreSQL only compares the query vector against chunks belonging to the specified index. Metadata filters add additional conditions to the same WHERE clause. If a workflow searches with metadata_filters={"department": "legal"}, only chunks from legal department documents are considered. The ORDER BY and LIMIT together give us the top-k most similar chunks from whatever remains after filtering.

The remaining methods that we must implement according to the interface in listing 5.16, insert and delete_by_document, are standard SQL that doesn't involve any vector operations, so we leave that as an exercise for you to implement. insert maps each chunk and its embedding into a row. delete_by_document removes all rows matching an index name and document ID, supporting the replace-on-reingest pattern from listing 5.13.

5.4.4Search orchestration
We've built the pieces: an embedding generator that converts text to vectors and a vector store that finds similar vectors. Now we need a method that ties them together so workflows can search an index with a plain text query. Listing 5.20 shows how the Data Service orchestrates this.

Listing 5.20 Data Service search orchestration
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
def search(
    self,
    index_name: str,
    query: str,
    top_k: int = 5,
    metadata_filters: Optional[Dict[str, str]] = None,
    score_threshold: float = 0.0
) -> List[SearchResult]:

    index = self.get_index(index_name)
 
    query_embedding = self.embedding_generator.embed_query(
        query=query,
        model=index.config.embedding_model
    )
 
    return self.vector_store.search(
        index_name=index_name,
        query_embedding=query_embedding,
        top_k=top_k,
        metadata_filters=metadata_filters,
        score_threshold=score_threshold
    )
The first thing the method does is look up the index configuration. This determines which embedding model to use for the query, because the query must be embedded with the same model that produced the index's chunk vectors. From there, the flow is straightforward: embed the query text, pass the resulting vector to the vector store's search method along with any filters and thresholds, and wrap the results. The method is short because the components do the hard work. The embedding generator handles provider communication through the Model Service. The vector store handles similarity computation and ranking. This method just wires them together. Figure 5.7 shows the complete search path.

Figure 5.7 The search path through the Data Service. A plain text query enters the Data Service's search method, which looks up the index configuration to determine the correct embedding model. The query is embedded through the Model Service (using the same model that produced the index's chunk embeddings). The resulting query vector is passed to the vector store, where it is compared against stored vectors, and returns the top-k most similar chunks ranked by cosine similarity. The Data Service wraps the raw results into a SearchResults object containing chunk texts, similarity scores, and source attribution, ready for the calling workflow to inject into the model's context.

The search pipeline we've built so far relies entirely on vector similarity: embed the query, find the closest vectors, return the results. This works well for semantic queries where the user describes what they're looking for in natural language. But it struggles with exact matches, keywords, and identifiers. The next section addresses this gap with hybrid search, combining vector similarity with traditional keyword matching.

livebook features:
discuss
  
Ask a question, share an example, or respond to another reader. Start a thread by selecting any piece of text and clicking the discussion icon.
5.5Hybrid search: combining vectors with keywords
Semantic search finds content by meaning. A query about "laptop return window" matches a chunk about "electronics refund period" because the embedding model understands these phrases describe the same concept. This is exactly the capability we built in section 5.4, and for most natural language queries, it works remarkably well.

But not all queries are natural language. A support agent searching for "ERR-4012" needs the chunk that contains that exact error code, not chunks that are semantically similar to the concept of errors. A compliance officer searching for "HIPAA 164.512(a)" needs the regulation section with that precise citation. In each case, the query is a precise identifier, and the user expects an exact match.

Semantic search struggles here because embedding models compress text into dense vectors that capture general meaning, not exact character sequences. The embedding for "ERR-4012" might land near embeddings for other error codes, other documents mentioning "error," or even chunks about "problems" and "issues." The specific code that matters is diluted into a cloud of related but wrong results.

Keyword search has the opposite strengths and weaknesses. Traditional text search (the kind that has powered search engines and databases for decades) excels at exact matches. It finds "ERR-4012" instantly because it looks for that literal string. It handles partial matches, boolean queries, and phrase matching. But it can't bridge vocabulary gaps. A keyword search for "laptop return" won't find a chunk that says "electronics refund" because the words don't overlap. Keyword search is precise but brittle. Semantic search is flexible but imprecise.

Hybrid search combines both. It runs a vector similarity search and a keyword search in parallel, then merges the results. The vector path catches the semantic matches that keywords would miss. The keyword path catches the exact matches that vectors would dilute. The merged result set is stronger than either path alone.

5.5.1Adding keyword search to the platform
Supporting hybrid search means the VectorStore interface needs a second retrieval method. The search method from listing 5.16 handles vector similarity. Now we need a keyword_search method that finds chunks by literal text matching. Listing 5.21 shows the addition.

Listing 5.21 Adding keyword search to the VectorStore interface
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
class VectorStore(ABC):
    # ... write operations from listing 5.12 ...
    # ... search from listing 5.13 ...

    def keyword_search(
        self,
        index_name: str,
        query: str,
        top_k: int = 5,
        metadata_filters: Optional[Dict[str, str]] = None
    ) -> List[SearchResult]:
        """Find chunks matching the query by keyword."""
        raise NotImplementedError(
            f"{type(self).__name__} 
➥does not support keyword search"
        )
The method keyword_search in listing 5.21 mirrors search with one key difference: it takes a raw query string instead of an embedding vector. Everything else stays the same. Same index scoping, same metadata filters, same return type. This consistency matters: the orchestration code works with a single result type regardless of which retrieval path produced it.

Unlike search, this is not an abstract method. The default implementation raises NotImplementedError, so backends only implement it when they actually support keyword search. A team using a minimal FAISS wrapper for pure vector search never has to think about keyword matching. A team using pgvector or Elasticsearch overrides the method to enable hybrid search.

The name VectorStore is admittedly narrow now that the interface includes keyword search, but it matches industry convention: Pinecone and Weaviate brand themselves as vector databases even though they all support keyword search today. Every production vector database we listed in table 5.1 supports some form of keyword search: Elasticsearch has BM25 natively, Pinecone encodes keyword signals as sparse vectors, and Weaviate exposes a hybrid search API.

5.5.2PostgreSQL keyword search implementation
The most widely used algorithm for keyword ranking is BM25 (Best Matching 25), a function that scores documents based on three factors: how often the query term appears in the document (term frequency), how rare the term is across all documents (inverse document frequency), and how long the document is relative to the average. A term that appears frequently in a short document but rarely elsewhere gets a high score. A common term like "the" that appears everywhere gets almost no weight. Elasticsearch and other dedicated search engines use BM25 as their default ranking algorithm.

PostgreSQL doesn't implement BM25 natively, but it does provide built-in full-text search. The key building block is the tsvector type, which converts text into a searchable token list, stripping stop words and applying stemming so that "returning" and "returned" both reduce to the same root form. Listing 5.22 shows how to add this to our existing chunks table.

NOTE
For teams that need true BM25 ranking in PostgreSQL, extensions like ParadeDB's pg_search and VectorChord-BM25 implement the full algorithm with dedicated index types. These are worth evaluating if keyword ranking quality is critical to your application. The built-in full-text search is a pragmatic starting point that avoids additional dependencies.

Listing 5.22 Adding full-text search to the chunks table
1
2
3
4
5
6
7
8
ALTER TABLE chunks
    ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', chunk_text)
    ) STORED;

CREATE INDEX idx_chunks_search
    ON chunks USING gin (search_vector);
The GENERATED ALWAYS AS clause in listing 5.22 means PostgreSQL maintains the search vector automatically. The ingestion pipeline we built earlier already writes chunk_text, and PostgreSQL derives the search vector from it. No code changes are needed.

At query time, PostgreSQL's @@ match operator checks whether a document's tsvector matches a tsquery, and the ts_rank function scores the match based on term frequency within the document. This ranking is simpler than BM25 (it doesn't account for how rare a term is across the whole corpus), but for hybrid search the distinction matters less than you might expect. We're combining keyword results with vector results through rank fusion, so what matters most is that the keyword path finds the right documents and puts them in a reasonable order.

5.5.3Merging results: Reciprocal Rank Fusion
Running a vector search and a keyword search in parallel is the easy part. The hard part is combining their results into a single ranked list. The vector search returns results scored by cosine similarity on a 0 to 1 scale. The keyword search typically returns results scored by a rank on an unbounded positive scale. These scores are not directly comparable and normalizing them into a common scale is unreliable because the distributions are different.

Reciprocal Rank Fusion, or RRF, sidesteps this problem entirely. Instead of comparing scores, it uses ranks. Each result gets a score based on its position in each list: 1/(k + rank), where k is a constant that prevents the top-ranked result from dominating. The original RRF paper found that k=60 works well empirically across a variety of retrieval tasks, and this value has become the standard default. A chunk that appears near the top of both lists gets a high combined score. A chunk that appears in only one list and ranks low gets a minimal score. The relative ordering is what matters, not the absolute numbers

RRF is elegant because it requires no tuning, no normalization, and no assumptions about score distributions. It works well in practice, which is why it has become the standard approach for combining heterogeneous search results.

Other ways to merge vector search and keyword search results
RRF is not the only way to combine two ranked lists. The most intuitive alternative is weighted scoring: scale both sets of scores into the same range (say 0 to 1), then compute a weighted average. This lets you dial the balance explicitly, giving 70% of the weight to vector results and 30% to keyword results, or vice versa. The problem is that the scaling step is fragile. Vector similarity scores and keyword scores have very different distributions, and a scaling formula that works well for one dataset can badly distort another. Teams at Assembled tried this approach before switching to RRF, finding that score distributions varied so widely across their customer base that no single set of weights worked reliably.

At the other end of the complexity spectrum, you can train a dedicated model to predict which results are most relevant, using signals like both search scores, how recently the document was updated, and user click history. This produces the best results when you have enough training data, but it requires building and maintaining a separate ML pipeline just for ranking.

RRF sits between these two extremes. It needs no tuning, no training data, and no assumptions about how scores are distributed. Research from both Elasticsearch and OpenSearch confirms that it performs within a few percentage points of carefully tuned weighted methods, which is why it has become the default in most hybrid search implementations.

5.5.4Putting it together
With keyword search and rank fusion in place, the Data Service can offer a hybrid search method that orchestrates both paths. An example flow, shown in figure 5.8, starts when a caller passes a text query to hybrid search. The method sends that query down two parallel paths. On the vector path, the query is embedded through the Model Service and then matched against stored vectors using cosine similarity. On the keyword path, the same raw query text is converted into a tsquery and matched against the full-text search column. Each path returns its own ranked list. Those two lists then feed into RRF, which produces a single merged ranking. The caller receives one list of results, ordered by combined relevance.

Figure 5.8 Hybrid search in the Data Service. A text query enters the search method and follows two parallel paths. The vector path embeds the query through the Model Service and runs a cosine similarity search against stored vectors. The keyword path converts the query into a tsquery and runs a full-text search with ts_rank scoring against the same chunks table. Both paths return ranked result lists, which Reciprocal Rank Fusion merges into a single ranked list by combining positional scores. The fused results are returned to the calling workflow.

One subtlety worth noting in the implementation: each path retrieves more candidates than the caller actually asked for. If the caller requests five results, each path fetches ten. This gives the fusion step a broader pool to work with. A chunk that ranks sixth in the vector results and seventh in the keyword results would be excluded if both paths only returned five, but it might rank third after fusion because it appeared in both lists. Oversampling by a factor of two is a common default that balances recall against the cost of scoring extra candidates. Listing 5.23 shows the complete method.

Listing 5.23 Hybrid search orchestration
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
def hybrid_search(
    self,
    index_name: str,
    query: str,
    top_k: int = 5,
    metadata_filters: Optional[Dict[str, str]] = None,
    score_threshold: float = 0.0
) -> List[SearchResult]:

    index = self.get_index(index_name)
 
    query_embedding = self.embedding_generator.embed_query(
        query=query,
        model=index.config.embedding_model
    )
 
    vector_results = self.vector_store.search(
        index_name=index_name,
        query_embedding=query_embedding,
        top_k=top_k * 2,
        metadata_filters=metadata_filters
    )
 
    keyword_results = self.vector_store.keyword_search(
        index_name=index_name,
        query=query,
        top_k=top_k * 2,
        metadata_filters=metadata_filters
    )
 
    fused = reciprocal_rank_fusion(
        vector_results, keyword_results
    )
 
    if score_threshold > 0:
        fused = [r for r in fused if r.score >= score_threshold]
 
    return fused[:top_k]
The keyword_search method on the vector store follows the same pattern as the vector search method. It queries the same chunks table, applies the same metadata filters, and returns the same SearchResult objects. The only difference is the matching logic. Callers of hybrid_search can switch to vector search without changing how they consume results, because both methods return List[SearchResult].

livebook features:
settings
  
Update your profile, view your dashboard, tweak the text size, or turn on dark mode.
5.6Service contract and complete retrieval flow
Like the Model Service in chapter 3 and the Session Service in chapter 4, the Data Service exposes its capabilities through a gRPC contract and SDK client. The contract groups operations into three categories: index management, document ingestion, and search. Listing 5.24 shows the service definition.

Listing 5.24 Data service gRPC contract
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
service DataService {
    // Index management
    rpc CreateIndex(CreateIndexRequest) returns (Index);
    rpc GetIndex(GetIndexRequest) returns (Index);
    rpc ListIndexes(ListIndexesRequest) returns (ListIndexesResponse);
    rpc DeleteIndex(DeleteIndexRequest) returns (DeleteIndexResponse);

    // Document ingestion
    rpc IngestDocument(IngestDocumentRequest) returns (IngestJob);
    rpc GetIngestJob(GetIngestJobRequest) returns (IngestJob);
    rpc DeleteDocument(DeleteDocumentRequest) returns 
➥(DeleteDocumentResponse);

    // Search
    rpc Search(SearchRequest) returns (SearchResponse);
    rpc HybridSearch(HybridSearchRequest) 
➥returns (SearchResponse);
}
The contract mirrors the Python interfaces we built throughout this chapter. Index management maps to the operations from section 5.2. Ingestion maps to the pipeline from section 5.3. Search and hybrid search map to the orchestration methods from sections 5.4 and 5.5. The SDK's DataClient translates these RPCs into Python methods. Listing 5.25 shows the implementation.

Listing 5.25 DataClient SDK wrapper
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
class DataClient:
    def __init__(self, channel: grpc.Channel):
        self._stub = DataServiceStub(channel)

    def create_index(self, config: IndexConfig) -> Index:
        return self._stub.CreateIndex(
            CreateIndexRequest(config=config)
        )
 
    def ingest(
        self,
        index_name: str,
        document_id: str,
        content: bytes,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> IngestJob:
        return self._stub.IngestDocument(
            IngestDocumentRequest(
                index_name=index_name,
                document_id=document_id,
                content=content,
                content_type=content_type,
                metadata=metadata or {}
            )
        )
 
    def search(
        self,
        index_name: str,
        query: str,
        top_k: int = 5,
        metadata_filters: Optional[Dict[str, str]] = None,
        score_threshold: float = 0.0
    ) -> List[SearchResult]:
        response = self._stub.Search(
            SearchRequest(
                index_name=index_name,
                query=query,
                top_k=top_k,
                metadata_filters=metadata_filters,
                score_threshold=score_threshold
            )
        )
        return [SearchResult(**r) 
➥for r in response.results]
The client is a thin wrapper. Each method translates a Python call into a gRPC request, sends it to the Data Service, and converts the response back into domain objects. The create_index and ingest methods are one-to-one mappings to their RPCs. The search method unpacks the repeated results field from the gRPC response into a list of SearchResult objects so that workflows work with plain Python dataclasses rather than protobuf messages. The hybrid_search method follows the same implementation, calling HybridSearch instead of Search on the stub. Both return List[SearchResult], so workflows can switch between them without changing how they handle results.

The DataClient gets imported as platform.data, so calling platform.data.search(...) or platform.data.ingest(...) follows the same convention workflows already use for platform.models and platform.sessions. With all three services now accessible through the SDK, we have the pieces needed for RAG.

The platform provides the infrastructure: session storage, vector search, model abstraction, and the SDK that makes them easy to compose. The workflow decides the application logic: which index to search, how many results to retrieve, what score threshold to apply, how to format the context, and what to include in the response.

livebook features:
highlight, annotate, and bookmark
  
You can automatically highlight a piece of text simply by selecting it. Create a note by clicking anywhere on the page and start typing.
Disable quick notes and highlights?
5.7Summary
The Data Service completes what Chapter 1 called "context-aware intelligence." The Session Service provides conversational memory. The Data Service provides organizational knowledge, grounding AI responses in factual information rather than plausible guesses.
Indexes are the organizational unit of the Data Service. Each index has its own embedding model, chunking strategy, and metadata schema, so different teams can configure knowledge retrieval independently without affecting each other.
The ingestion pipeline handles diverse file formats through format-specific parsers that extract clean text and structural information. Workflow authors call platform.data.ingest() without knowing whether the document is a PDF, Word file, or HTML page.
Document lifecycle management through the replace-on-reingest pattern keeps indexes current when source documents change. The pipeline deletes old chunks and reprocesses updated content without manual intervention.
Chunking quality directly impacts retrieval accuracy. A chunk that splits critical information in half means the system cannot find the complete answer, regardless of how good the embedding model or search algorithm is.
The Data Service generates embeddings through the Model Service rather than calling provider APIs directly. This reuses provider abstraction, cost tracking, fallback logic, and retry handling that already exist.
The vector store interface defines write operations for inserting and deleting chunks, and a search method that returns ranked results with scores, document IDs, and metadata. Teams can swap backends without changing application code.
The pgvector implementation stores vectors alongside chunk text and metadata in PostgreSQL, using IVFFlat, a clustering-based approximate nearest neighbor algorithm, for efficient similarity search at scale.
Hybrid search adds a keyword search method to the vector store interface as an optional method, so teams that only need vector search aren't forced to implement it.
Reciprocal Rank Fusion (RRF) merges results from vector and keyword search using rank positions rather than scores. This avoids fragile score normalization and produces competitive results without tuning or training data.
The Data Service exposes its capabilities through a gRPC contract and SDK client. Calling platform.data.search() or platform.data.hybrid_search() follows the same convention as the other platform services, and both return List[SearchResult] so workflows can switch between them freely.
The platform provides retrieval infrastructure while workflows control application logic: which index to search, how many results to retrieve, what score threshold to apply, and how to format context for the model.
 Prev Chapter
5 The Data Service: teaching AI what your organization knows
Next Chapter
cover

Up next...
6 Tools and Guardrails: Enabling safe, managed AI actions
Designing the Tool Service for managed tool discovery
Execution patterns for reliable external integrations
Integrating with MCP and other emerging standards
Isolating tool execution for safety and reliability
Reframing guardrails as platform-enforced execution policies that protect the application from unsafe or unintended outputs
Making safety decisions visible through metrics and audit trails
next chapter

What do you need help with? Select a topic or type your question below.
explain
translate
summarize this chapter
turn on dark mode
increase text size
turn on zen mode
ask anything...
