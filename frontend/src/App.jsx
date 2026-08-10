import { useState } from "react";
import UploadPanel from "./components/UploadPanel.jsx";
import ChatPanel from "./components/ChatPanel.jsx";
import { uploadDocument, askQuestion, deleteDocument } from "./api.js";

export default function App() {
    const [doc, setDoc] = useState(null); // {document_id, filename, num_pages, num_chunks, elapsed_ms}
    const [uploading, setUploading] = useState(false);
    const [uploadError, setUploadError] = useState("");
    const [messages, setMessages] = useState([]);
    const [busy, setBusy] = useState(false);

    async function handleUpload(file, manualError) {
        setUploadError("");
        if (manualError) {
            setUploadError(manualError);
            return;
        }
        try {
            const result = await uploadDocument(file, setUploading);
            setDoc(result);
            setMessages([]);
        } catch (err) {
            setUploadError(err.message || "Upload failed.");
        }
    }

    async function handleReset() {
        if (doc) {
            deleteDocument(doc.document_id).catch(() => { });
        }
        setDoc(null);
        setMessages([]);
        setUploadError("");
    }

    async function handleSend(question) {
        const nextMessages = [...messages, { role: "user", content: question }];
        setMessages(nextMessages);
        setBusy(true);
        try {
            const history = nextMessages.map((m) => ({ role: m.role, content: m.content }));
            const result = await askQuestion(doc.document_id, question, history.slice(0, -1));
            setMessages((prev) => [
                ...prev,
                { role: "assistant", content: result.answer, sources: result.sources },
            ]);
        } catch (err) {
            setMessages((prev) => [
                ...prev,
                { role: "error", content: err.message || "Something went wrong answering that." },
            ]);
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="app">
            <header className="app__header">
                <h1 className="app__title">
                    <span className="dot" />
                    chat-with-your-pdf
                </h1>
                <span className="app__subtitle">retrieval-augmented Q&amp;A · Gemini</span>
            </header>

            <div className="layout">
                <UploadPanel
                    doc={doc}
                    uploading={uploading}
                    error={uploadError}
                    onUpload={handleUpload}
                    onReset={handleReset}
                />
                <ChatPanel docReady={!!doc} messages={messages} busy={busy} onSend={handleSend} />
            </div>

            <p className="footer-note">
                documents are held in memory for this session only · nothing is persisted
            </p>
        </div>
    );
}