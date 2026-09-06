import { useState } from "react";

interface Props {
  onJoin: (code: string, player: string) => void;
}

const DIFFICULTIES = ["leicht", "mittel", "schwer", "brutal"] as const;
const ROUND_TIMES = [
  { label: "1 Min", seconds: 60 },
  { label: "2 Min", seconds: 120 },
  { label: "3 Min", seconds: 180 },
  { label: "5 Min", seconds: 300 },
] as const;
const ROUND_COUNTS = [3, 5, 10, 15] as const;

export function Lobby({ onJoin }: Props) {
  const [player, setPlayer] = useState("");
  const [code, setCode] = useState("");
  const [difficulty, setDifficulty] = useState<string>("mittel");
  const [roundSeconds, setRoundSeconds] = useState(180);
  const [rounds, setRounds] = useState(10);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/games", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          difficulty,
          rounds,
          round_seconds: roundSeconds,
        }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const { code: newCode } = await res.json();
      onJoin(newCode, player.trim() || "Spieler");
    } catch {
      setError("Spiel konnte nicht erstellt werden. Server erreichbar?");
      setBusy(false);
    }
  };

  return (
    <div className="app">
      <div className="stack">
        <h1>Wortissimo</h1>
        <p className="muted" style={{ margin: 0 }}>
          Finde deutsche Wörter, die zusammenhängend im Rätselwort stecken.
        </p>

        <input
          value={player}
          onChange={(e) => setPlayer(e.target.value)}
          placeholder="Dein Name"
          autoCorrect="off"
          autoCapitalize="words"
          spellCheck={false}
          aria-label="Dein Name"
        />

        <div>
          <label>Schwierigkeit</label>
          <div className="row" style={{ marginTop: 8 }}>
            {DIFFICULTIES.map((d) => (
              <button
                key={d}
                type="button"
                className={difficulty === d ? "" : "ghost"}
                onClick={() => setDifficulty(d)}
                aria-pressed={difficulty === d}
              >
                {d}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label>Zeit pro Runde</label>
          <div className="row" style={{ marginTop: 8 }}>
            {ROUND_TIMES.map((t) => (
              <button
                key={t.seconds}
                type="button"
                className={roundSeconds === t.seconds ? "" : "ghost"}
                onClick={() => setRoundSeconds(t.seconds)}
                aria-pressed={roundSeconds === t.seconds}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label>Runden</label>
          <div className="row" style={{ marginTop: 8 }}>
            {ROUND_COUNTS.map((n) => (
              <button
                key={n}
                type="button"
                className={rounds === n ? "" : "ghost"}
                onClick={() => setRounds(n)}
                aria-pressed={rounds === n}
              >
                {n}
              </button>
            ))}
          </div>
        </div>

        <button onClick={create} disabled={busy}>
          {busy ? "…" : "Neues Spiel"}
        </button>

        {error && <div className="flash">{error}</div>}

        <hr style={{ border: 0, borderTop: "1px solid var(--line)", width: "100%" }} />

        <label htmlFor="code">Einem Spiel beitreten</label>
        <input
          id="code"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase().slice(0, 4))}
          placeholder="CODE"
          autoCorrect="off"
          autoCapitalize="characters"
          spellCheck={false}
          inputMode="text"
          maxLength={4}
          style={{ letterSpacing: "0.3em", textAlign: "center" }}
          aria-label="Spielcode"
        />
        <button
          onClick={() => onJoin(code, player.trim() || "Spieler")}
          disabled={code.length !== 4}
        >
          Beitreten
        </button>
      </div>
    </div>
  );
}
