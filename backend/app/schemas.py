from pydantic import BaseModel


class DiffSegmentResponse(BaseModel):
    type: str
    original: str = ""
    modified: str = ""


class CellChangeResponse(BaseModel):
    row: int
    col: int
    original: str
    modified: str


class TableRowDiffResponse(BaseModel):
    type: str
    original: list[str] | None = None
    modified: list[str] | None = None
    cell_changes: list[CellChangeResponse] = []


class TableDiffResponse(BaseModel):
    name: str
    stats: dict[str, int]
    rows: list[TableRowDiffResponse]


class SpreadsheetDiffResponse(BaseModel):
    """Phase 5: present on a JobStatusResponse only when both documents
    had spreadsheet-like tables to compare — see table_diff.py."""

    tables: list[TableDiffResponse]
    added_tables: list[str]
    removed_tables: list[str]


class DifferenceRegionResponse(BaseModel):
    id: str
    page: int
    x: int
    y: int
    width: int
    height: int
    diff_type: str  # "text", "layout", "image", "table"
    severity: str  # "high", "medium", "low"
    pixel_count: int
    percentage: float


class PageVisualDebugInfo(BaseModel):
    original_dims: list[int]
    modified_dims: list[int]
    dpi: int
    page_size_name: str
    scale_factor: float
    canvas_dims: list[int]
    alignment_offset: list[int]
    diff_threshold: int
    changed_pixels: int
    total_pixels: int
    changed_percentage: float


class PageVisualDiffResponse(BaseModel):
    """Page visual comparison result for PDF and DOCX documents. Supports
    multi-mode preview (side-by-side, overlay, heatmap, blink, diff-only),
    detected difference regions with bounding boxes, and developer debug info."""

    page: int
    similarity: float
    confidence_score: float = 1.0
    status: str = "compared"  # "compared" | "only_in_original" | "only_in_modified"
    diff_image_key: str
    original_image_key: str | None = None
    modified_image_key: str | None = None
    diff_only_image_key: str | None = None
    regions: list[DifferenceRegionResponse] = []
    debug_info: PageVisualDebugInfo | None = None


class ParagraphMatchResponse(BaseModel):
    type: str
    original: str | None = None
    modified: str | None = None
    similarity: float | None = None
    confidence: str | None = None


class SemanticDiffResponse(BaseModel):
    """Phase 7: paragraph-level semantic comparison — see semantic_diff.py.
    `provider` reports which similarity method actually produced these
    scores ("tfidf" by default, "sentence-transformers" only if that
    optional dependency is installed and configured), since the two have
    meaningfully different accuracy characteristics and the response
    shouldn't hide which one ran."""

    provider: str
    matches: list[ParagraphMatchResponse]
    stats: dict[str, int]


class FormattingChangeResponse(BaseModel):
    type: str
    original_text: str | None = None
    modified_text: str | None = None
    changed_properties: dict = {}


class FormattingDiffResponse(BaseModel):
    """Font/size/bold/italic/underline/color comparison — DOCX and PDF
    only, see formatting_diff.py."""

    changes: list[FormattingChangeResponse]
    stats: dict[str, int]


class HealthResponse(BaseModel):
    status: str
    version: str


class JobCreateResponse(BaseModel):
    """Returned immediately by POST /jobs — before any comparison work
    has actually happened. Status is always "queued" at this point."""

    id: str
    status: str


class PasteCompareRequest(BaseModel):
    """Request body for POST /jobs/text — accepts raw text strings instead
    of multipart file uploads."""

    original_text: str
    modified_text: str


class JobStatusResponse(BaseModel):
    """Returned by GET /jobs/{id}. The comparison-result fields are only
    populated once status == "done"; `error` is only populated once
    status == "failed". Modeling this as one response with optional
    fields (rather than a union type) keeps polling on the frontend
    simple — one shape to check `.status` on, every time."""

    id: str
    status: str
    similarity: float | None = None
    stats: dict[str, int] | None = None
    segments: list[DiffSegmentResponse] | None = None
    warnings: list[str] | None = None
    table_diff: SpreadsheetDiffResponse | None = None
    visual_diff: list[PageVisualDiffResponse] | None = None
    semantic_diff: SemanticDiffResponse | None = None
    formatting_diff: FormattingDiffResponse | None = None
    error: str | None = None
