"""
Page-level visual comparison for PDF, DOCX, and image documents.

Key capabilities:
1. Exact document sizing and scaling: Normalizes documents to a common canonical
   page dimension at a fixed DPI (144 DPI) without non-uniform stretching or
   aspect ratio distortion.
2. Unified rendering pipeline: High-quality rendering via headless LibreOffice
   with an in-process pure-Python fallback (python-docx + PyMuPDF) for DOCX,
   ensuring deterministic output in both production and test environments.
3. Pixel-accurate alignment: Both documents share a single coordinate system
   origin (0, 0) on a canonical canvas, properly accounting for Letter, A4,
   and landscape orientations.
4. Robust image-difference & anti-aliasing separation: Distinguishes true content
   differences (added/removed/shifted text, font sizes, line heights, margins,
   tables, images) from font rasterization, subpixel positioning, and
   anti-aliasing noise.
5. Difference region detection: Uses connected-component analysis and bounding-box
   clustering to detect and classify changed regions (text, layout, image, table)
   with severity ratings for the interactive difference sidebar.
6. Multi-mode visual asset generation: Generates original page, modified page,
   difference heatmap, and difference-only transparent overlays for
   Side-by-Side, Overlay, Heatmap, Blink, and Diff-Only viewing modes.
7. Page-by-page comparison: Reports exact page-level statistics, confidence scores,
   developer debug info, and clearly flags page-count mismatches.
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from typing import Callable

import docx
import fitz
import numpy as np
from PIL import Image
from scipy.ndimage import binary_opening, maximum_filter, minimum_filter
from skimage.measure import label, regionprops
from skimage.metrics import structural_similarity

logger = logging.getLogger(__name__)

RENDER_DPI = 144  # 2x standard 72 pt/in for sharp rendering and accurate diffing
MAX_VISUAL_DIFF_PAGES = 20  # cap rendering cost for very long documents
DIFF_THRESHOLD = 25  # per-pixel color delta threshold
MIN_CLUSTER_AREA = 4  # minimum connected-component area to qualify as a real difference


def make_diff_storage_key(suffix: str = "") -> str:
    """Returns a storage key matching app/main.py's servable regex
    r"^diffs/[0-9a-fA-F\\-_]+\\.png$"."""
    base_uuid = str(uuid.uuid4())
    if suffix:
        return f"diffs/{base_uuid}_{suffix}.png"
    return f"diffs/{base_uuid}.png"


def detect_page_size_name(width_pt: float, height_pt: float) -> str:
    """Identifies standard paper sizes (Letter, A4, Legal, etc.) and orientation."""
    w, h = min(width_pt, height_pt), max(width_pt, height_pt)
    orientation = "Landscape" if width_pt > height_pt else "Portrait"

    # Match standard dimensions within 6pt tolerance
    if abs(w - 612) <= 6 and abs(h - 792) <= 6:
        size_name = "Letter"
    elif abs(w - 595.3) <= 6 and abs(h - 841.9) <= 6:
        size_name = "A4"
    elif abs(w - 612) <= 6 and abs(h - 1008) <= 6:
        size_name = "Legal"
    elif abs(w - 792) <= 6 and abs(h - 1224) <= 6:
        size_name = "Tabloid"
    elif abs(w - 841.9) <= 6 and abs(h - 1190.6) <= 6:
        size_name = "A3"
    elif abs(w - 522) <= 6 and abs(h - 756) <= 6:
        size_name = "Executive"
    else:
        size_name = f"{round(width_pt)}x{round(height_pt)} pt"

    return f"{size_name} ({orientation})"


def _docx_to_pdf_libreoffice(docx_bytes: bytes) -> bytes | None:
    """Converts DOCX to PDF using headless LibreOffice if installed."""
    libreoffice_bin = shutil.which("libreoffice") or shutil.which("soffice")
    if not libreoffice_bin:
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "input.docx")
        with open(input_path, "wb") as f:
            f.write(docx_bytes)

        try:
            cmd = [
                libreoffice_bin,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                tmpdir,
                input_path,
            ]
            result = subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            output_path = os.path.join(tmpdir, "input.pdf")
            if os.path.exists(output_path):
                with open(output_path, "rb") as f:
                    return f.read()
            logger.warning("LibreOffice command succeeded but output PDF missing: %s", result.stdout)
        except Exception as e:
            logger.warning("Headless LibreOffice conversion failed: %s; falling back to internal renderer", e)
    return None


def _docx_to_pdf_fallback(docx_bytes: bytes) -> bytes:
    """In-process pure-Python fallback renderer that converts DOCX into a clean,
    dimensionally accurate PDF using python-docx and PyMuPDF."""
    doc = docx.Document(io.BytesIO(docx_bytes))
    pdf = fitz.open()

    section = doc.sections[0] if doc.sections else None
    page_w = section.page_width.pt if section and section.page_width else 612.0
    page_h = section.page_height.pt if section and section.page_height else 792.0
    margin_l = section.left_margin.pt if section and section.left_margin else 72.0
    margin_t = section.top_margin.pt if section and section.top_margin else 72.0
    margin_r = section.right_margin.pt if section and section.right_margin else 72.0
    margin_b = section.bottom_margin.pt if section and section.bottom_margin else 72.0

    usable_w = max(page_w - margin_l - margin_r, 100.0)
    current_page = pdf.new_page(width=page_w, height=page_h)
    cursor_y = margin_t

    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            cursor_y += 12.0
            continue

        fontsize = 11.0
        is_bold = False
        is_italic = False
        color_rgb = (0, 0, 0)

        for run in p.runs:
            if run.font.size:
                fontsize = float(run.font.size.pt)
            if run.bold:
                is_bold = True
            if run.italic:
                is_italic = True
            if run.font.color and run.font.color.rgb:
                hex_col = str(run.font.color.rgb)
                if len(hex_col) == 6:
                    color_rgb = (
                        int(hex_col[0:2], 16) / 255.0,
                        int(hex_col[2:4], 16) / 255.0,
                        int(hex_col[4:6], 16) / 255.0,
                    )
            break

        line_height = fontsize * 1.35
        # Word wrap estimate
        chars_per_line = max(int(usable_w / (fontsize * 0.52)), 10)
        lines = [text[i : i + chars_per_line] for i in range(0, len(text), chars_per_line)]

        for line in lines:
            if cursor_y + line_height > page_h - margin_b:
                current_page = pdf.new_page(width=page_w, height=page_h)
                cursor_y = margin_t

            font_name = "helv"
            if is_bold and is_italic:
                font_name = "hebi"
            elif is_bold:
                font_name = "hebo"
            elif is_italic:
                font_name = "heit"

            current_page.insert_text(
                (margin_l, cursor_y + fontsize),
                line,
                fontsize=fontsize,
                fontname=font_name,
                color=color_rgb,
            )
            cursor_y += line_height

        cursor_y += 4.0

    # Handle tables if any
    for table in doc.tables:
        cursor_y += 8.0
        num_cols = len(table.columns) if table.columns else 1
        col_w = usable_w / max(num_cols, 1)

        for row in table.rows:
            row_h = 20.0
            if cursor_y + row_h > page_h - margin_b:
                current_page = pdf.new_page(width=page_w, height=page_h)
                cursor_y = margin_t

            for col_idx, cell in enumerate(row.cells):
                cell_rect = fitz.Rect(
                    margin_l + col_idx * col_w,
                    cursor_y,
                    margin_l + (col_idx + 1) * col_w,
                    cursor_y + row_h,
                )
                current_page.draw_rect(cell_rect, color=(0.7, 0.7, 0.7), width=0.5)
                cell_text = cell.text.strip()
                if cell_text:
                    current_page.insert_text(
                        (cell_rect.x0 + 4, cell_rect.y0 + 13),
                        cell_text[: int(col_w / 6)],
                        fontsize=9.0,
                        color=(0.1, 0.1, 0.1),
                    )
            cursor_y += row_h

    pdf_bytes = pdf.tobytes()
    pdf.close()
    return pdf_bytes


def docx_to_pdf(docx_bytes: bytes) -> bytes:
    """Converts DOCX bytes to PDF bytes, using LibreOffice if available,
    or our robust built-in fallback renderer."""
    lo_pdf = _docx_to_pdf_libreoffice(docx_bytes)
    if lo_pdf is not None:
        return lo_pdf
    return _docx_to_pdf_fallback(docx_bytes)


def _document_to_pdf(raw_bytes: bytes, fmt: str) -> fitz.Document:
    """Normalizes any supported visual document (PDF, DOCX) into a PyMuPDF Document."""
    if fmt == "pdf":
        return fitz.open(stream=raw_bytes, filetype="pdf")
    if fmt == "docx":
        pdf_bytes = docx_to_pdf(raw_bytes)
        return fitz.open(stream=pdf_bytes, filetype="pdf")
    if fmt == "image":
        # Wrap image in a clean single-page PDF
        img = Image.open(io.BytesIO(raw_bytes))
        doc = fitz.open()
        w_pt = (img.width / RENDER_DPI) * 72.0
        h_pt = (img.height / RENDER_DPI) * 72.0
        page = doc.new_page(width=w_pt, height=h_pt)
        page.insert_image(fitz.Rect(0, 0, w_pt, h_pt), stream=raw_bytes)
        return doc
    raise ValueError(f"Unsupported format for visual comparison: {fmt}")


def merge_boxes(
    boxes: list[list[int]], max_gap_x: int = 24, max_gap_y: int = 8
) -> list[list[int]]:
    """Merges adjacent and proximate bounding boxes (e.g. letters on the same line)
    into unified line/phrase difference regions."""
    if not boxes:
        return []

    sorted_boxes = sorted(boxes, key=lambda b: (b[0], b[1]))
    clusters: list[list[int]] = []

    for b in sorted_boxes:
        min_y, min_x, max_y, max_x, count = b
        merged = False
        for c in clusters:
            c_min_y, c_min_x, c_max_y, c_max_x, c_count = c
            y_overlap = not (max_y + max_gap_y < c_min_y or min_y > c_max_y + max_gap_y)
            x_overlap = not (max_x + max_gap_x < c_min_x or min_x > c_max_x + max_gap_x)
            if y_overlap and x_overlap:
                c[0] = min(c_min_y, min_y)
                c[1] = min(c_min_x, min_x)
                c[2] = max(c_max_y, max_y)
                c[3] = max(c_max_x, max_x)
                c[4] += count
                merged = True
                break
        if not merged:
            clusters.append([min_y, min_x, max_y, max_x, count])

    return clusters


def _classify_region(
    w: int, h: int, count: int, page_w_px: int, page_h_px: int
) -> tuple[str, str]:
    """Classifies a difference region into type and severity."""
    area = w * h
    density = count / max(area, 1)

    # Difference type classification
    if (w > 100 and h <= 8) or (h > 100 and w <= 8):
        diff_type = "table"
    elif h <= 48 and w >= 6:
        diff_type = "text"
    elif h > 48 and w > 60 and density > 0.25:
        diff_type = "image"
    else:
        diff_type = "layout"

    # Severity classification
    if count > 400 or (area > (page_w_px * page_h_px * 0.05)):
        severity = "high"
    elif count >= 70:
        severity = "medium"
    else:
        severity = "low"

    return diff_type, severity


def compare_pages(
    page_orig: fitz.Page,
    page_mod: fitz.Page,
    page_num: int,
    store_image: Callable[[bytes], str],
    store_all_assets: bool = False,
) -> dict:
    """Compares two PDF pages with exact canonical sizing, anti-aliasing
    separation, and region extraction."""
    w_orig_pt, h_orig_pt = page_orig.rect.width, page_orig.rect.height
    w_mod_pt, h_mod_pt = page_mod.rect.width, page_mod.rect.height

    # Canonical common canvas dimensions in points
    target_w_pt = max(w_orig_pt, w_mod_pt)
    target_h_pt = max(h_orig_pt, h_mod_pt)

    scale = RENDER_DPI / 72.0
    target_w_px = int(round(target_w_pt * scale))
    target_h_px = int(round(target_h_pt * scale))

    matrix = fitz.Matrix(scale, scale)
    pix_orig = page_orig.get_pixmap(matrix=matrix, alpha=False)
    pix_mod = page_mod.get_pixmap(matrix=matrix, alpha=False)

    # Place both pages onto an identical white canvas aligned at (0, 0)
    orig_canvas = Image.new("RGB", (target_w_px, target_h_px), (255, 255, 255))
    orig_page_img = Image.frombytes("RGB", (pix_orig.width, pix_orig.height), pix_orig.samples)
    orig_canvas.paste(orig_page_img, (0, 0))

    mod_canvas = Image.new("RGB", (target_w_px, target_h_px), (255, 255, 255))
    mod_page_img = Image.frombytes("RGB", (pix_mod.width, pix_mod.height), pix_mod.samples)
    mod_canvas.paste(mod_page_img, (0, 0))

    arr_orig = np.asarray(orig_canvas, dtype=np.int16)
    arr_mod = np.asarray(mod_canvas, dtype=np.int16)

    # Color difference
    delta = np.max(np.abs(arr_orig - arr_mod), axis=2)
    candidate_mask = delta > DIFF_THRESHOLD

    # Anti-aliasing & subpixel separation
    gray_orig = np.asarray(orig_canvas.convert("L"), dtype=np.float32)
    gray_mod = np.asarray(mod_canvas.convert("L"), dtype=np.float32)

    min_orig = minimum_filter(gray_orig, size=3)
    max_orig = maximum_filter(gray_orig, size=3)
    min_mod = minimum_filter(gray_mod, size=3)
    max_mod = maximum_filter(gray_mod, size=3)

    edge_orig = (max_orig - min_orig) > 35
    edge_mod = (max_mod - min_mod) > 35

    is_subpixel_aa = (
        edge_orig
        & edge_mod
        & (gray_orig >= min_mod - 12)
        & (gray_orig <= max_mod + 12)
        & (gray_mod >= min_orig - 12)
        & (gray_mod <= max_orig + 12)
    )

    real_diff_mask = candidate_mask & (~is_subpixel_aa)
    real_diff_mask = binary_opening(real_diff_mask, structure=np.ones((2, 2)))

    # Connected component labeling and region grouping
    labeled_mask = label(real_diff_mask)
    raw_boxes: list[list[int]] = []
    for r in regionprops(labeled_mask):
        if r.area >= MIN_CLUSTER_AREA:
            min_y, min_x, max_y, max_x = r.bbox
            raw_boxes.append([min_y, min_x, max_y, max_x, int(r.area)])

    merged_boxes = merge_boxes(raw_boxes, max_gap_x=24, max_gap_y=8)

    regions: list[dict] = []
    for idx, (min_y, min_x, max_y, max_x, count) in enumerate(merged_boxes):
        w = max_x - min_x
        h = max_y - min_y
        diff_type, severity = _classify_region(w, h, count, target_w_px, target_h_px)
        regions.append(
            {
                "id": f"p{page_num}-r{idx+1}",
                "page": page_num,
                "x": int(min_x),
                "y": int(min_y),
                "width": int(w),
                "height": int(h),
                "diff_type": diff_type,
                "severity": severity,
                "pixel_count": int(count),
                "percentage": round((count / (target_w_px * target_h_px)) * 100, 3),
            }
        )

    # Generate difference heatmap overlay
    dimmed = (gray_orig * 0.45 + 140).astype(np.uint8)
    heatmap = np.stack([dimmed, dimmed, dimmed], axis=-1)
    heatmap[real_diff_mask] = [225, 35, 55]  # vivid high-contrast red
    diff_img = Image.fromarray(heatmap, mode="RGB")

    # Generate difference-only transparent PNG overlay
    diff_only = np.zeros((target_h_px, target_w_px, 4), dtype=np.uint8)
    diff_only[real_diff_mask] = [225, 35, 55, 240]
    diff_only_img = Image.fromarray(diff_only, mode="RGBA")

    # Save visual assets
    def _save(img: Image.Image, fmt: str = "PNG") -> bytes:
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        return buf.getvalue()

    diff_key = store_image(_save(diff_img))
    if store_all_assets:
        orig_key = store_image(_save(orig_canvas))
        mod_key = store_image(_save(mod_canvas))
        diff_only_key = store_image(_save(diff_only_img))
    else:
        orig_key = None
        mod_key = None
        diff_only_key = None

    # Metric calculations
    ssim_val = float(structural_similarity(gray_orig, gray_mod, data_range=255.0))
    changed_pixels = int(np.count_nonzero(real_diff_mask))
    total_pixels = target_w_px * target_h_px
    pixel_similarity = 1.0 - (changed_pixels / total_pixels)

    similarity = round(max(0.0, min(1.0, 0.5 * ssim_val + 0.5 * pixel_similarity)), 4)
    confidence_score = round(similarity * 100.0, 1)

    page_size_name = detect_page_size_name(target_w_pt, target_h_pt)

    debug_info = {
        "original_dims": [int(pix_orig.width), int(pix_orig.height)],
        "modified_dims": [int(pix_mod.width), int(pix_mod.height)],
        "dpi": RENDER_DPI,
        "page_size_name": page_size_name,
        "scale_factor": round(scale, 2),
        "canvas_dims": [int(target_w_px), int(target_h_px)],
        "alignment_offset": [0, 0],
        "diff_threshold": DIFF_THRESHOLD,
        "changed_pixels": changed_pixels,
        "total_pixels": total_pixels,
        "changed_percentage": round((changed_pixels / total_pixels) * 100, 4),
    }

    return {
        "page": page_num,
        "similarity": similarity,
        "confidence_score": confidence_score,
        "status": "compared",
        "diff_image_key": diff_key,
        "original_image_key": orig_key,
        "modified_image_key": mod_key,
        "diff_only_image_key": diff_only_key,
        "regions": regions,
        "debug_info": debug_info,
    }


def compare_documents_visual(
    original_bytes: bytes,
    original_format: str,
    modified_bytes: bytes,
    modified_format: str,
    store_image: Callable[[bytes], str],
    store_all_assets: bool = False,
    include_extra_pages: bool = False,
) -> list[dict]:
    """Compares two documents (PDF, DOCX) page by page visually.
    Handles page count mismatches by reporting unpaired pages when include_extra_pages is True."""
    orig_doc = _document_to_pdf(original_bytes, original_format)
    mod_doc = _document_to_pdf(modified_bytes, modified_format)

    try:
        total_orig = len(orig_doc)
        total_mod = len(mod_doc)
        common_pages = min(total_orig, total_mod, MAX_VISUAL_DIFF_PAGES)

        results: list[dict] = []

        # 1. Compare common pages
        for i in range(common_pages):
            page_diff = compare_pages(orig_doc[i], mod_doc[i], i + 1, store_image, store_all_assets=store_all_assets)
            results.append(page_diff)

        scale = RENDER_DPI / 72.0
        matrix = fitz.Matrix(scale, scale)

        def _save_img(pix: fitz.Pixmap) -> str:
            buf = io.BytesIO()
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img.save(buf, format="PNG")
            return store_image(buf.getvalue())

        # 2. Pages only in original (if any, when include_extra_pages is requested)
        if include_extra_pages and total_orig > common_pages and len(results) < MAX_VISUAL_DIFF_PAGES:
            for i in range(common_pages, min(total_orig, MAX_VISUAL_DIFF_PAGES)):
                p = orig_doc[i]
                pix = p.get_pixmap(matrix=matrix, alpha=False)
                key = _save_img(pix)
                results.append(
                    {
                        "page": i + 1,
                        "similarity": 0.0,
                        "confidence_score": 0.0,
                        "status": "only_in_original",
                        "diff_image_key": key,
                        "original_image_key": key,
                        "modified_image_key": None,
                        "diff_only_image_key": None,
                        "regions": [],
                        "debug_info": {
                            "original_dims": [pix.width, pix.height],
                            "modified_dims": [0, 0],
                            "dpi": RENDER_DPI,
                            "page_size_name": detect_page_size_name(p.rect.width, p.rect.height),
                            "scale_factor": round(scale, 2),
                            "canvas_dims": [pix.width, pix.height],
                            "alignment_offset": [0, 0],
                            "diff_threshold": DIFF_THRESHOLD,
                            "changed_pixels": pix.width * pix.height,
                            "total_pixels": pix.width * pix.height,
                            "changed_percentage": 100.0,
                        },
                    }
                )

        # 3. Pages only in modified (if any, when include_extra_pages is requested)
        if include_extra_pages and total_mod > common_pages and len(results) < MAX_VISUAL_DIFF_PAGES:
            for i in range(common_pages, min(total_mod, MAX_VISUAL_DIFF_PAGES)):
                p = mod_doc[i]
                pix = p.get_pixmap(matrix=matrix, alpha=False)
                key = _save_img(pix)
                results.append(
                    {
                        "page": i + 1,
                        "similarity": 0.0,
                        "confidence_score": 0.0,
                        "status": "only_in_modified",
                        "diff_image_key": key,
                        "original_image_key": None,
                        "modified_image_key": key,
                        "diff_only_image_key": None,
                        "regions": [],
                        "debug_info": {
                            "original_dims": [0, 0],
                            "modified_dims": [pix.width, pix.height],
                            "dpi": RENDER_DPI,
                            "page_size_name": detect_page_size_name(p.rect.width, p.rect.height),
                            "scale_factor": round(scale, 2),
                            "canvas_dims": [pix.width, pix.height],
                            "alignment_offset": [0, 0],
                            "diff_threshold": DIFF_THRESHOLD,
                            "changed_pixels": pix.width * pix.height,
                            "total_pixels": pix.width * pix.height,
                            "changed_percentage": 100.0,
                        },
                    }
                )

        return results
    finally:
        orig_doc.close()
        mod_doc.close()


def compare_pdf_pages(
    original_bytes: bytes,
    modified_bytes: bytes,
    store_image: Callable[[bytes], str],
    store_all_assets: bool = False,
    include_extra_pages: bool = False,
) -> list[dict]:
    """Preserved backward-compatible entrypoint for PDF-vs-PDF visual comparison."""
    return compare_documents_visual(
        original_bytes,
        "pdf",
        modified_bytes,
        "pdf",
        store_image,
        store_all_assets=store_all_assets,
        include_extra_pages=include_extra_pages,
    )

