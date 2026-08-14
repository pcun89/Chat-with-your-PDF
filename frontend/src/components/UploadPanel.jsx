import { useRef, useState } from "react";

export default function UploadPanel({ doc, uploading, error, onUpload, onReset }) {
    const inputRef = useRef(null);
    const [dragActive, setDragActive] = useState(false);

    function handleFiles(files) {
        const file = files?.[0];
        if (!file) return;
        if (!file.name.toLowerCase().endsWith(".pdf")) {
            onUpload(null, "Please choose a .pdf file.");
            return;
        }
        onUpload(file);
    }

    return (
        <div className="card">
            <div className="card__header">01 — Source document</div>

            {!doc && (
                <div
                    className={`dropzone ${dragActive ? "dropzone--active" : ""}`}
                    onClick={() => inputRef.current?.click()}
                    onDragOver={(e) => {
                        e.preventDefault();
                        setDragActive(true);
                    }}
                    onDragLeave={() => setDragActive(false)}
                    onDrop={(e) => {
                        e.preventDefault();
                        setDragActive(false);
                        handleFiles(e.dataTransfer.files);
                    }}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
                >
                    <div className="dropzone__icon">⤓</div>
                    <p className="dropzone__label">{uploading ? "Reading & embedding…" : "Drop a PDF here"}</p>
                    <p className="dropzone__hint">or click to browse · max 20MB</p>
                    <input
                        ref={inputRef}
                        type="file"
                        accept="application/pdf"
                        onChange={(e) => handleFiles(e.target.files)}
                    />
                </div>
            )}

            {doc && (
                <div className="doc-meta">
                    <p className="doc-meta__name">{doc.filename}</p>
                    <div className="doc-meta__stats">
                        <span><b>{doc.num_pages}</b> pages</span>
                        <span><b>{doc.num_chunks}</b> chunks</span>
                        <span><b>{doc.elapsed_ms}</b> ms indexed</span>
                    </div>
                    <button className="doc-meta__reset" onClick={onReset}>
                        ✕ Remove & upload another
                    </button>
                </div>
            )}

            {error && <div className="banner">{error}</div>}

            <p className="about">
                Each page is split into overlapping chunks, embedded with{" "}
                <code>gemini-embedding-001</code>, and held in a per-document vector
                index. Questions retrieve the top-matching chunks by cosine similarity
                before <code>gemini-2.5-flash</code> drafts an answer grounded in only
                that retrieved text.
            </p>
        </div>
    );
}