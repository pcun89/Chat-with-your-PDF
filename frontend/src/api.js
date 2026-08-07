const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function handle(res) {
    if (!res.ok) {
        let detail = res.statusText;
        try {
            const body = await res.json();
            detail = body.detail || detail;
        } catch {
            /* ignore parse failure */
        }
        throw new Error(detail);
    }
    return res.json();
}

export async function uploadDocument(file, onUploading) {
    const form = new FormData();
    form.append("file", file);
    onUploading?.(true);
    try {
        const res = await fetch(`${API_URL}/api/documents`, {
            method: "POST",
            body: form,
        });
        return await handle(res);
    } finally {
        onUploading?.(false);
    }
}

export async function askQuestion(documentId, question, history) {
    const res = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_id: documentId, question, history }),
    });
    return handle(res);
}

export async function deleteDocument(documentId) {
    const res = await fetch(`${API_URL}/api/documents/${documentId}`, {
        method: "DELETE",
    });
    return handle(res);
}