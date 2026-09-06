interface Score {
  player: string;
  name: string;
  points: number;
  words: string[];
  unique_words: string[];
}

export interface RoundResult {
  source_word: string;
  solution_count: number;
  scores: Score[];
  shared_words: string[];
  missed_words: string[];
  totals: Record<string, number>;
}

interface Props {
  result: RoundResult;
  finished: boolean;
  onNext: () => void;
  onFlagRound: () => void;
  flagged: boolean;
  roundIdx: number;
  totalRounds: number;
  onShowStats?: () => void;
}

export function Results({
  result, finished, onNext, onFlagRound, flagged, roundIdx, totalRounds,
  onShowStats,
}: Props) {
  const found = new Set(result.scores.flatMap((s) => s.words)).size;
  const ranked = [...result.scores].sort(
    (a, b) => (result.totals[b.player] ?? 0) - (result.totals[a.player] ?? 0),
  );

  return (
    <div className="app">
      <div className="source-word">{result.source_word.toUpperCase()}</div>
      <p className="muted center" style={{ margin: "0 16px" }}>
        Runde {Math.min(roundIdx, totalRounds)} von {totalRounds} · {found} von{" "}
        {result.solution_count} gefunden
      </p>

      <div className="stack">
        {ranked.map((s) => (
          <section key={s.player}>
            <h3>
              {s.name} — {s.points} Punkte{" "}
              <span className="muted" style={{ fontWeight: 400 }}>
                (gesamt {result.totals[s.player] ?? 0})
              </span>
            </h3>
            <div className="row">
              {s.words.length === 0 && <span className="muted">nichts gefunden</span>}
              {s.words.map((w) => (
                <span
                  className={`chip${s.unique_words.includes(w) ? " unique" : ""}`}
                  key={w}
                >
                  {w}
                  {s.unique_words.includes(w) ? " ×2" : ""}
                </span>
              ))}
            </div>
          </section>
        ))}

        {result.missed_words.length > 0 && (
          <section>
            <h3 className="muted">Verpasst</h3>
            <div className="row">
              {result.missed_words.map((w) => (
                <span className="chip missed" key={w}>
                  {w}
                </span>
              ))}
            </div>
          </section>
        )}

        <div className="row" style={{ paddingBottom: 40 }}>
          {!finished && <button onClick={onNext}>Nächste Runde</button>}
          {finished && onShowStats && (
            <button onClick={onShowStats}>Auswertung ansehen</button>
          )}
          {finished && !onShowStats && <strong>Spiel vorbei</strong>}
          <button className="ghost" onClick={onFlagRound} disabled={flagged}>
            {flagged ? "Gemeldet" : "Schlechte Runde"}
          </button>
        </div>
      </div>
    </div>
  );
}
