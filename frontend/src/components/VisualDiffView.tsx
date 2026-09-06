"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { getFileUrl, type DifferenceRegion, type PageVisualDiff } from "@/lib/api";

type ViewMode = "side-by-side" | "overlay" | "heatmap" | "blink" | "diff-only" | "grid";

const DIFF_TYPE_BADGE: Record<string, { label: string; style: string }> = {
  text: { label: "Text", style: "bg-blue-50 text-blue-700 border-blue-200" },
  layout: { label: "Layout", style: "bg-amber-50 text-amber-700 border-amber-200" },
  image: { label: "Image", style: "bg-purple-50 text-purple-700 border-purple-200" },
  table: { label: "Table", style: "bg-emerald-50 text-emerald-700 border-emerald-200" },
};

const SEVERITY_BADGE: Record<string, { label: string; style: string }> = {
  high: { label: "High", style: "bg-rose-100 text-rose-800" },
  medium: { label: "Medium", style: "bg-amber-100 text-amber-800" },
  low: { label: "Low", style: "bg-slate-100 text-slate-700" },
};

function similarityColor(similarity: number): string {
  if (similarity >= 0.98) return "text-emerald-600";
  if (similarity >= 0.90) return "text-amber-600";
  return "text-rose-600";
}

function confidenceLabel(similarity: number): { label: string; style: string } {
  const pct = similarity * 100;
  if (pct >= 99.0) return { label: "Virtually identical (99–100%)", style: "text-emerald-700 bg-emerald-50 border-emerald-200" };
  if (pct >= 95.0) return { label: "Very minor differences (95–99%)", style: "text-blue-700 bg-blue-50 border-blue-200" };
  if (pct >= 90.0) return { label: "Noticeable differences (90–95%)", style: "text-amber-700 bg-amber-50 border-amber-200" };
  return { label: "Significant differences (<90%)", style: "text-rose-700 bg-rose-50 border-rose-200" };
}

