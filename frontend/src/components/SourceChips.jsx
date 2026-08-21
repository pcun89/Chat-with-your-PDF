export default function SourceChips({ sources }) {
    if (!sources?.length) return null;
    return (
        <div className="sources">
            {sources.map((s, i) => (
                <span className="source-chip" tabIndex={0} key={i}>
                    p.{s.page} · {(s.relevance * 100).toFixed(0)}%
                    <span className="source-chip__pop">{s.snippet}</span>
                </span>
            ))}
        </div>
    );
}