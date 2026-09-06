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

export const MIN_MINUTES = 1;
export const MAX_MINUTES = 30;

/**
 * Parse the custom-minutes box. Returns null for anything unusable.
 *
 * The empty string is rejected explicitly rather than left to the range
 * check: Number("") is 0, so an empty box would begin validating as a
 * legal value the moment MIN_MINUTES ever reached 0.
 */
export function parseMinutes(raw: string): number | null {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  if (!Number.isInteger(n)) return null;
  if (n < MIN_MINUTES || n > MAX_MINUTES) return null;
  return n;
}

export function Lobby({ onJoin }: Props) {
  const [player, setPlayer] = useState("");
  const [code, setCode] = useState("");
  const [difficulty, setDifficulty] = useState<string>("mittel");
  const [presetSeconds, setPresetSeconds] = useState(180);
  const [customMinutes, setCustomMinutes] = useState("");
  const [rounds, setRounds] = useState(10);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Derived, never mirrored into state. Mirroring on each keystroke left a
  // stale value behind when the box was cleared, so a game could be created
  // with a round length that nothing on screen was showing.
  const customValid = parseMinutes(customMinutes);
  const customInvalid = customMinutes.trim() !== "" && customValid === null;
  const roundSeconds = customValid !== null ? customValid * 60 : presetSeconds;

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/games", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ difficulty, rounds, round_seconds: roundSeconds }),
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

        <div>
          <label htmlFor="name">Dein Name</label>
          <input
            id="name"
            value={player}
            onChange={(e) => setPlayer(e.target.value.slice(0, 24))}
            placeholder="z. B. Jonas"
            autoCorrect="off"
            autoCapitalize="words"
            spellCheck={false}
            style={{ width: "100%", marginTop: 8 }}
          />
        </div>

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
            {ROUND_TIMES.map((t) => {
              const active = customValid === null && presetSeconds === t.seconds;
              return (
                <button
                  key={t.seconds}
                  type="button"
                  className={active ? "" : "ghost"}
                  onClick={() => {
                    setPresetSeconds(t.seconds);
                    setCustomMinutes("");
                  }}
                  aria-pressed={active}
                >
                  {t.label}
                </button>
              );
            })}
          </div>
          <div className="row" style={{ marginTop: 8, alignItems: "center" }}>
            <input
              value={customMinutes}
              onChange={(e) =>
                setCustomMinutes(e.target.value.replace(/[^0-9]/g, "").slice(0, 2))
              }
              placeholder="eigene"
              inputMode="numeric"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              aria-label="Eigene Rundenzeit in Minuten"
              aria-invalid={customInvalid}
              style={{ width: 96, textAlign: "center" }}
            />
            <span className="muted" style={{ fontSize: 14 }}>
              Min ({MIN_MINUTES}–{MAX_MINUTES})
            </span>
          </div>
          {customInvalid && (
            <p className="flash" style={{ marginTop: 8 }}>
              Bitte eine ganze Zahl zwischen {MIN_MINUTES} und {MAX_MINUTES}.
            </p>
          )}
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

        <button onClick={create} disabled={busy || customInvalid}>
          {busy
            ? "…"
            : `Neues Spiel · ${Math.round(roundSeconds / 60)} Min · ${rounds} Runden`}
        </button>

        {player.trim() === "" && (
          <p className="muted" style={{ margin: 0, fontSize: 14 }}>
            Ohne Namen heißt du „Spieler“ — mit Namen ist die Auswertung leichter
            zu lesen.
          </p>
        )}

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