export function VisualDiffView({ pages }: { pages: PageVisualDiff[] }) {
  const [currentPageIndex, setCurrentPageIndex] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>("side-by-side");
  const [zoom, setZoom] = useState(1.0);
  const [overlayOpacity, setOverlayOpacity] = useState(50);
  const [overlayTop, setOverlayTop] = useState<"modified" | "original">("modified");
  const [blinkActive, setBlinkActive] = useState(false);
  const [blinkShowModified, setBlinkShowModified] = useState(false);
  const [activeRegionId, setActiveRegionId] = useState<string | null>(null);
  const [showDebug, setShowDebug] = useState(false);
  const [devicePixelRatio, setDevicePixelRatio] = useState(() => {
    if (typeof window !== "undefined") {
      return window.devicePixelRatio || 1;
    }
    return 1;
  });

  useEffect(() => {
    const updateDpr = () => {
      setDevicePixelRatio(window.devicePixelRatio || 1);
    };
    window.addEventListener("resize", updateDpr);
    return () => window.removeEventListener("resize", updateDpr);
  }, []);

  const currentPage = pages[currentPageIndex] ?? pages[0];

  // Blink interval timer
  useEffect(() => {
    if (viewMode !== "blink" || !blinkActive) return;
    const timer = setInterval(() => {
      setBlinkShowModified((prev) => !prev);
    }, 600);
    return () => clearInterval(timer);
  }, [viewMode, blinkActive]);

  // Synchronized scrolling between original and modified panes
  const leftScrollRef = useRef<HTMLDivElement | null>(null);
  const rightScrollRef = useRef<HTMLDivElement | null>(null);
  const isSyncingScroll = useRef(false);

  const handleScroll = (source: "left" | "right") => {
    if (isSyncingScroll.current) return;
    const sourceEl = source === "left" ? leftScrollRef.current : rightScrollRef.current;
    const targetEl = source === "left" ? rightScrollRef.current : leftScrollRef.current;
    if (!sourceEl || !targetEl) return;

    isSyncingScroll.current = true;
    targetEl.scrollTop = sourceEl.scrollTop;
    targetEl.scrollLeft = sourceEl.scrollLeft;
    requestAnimationFrame(() => {
      isSyncingScroll.current = false;
    });
  };

  // Base canvas dimensions in pixels (native DPI)
  const canvasW = currentPage?.debug_info?.canvas_dims?.[0] ?? 1224;
  const canvasH = currentPage?.debug_info?.canvas_dims?.[1] ?? 1584;

  // Rendered display width and height according to zoom
  const displayW = Math.round((canvasW / 2) * zoom);
  const displayH = Math.round((canvasH / 2) * zoom);

  const totalDifferencesAcrossAllPages = useMemo(() => {
    return pages.reduce((sum, p) => sum + (p.regions?.length ?? 0), 0);
  }, [pages]);

  const pageDifferences = currentPage?.regions ?? [];

  // Jump to difference and scroll into view
  const handleJumpToRegion = (region: DifferenceRegion) => {
    if (region.page !== currentPage.page) {
      const targetIndex = pages.findIndex((p) => p.page === region.page);
      if (targetIndex !== -1) {
        setCurrentPageIndex(targetIndex);
      }
    }
    setActiveRegionId(region.id);

    // Scroll to region bounding box
    setTimeout(() => {
      const scrollY = (region.y / canvasH) * displayH - 100;
      const scrollX = (region.x / canvasW) * displayW - 100;

      if (leftScrollRef.current) {
        leftScrollRef.current.scrollTo({ top: Math.max(0, scrollY), left: Math.max(0, scrollX), behavior: "smooth" });
      }
      if (rightScrollRef.current) {
        rightScrollRef.current.scrollTo({ top: Math.max(0, scrollY), left: Math.max(0, scrollX), behavior: "smooth" });
      }
    }, 80);
  };

  if (!currentPage) {
    return <p className="text-sm text-muted">No visual diff data available.</p>;
  }

  const origImgUrl = currentPage.original_image_key ? getFileUrl(currentPage.original_image_key) : null;
  const modImgUrl = currentPage.modified_image_key ? getFileUrl(currentPage.modified_image_key) : null;
  const diffImgUrl = getFileUrl(currentPage.diff_image_key);
  const diffOnlyImgUrl = currentPage.diff_only_image_key ? getFileUrl(currentPage.diff_only_image_key) : null;

  const confInfo = confidenceLabel(currentPage.similarity);

  return (
    <div className="flex flex-col gap-6">
      {/* Header bar: Title & Confidence Rating */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-paper-line pb-4">
        <div>
          <div className="text-xs uppercase tracking-[0.15em] text-muted">Pixel-Accurate Visual Comparison</div>
          <h2 className="font-serif text-xl text-ink">
            Page {currentPage.page} of {pages.length}
            {currentPage.status === "only_in_original" && (
              <span className="ml-2 inline-block rounded bg-rose-100 px-2 py-0.5 text-xs font-sans text-rose-700">
                Only in Original document
              </span>
            )}
            {currentPage.status === "only_in_modified" && (
              <span className="ml-2 inline-block rounded bg-rose-100 px-2 py-0.5 text-xs font-sans text-rose-700">
                Only in Modified document
              </span>
            )}
          </h2>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className={`rounded border px-3 py-1 text-xs font-medium ${confInfo.style}`}>
            {confInfo.label}
          </div>
          <div className="text-sm font-semibold">
            <span className={similarityColor(currentPage.similarity)}>
              {Math.round(currentPage.similarity * 1000) / 10}% match
            </span>
          </div>
          <button
            onClick={() => setShowDebug((prev) => !prev)}
            className="rounded border border-paper-line bg-white px-2.5 py-1 text-xs font-medium text-muted hover:text-ink"
            title="Toggle Developer & Debug Inspector"
          >
            {showDebug ? "Hide Debug" : "Debug Info"}
          </button>
        </div>
      </div>

      {/* Developer / Debug Inspector Panel */}
      {showDebug && currentPage.debug_info && (
        <div className="rounded-sm border border-paper-line bg-slate-50 p-4 font-mono text-xs text-slate-800">
          <div className="mb-2 font-bold uppercase tracking-wider text-slate-600">
            Developer / Calibration Inspection Data
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-4">
            <div>
              <span className="text-slate-500">Original Dims:</span> {currentPage.debug_info.original_dims[0]} × {currentPage.debug_info.original_dims[1]} px
            </div>
            <div>
              <span className="text-slate-500">Modified Dims:</span> {currentPage.debug_info.modified_dims[0]} × {currentPage.debug_info.modified_dims[1]} px
            </div>
            <div>
              <span className="text-slate-500">Render DPI:</span> {currentPage.debug_info.dpi}
            </div>
            <div>
              <span className="text-slate-500">Paper Format:</span> {currentPage.debug_info.page_size_name}
            </div>
            <div>
              <span className="text-slate-500">Canvas Dims:</span> {canvasW} × {canvasH} px
            </div>
            <div>
              <span className="text-slate-500">Display Scale:</span> {currentPage.debug_info.scale_factor}x ({zoom * 100}%)
            </div>
            <div>
              <span className="text-slate-500">Device Pixel Ratio:</span> {devicePixelRatio}
            </div>
            <div>
              <span className="text-slate-500">Alignment Offset:</span> (0, 0)
            </div>
            <div>
              <span className="text-slate-500">Diff Threshold:</span> {currentPage.debug_info.diff_threshold} ΔRGB
            </div>
            <div>
              <span className="text-slate-500">Changed Pixels:</span> {currentPage.debug_info.changed_pixels.toLocaleString()}
            </div>
            <div>
              <span className="text-slate-500">Changed Pct:</span> {currentPage.debug_info.changed_percentage}%
            </div>
            <div>
              <span className="text-slate-500">Confidence Score:</span> {currentPage.confidence_score ?? Math.round(currentPage.similarity * 100)}%
            </div>
          </div>
        </div>
      )}

      {/* Main Toolbar: Modes, Zoom, and Navigation */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-sm border border-paper-line bg-white p-3">
        {/* Comparison Mode Switcher */}
        <div className="flex flex-wrap items-center gap-1">
          <span className="mr-1 text-xs font-medium uppercase tracking-wider text-muted">Mode:</span>
          {(
            [
              ["side-by-side", "Side-by-Side"],
              ["overlay", "Overlay"],
              ["heatmap", "Difference Heatmap"],
              ["blink", "Blink / Compare"],
              ["diff-only", "Difference Only"],
              ["grid", "All Pages"],
            ] as [ViewMode, string][]
          ).map(([mode, label]) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              className={[
                "rounded px-3 py-1 text-xs font-medium transition-colors",
                viewMode === mode ? "bg-ink text-paper" : "text-muted hover:bg-slate-100 hover:text-ink",
              ].join(" ")}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Page & Zoom Controls */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Zoom controls */}
          <div className="flex items-center gap-1 rounded border border-paper-line bg-slate-50 px-2 py-0.5 text-xs">
            <button
              onClick={() => setZoom((z) => Math.max(0.4, Number((z - 0.2).toFixed(1))))}
              className="px-1 text-slate-700 hover:text-ink disabled:opacity-30"
              disabled={zoom <= 0.4}
              title="Zoom out"
            >
              −
            </button>
            <span className="w-12 text-center font-mono font-medium text-ink">{Math.round(zoom * 100)}%</span>
            <button
              onClick={() => setZoom((z) => Math.min(2.5, Number((z + 0.2).toFixed(1))))}
              className="px-1 text-slate-700 hover:text-ink disabled:opacity-30"
              disabled={zoom >= 2.5}
              title="Zoom in"
            >
              +
            </button>
            <button
              onClick={() => setZoom(1.0)}
              className="ml-1 border-l border-paper-line pl-1 text-[11px] text-muted hover:text-ink"
            >
              Reset
            </button>
          </div>

          {/* Page navigation */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => setCurrentPageIndex((p) => Math.max(0, p - 1))}
              disabled={currentPageIndex === 0}
              className="rounded border border-paper-line px-2.5 py-1 text-xs font-medium text-ink disabled:opacity-30"
            >
              ← Prev
            </button>
            <span className="px-1 text-xs font-medium text-ink">
              {currentPageIndex + 1} / {pages.length}
            </span>
            <button
              onClick={() => setCurrentPageIndex((p) => Math.min(pages.length - 1, p + 1))}
              disabled={currentPageIndex === pages.length - 1}
              className="rounded border border-paper-line px-2.5 py-1 text-xs font-medium text-ink disabled:opacity-30"
            >
              Next →
            </button>
          </div>
        </div>
      </div>

      {/* Mode Specific Controls (Overlay & Blink) */}
      {viewMode === "overlay" && (
        <div className="flex flex-wrap items-center gap-4 rounded-sm border border-paper-line bg-white p-3 text-xs">
          <div className="flex items-center gap-2">
            <span className="font-medium text-ink">Top Layer:</span>
            <button
              onClick={() => setOverlayTop((t) => (t === "modified" ? "original" : "modified"))}
              className="rounded border border-paper-line bg-slate-50 px-2.5 py-1 font-medium text-ink hover:bg-slate-100"
            >
              {overlayTop === "modified" ? "Modified Document (PDF) [Top]" : "Original Document (DOCX) [Top]"} (Click to Swap)
            </button>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-medium text-ink">Opacity:</span>
            <input
              type="range"
              min={0}
              max={100}
              value={overlayOpacity}
              onChange={(e) => setOverlayOpacity(Number(e.target.value))}
              className="w-36 accent-ink"
            />
            <span className="w-8 font-mono text-ink">{overlayOpacity}%</span>
          </div>
          <span className="text-muted">
            Drag slider to blend between Original and Modified in place.
          </span>
        </div>
      )}

      {viewMode === "blink" && (
        <div className="flex flex-wrap items-center gap-4 rounded-sm border border-paper-line bg-white p-3 text-xs">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setBlinkActive((b) => !b)}
              className={[
                "rounded px-3 py-1 font-medium transition-colors",
                blinkActive ? "bg-rose-600 text-white" : "bg-ink text-paper",
              ].join(" ")}
            >
              {blinkActive ? "Stop Alternating" : "Auto-Blink (600ms)"}
            </button>
            <button
              onMouseDown={() => setBlinkShowModified(true)}
              onMouseUp={() => setBlinkShowModified(false)}
              onTouchStart={() => setBlinkShowModified(true)}
              onTouchEnd={() => setBlinkShowModified(false)}
              className="rounded border border-paper-line bg-slate-50 px-3 py-1 font-medium text-ink active:bg-slate-200"
            >
              Hold to Reveal Modified
            </button>
          </div>
          <div className="font-medium text-ink">
            Currently displaying:{" "}
            <span className="font-bold text-rose-600">
              {blinkShowModified ? "Modified (PDF)" : "Original (DOCX)"}
            </span>
          </div>
          <span className="text-muted">
            Alternating frames reveal text movement, margin shifts, and line height differences instantly.
          </span>
        </div>
      )}

      {/* Main View Area: Viewer + Difference Navigation Sidebar */}
      {viewMode === "grid" ? (
        /* All Pages Grid Overview */
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {pages.map((p, idx) => (
            <div
              key={p.page}
              onClick={() => {
                setCurrentPageIndex(idx);
                setViewMode("side-by-side");
              }}
              className="cursor-pointer rounded-sm border border-paper-line bg-white p-4 transition-shadow hover:shadow-md"
            >
              <div className="mb-2 flex items-center justify-between text-sm">
                <span className="font-serif text-ink">Page {p.page}</span>
                <span className={similarityColor(p.similarity)}>
                  {Math.round(p.similarity * 100)}% match
                </span>
              </div>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={getFileUrl(p.diff_image_key)}
                alt={`Visual difference highlight for page ${p.page}`}
                className="w-full rounded-sm border border-paper-line"
              />
              <div className="mt-2 text-xs text-muted">
                {p.regions?.length ?? 0} difference regions · Click to inspect
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Single Page Detail with Difference Navigation Sidebar */
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Document Viewer Container (8 or 9 cols) */}
          <div className="lg:col-span-8 xl:col-span-9">
            {viewMode === "side-by-side" && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {/* Left Column: Original */}
                <div className="rounded-sm border border-paper-line bg-white p-3">
                  <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-wider text-muted">
                    <span>Original (DOCX)</span>
                    <span>100% Scale</span>
                  </div>
                  <div
                    ref={leftScrollRef}
                    onScroll={() => handleScroll("left")}
                    className="overflow-auto border border-slate-200 bg-slate-100 p-2"
                    style={{ maxHeight: "720px" }}
                  >
                    <div
                      className="relative mx-auto bg-white shadow-sm"
                      style={{ width: `${displayW}px`, height: `${displayH}px` }}
                    >
                      {origImgUrl ? (
                        /* eslint-disable-next-line @next/next/no-img-element */
                        <img
                          src={origImgUrl}
                          alt="Original rendered document page"
                          className="max-h-none max-w-none select-none"
                          style={{ width: `${displayW}px`, height: `${displayH}px` }}
                        />
                      ) : (
                        <div className="flex h-full items-center justify-center text-xs text-muted">
                          Original page not present
                        </div>
                      )}

                      {/* Interactive Difference Bounding Boxes */}
                      {pageDifferences.map((r) => {
                        const isActive = activeRegionId === r.id;
                        return (
                          <div
                            key={r.id}
                            onClick={() => setActiveRegionId(r.id)}
                            className={[
                              "absolute cursor-pointer border transition-all",
                              isActive
                                ? "z-20 border-2 border-rose-600 bg-rose-500/20 ring-2 ring-rose-400"
                                : "z-10 border border-rose-500/60 bg-rose-500/10 hover:border-rose-600 hover:bg-rose-500/20",
                            ].join(" ")}
                            style={{
                              left: `${(r.x / canvasW) * 100}%`,
                              top: `${(r.y / canvasH) * 100}%`,
                              width: `${(r.width / canvasW) * 100}%`,
                              height: `${(r.height / canvasH) * 100}%`,
                            }}
                            title={`${r.diff_type} difference (${r.severity} severity)`}
                          />
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Right Column: Modified */}
                <div className="rounded-sm border border-paper-line bg-white p-3">
                  <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-wider text-muted">
                    <span>Modified (PDF)</span>
                    <span>100% Scale</span>
                  </div>
                  <div
                    ref={rightScrollRef}
                    onScroll={() => handleScroll("right")}
                    className="overflow-auto border border-slate-200 bg-slate-100 p-2"
                    style={{ maxHeight: "720px" }}
                  >
                    <div
                      className="relative mx-auto bg-white shadow-sm"
                      style={{ width: `${displayW}px`, height: `${displayH}px` }}
                    >
                      {modImgUrl ? (
                        /* eslint-disable-next-line @next/next/no-img-element */
                        <img
                          src={modImgUrl}
                          alt="Modified rendered document page"
                          className="max-h-none max-w-none select-none"
                          style={{ width: `${displayW}px`, height: `${displayH}px` }}
                        />
                      ) : (
                        <div className="flex h-full items-center justify-center text-xs text-muted">
                          Modified page not present
                        </div>
                      )}

                      {/* Interactive Difference Bounding Boxes */}
                      {pageDifferences.map((r) => {
                        const isActive = activeRegionId === r.id;
                        return (
                          <div
                            key={r.id}
                            onClick={() => setActiveRegionId(r.id)}
                            className={[
                              "absolute cursor-pointer border transition-all",
                              isActive
                                ? "z-20 border-2 border-rose-600 bg-rose-500/20 ring-2 ring-rose-400"
                                : "z-10 border border-rose-500/60 bg-rose-500/10 hover:border-rose-600 hover:bg-rose-500/20",
                            ].join(" ")}
                            style={{
                              left: `${(r.x / canvasW) * 100}%`,
                              top: `${(r.y / canvasH) * 100}%`,
                              width: `${(r.width / canvasW) * 100}%`,
                              height: `${(r.height / canvasH) * 100}%`,
                            }}
                            title={`${r.diff_type} difference (${r.severity} severity)`}
                          />
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {viewMode === "overlay" && (
              <div className="rounded-sm border border-paper-line bg-white p-4">
                <div className="overflow-auto border border-slate-200 bg-slate-100 p-2" style={{ maxHeight: "760px" }}>
                  <div
                    className="relative mx-auto bg-white shadow-sm"
                    style={{ width: `${displayW * 1.5}px`, height: `${displayH * 1.5}px` }}
                  >
                    {/* Bottom Layer */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={overlayTop === "modified" ? (origImgUrl ?? diffImgUrl) : (modImgUrl ?? diffImgUrl)}
                      alt="Bottom layer"
                      className="absolute inset-0 max-h-none max-w-none select-none"
                      style={{ width: `${displayW * 1.5}px`, height: `${displayH * 1.5}px` }}
                    />
                    {/* Top Layer with Opacity */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={overlayTop === "modified" ? (modImgUrl ?? diffImgUrl) : (origImgUrl ?? diffImgUrl)}
                      alt="Top layer"
                      className="absolute inset-0 max-h-none max-w-none select-none"
                      style={{
                        width: `${displayW * 1.5}px`,
                        height: `${displayH * 1.5}px`,
                        opacity: overlayOpacity / 100,
                      }}
                    />
                  </div>
                </div>
              </div>
            )}

            {viewMode === "heatmap" && (
              <div className="rounded-sm border border-paper-line bg-white p-4">
                <div className="overflow-auto border border-slate-200 bg-slate-100 p-2" style={{ maxHeight: "760px" }}>
                  <div
                    className="relative mx-auto bg-white shadow-sm"
                    style={{ width: `${displayW * 1.5}px`, height: `${displayH * 1.5}px` }}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={diffImgUrl}
                      alt="Difference Heatmap"
                      className="max-h-none max-w-none select-none"
                      style={{ width: `${displayW * 1.5}px`, height: `${displayH * 1.5}px` }}
                    />

                    {/* Bounding box highlights on heatmap */}
                    {pageDifferences.map((r) => (
                      <div
                        key={r.id}
                        onClick={() => setActiveRegionId(r.id)}
                        className={[
                          "absolute cursor-pointer transition-all",
                          activeRegionId === r.id
                            ? "border-2 border-cyan-400 bg-cyan-400/20 ring-2 ring-cyan-300"
                            : "border border-cyan-400/60 hover:border-cyan-400 hover:bg-cyan-400/10",
                        ].join(" ")}
                        style={{
                          left: `${(r.x / canvasW) * 100}%`,
                          top: `${(r.y / canvasH) * 100}%`,
                          width: `${(r.width / canvasW) * 100}%`,
                          height: `${(r.height / canvasH) * 100}%`,
                        }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}

            {viewMode === "blink" && (
              <div className="rounded-sm border border-paper-line bg-white p-4">
                <div className="overflow-auto border border-slate-200 bg-slate-100 p-2" style={{ maxHeight: "760px" }}>
                  <div
                    className="relative mx-auto bg-white shadow-sm"
                    style={{ width: `${displayW * 1.5}px`, height: `${displayH * 1.5}px` }}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={blinkShowModified ? (modImgUrl ?? diffImgUrl) : (origImgUrl ?? diffImgUrl)}
                      alt="Blink view comparison frame"
                      className="max-h-none max-w-none select-none"
                      style={{ width: `${displayW * 1.5}px`, height: `${displayH * 1.5}px` }}
                    />
                  </div>
                </div>
              </div>
            )}

            {viewMode === "diff-only" && (
              <div className="rounded-sm border border-paper-line bg-white p-4">
                <div
                  className="overflow-auto border border-slate-200 bg-[radial-gradient(#e2e8f0_1px,transparent_1px)] [background-size:16px_16px] p-2"
                  style={{ maxHeight: "760px" }}
                >
                  <div
                    className="relative mx-auto bg-white shadow-sm"
                    style={{ width: `${displayW * 1.5}px`, height: `${displayH * 1.5}px` }}
                  >
                    {diffOnlyImgUrl ? (
                      /* eslint-disable-next-line @next/next/no-img-element */
                      <img
                        src={diffOnlyImgUrl}
                        alt="Difference-only extracted pixels"
                        className="max-h-none max-w-none select-none"
                        style={{ width: `${displayW * 1.5}px`, height: `${displayH * 1.5}px` }}
                      />
                    ) : (
                      /* eslint-disable-next-line @next/next/no-img-element */
                      <img
                        src={diffImgUrl}
                        alt="Difference view"
                        className="max-h-none max-w-none select-none"
                        style={{ width: `${displayW * 1.5}px`, height: `${displayH * 1.5}px` }}
                      />
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Difference Navigation Sidebar (4 or 3 cols) */}
          <div className="flex flex-col gap-4 lg:col-span-4 xl:col-span-3">
            <div className="rounded-sm border border-paper-line bg-white p-4">
              <div className="flex items-center justify-between border-b border-paper-line pb-3">
                <h3 className="font-serif text-base font-medium text-ink">Differences</h3>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-ink">
                  {pageDifferences.length} on page
                </span>
              </div>

              <div className="mt-3 text-xs text-muted">
                {totalDifferencesAcrossAllPages} total difference regions detected across {pages.length} page
                {pages.length > 1 ? "s" : ""}. Click any card to navigate & highlight:
              </div>

              {/* List of Difference Regions */}
              <div className="mt-4 flex max-h-[640px] flex-col gap-2.5 overflow-y-auto pr-1">
                {pageDifferences.length === 0 ? (
                  <div className="rounded border border-dashed border-slate-200 p-6 text-center text-xs text-muted">
                    No visual differences detected on this page.
                  </div>
                ) : (
                  pageDifferences.map((r, i) => {
                    const isSelected = activeRegionId === r.id;
                    const typeBadge = DIFF_TYPE_BADGE[r.diff_type] ?? DIFF_TYPE_BADGE.layout;
                    const sevBadge = SEVERITY_BADGE[r.severity] ?? SEVERITY_BADGE.low;

                    return (
                      <div
                        key={r.id}
                        onClick={() => handleJumpToRegion(r)}
                        className={[
                          "cursor-pointer rounded border p-3 text-xs transition-all",
                          isSelected
                            ? "border-ink bg-slate-50 shadow-sm ring-1 ring-ink"
                            : "border-paper-line bg-white hover:border-slate-400 hover:bg-slate-50/50",
                        ].join(" ")}
                      >
                        <div className="mb-1.5 flex items-center justify-between">
                          <span className="font-semibold text-ink">
                            #{i + 1} {typeBadge.label} Change
                          </span>
                          <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${sevBadge.style}`}>
                            {sevBadge.label}
                          </span>
                        </div>

                        <div className="flex items-center gap-1.5 text-[11px] text-muted">
                          <span className={`rounded border px-1 py-0.2 ${typeBadge.style}`}>
                            {typeBadge.label}
                          </span>
                          <span>·</span>
                          <span>{r.pixel_count.toLocaleString()} changed px</span>
                          <span>·</span>
                          <span>{r.percentage}% of page</span>
                        </div>

                        <div className="mt-2 text-[10px] font-mono text-slate-400">
                          bbox: [{r.x}, {r.y}] {r.width}×{r.height}px
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

