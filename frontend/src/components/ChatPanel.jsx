import { useEffect, useRef, useState } from "react";
import SourceChips from "./SourceChips.jsx";

const TRACE_STEPS = [
    "embedding question…",
    "scanning chunk index…",
    "ranking by cosine similarity…",
    "drafting grounded answer…",
];

function RetrievalTrace() {
    const [step, setStep] = useState(0);
    useEffect(() => {
        const id = setInterval(() => setStep((s) => Math.min(s + 1, TRACE_STEPS.length - 1)), 650);
        return () => clearInterval(id);
    }, []);
    return (
        <div className="trace">
            <div className="trace__line">
                <span>{TRACE_STEPS[step]}</span>
                <span className="trace__bar">
                    <span className="trace__bar-fill" />
                </span>
            </div>
        </div>
    );
}

export default function ChatPanel({ docReady, messages, busy, onSend }) {
    const [draft, setDraft] = useState("");
    const scrollRef = useRef(null);

    useEffect(() => {
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }, [messages, busy]);

    function submit(e) {
        e.preventDefault();
        const q = draft.trim();
        if (!q || busy || !docReady) return;
        onSend(q);
        setDraft("");
    }

    return (
        <div className="card chat">
            <div className="card__header">02 — Ask the document</div>

            <div className="chat__messages" ref={scrollRef}>
                {messages.length === 0 && (
                    <div className="chat__empty">
                        {docReady
                            ? "Ask anything about the document — try \"summarize this in 3 bullets\" or \"what's the most important number in here?\""
                            : "Upload a PDF on the left to start asking it questions."}
                    </div>
                )}

                {messages.map((m, i) => (
                    <div className={`msg msg--${m.role}`} key={i}>
                        <div className="msg__bubble">{m.content}</div>
                        {m.sources && <SourceChips sources={m.sources} />}
                    </div>
                ))}

                {busy && <RetrievalTrace />}
            </div>

            <form className="chat__input-row" onSubmit={submit}>
                <input
                    placeholder={docReady ? "Ask a question about this PDF…" : "Upload a PDF first…"}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    disabled={!docReady || busy}
                />
                <button className="chat__send" type="submit" disabled={!docReady || busy || !draft.trim()}>
                    Ask
                </button>
            </form>
        </div>
    );
}