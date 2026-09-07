import { useState } from "react";
import { MAX_MINUTES, MIN_MINUTES, parseMinutes } from "./Lobby";
import type { SoloConfig } from "../lib/solo";
import { resolveNames, uniqueNames } from "../lib/solo";

interface Props {
  onStart: (config: SoloConfig) => void;
  onBack: () => void;
}

const DIFFICULTIES = ["leicht", "mittel", "schwer", "brutal"] as const;
const ROUND_TIMES = [
  { label: "1 Min", seconds: 60 },
  { label: "2 Min", seconds: 120 },
  { label: "3 Min", seconds: 180 },
  { label: "5 Min", seconds: 300 },
] as const;
const ROUND_COUNTS = [3, 5, 10, 15] as const;
const MIN_PLAYERS = 2;
const MAX_PLAYERS = 6;

export function SoloSetup({ onStart, onBack }: Props) {
  const [names, setNames] = useState<string[]>(["", ""]);
  const [difficulty, setDifficulty] = useState<string>("mittel");
  const [presetSeconds, setPresetSeconds] = useState(180);
  const [customMinutes, setCustomMinutes] = useState("");
  const [rounds, setRounds] = useState(5);

  const customValid = parseMinutes(customMinutes);
  const customInvalid = customMinutes.trim() !== "" && customValid === null;
  const roundSeconds = customValid !== null ? customValid * 60 : presetSeconds;

  const setName = (i: number, value: string) =>
    setNames((prev) => prev.map((n, j) => (j === i ? value.slice(0, 24) : n)));

  const addPlayer = () =>
    setNames((prev) => (prev.length < MAX_PLAYERS ? [...prev, ""] : prev));
  const removePlayer = () =>
    setNames((prev) => (prev.length > MIN_PLAYERS ? prev.slice(0, -1) : prev));

  const start = () =>
    onStart({
      names: uniqueNames(resolveNames(names)),
      difficulty,
      roundSeconds,
      rounds,
    });

  return (
    <div className="app">
      <div className="stack">
        <div>
          <button className="ghost" onClick={onBack}>
            ← Zurück
          </button>
        </div>

        <h1>Auf Papier</h1>
        <p className="muted" style={{ margin: 0 }}>
          Ein Gerät, ein Wort, eine Uhr. Jeder schreibt auf Papier mit — danach
          tippt reihum jeder seine Wörter an.
        </p>

        <div>
          <label>
            Spieler ({names.length})
          </label>
          <div className="row" style={{ marginTop: 8 }}>
            <button
              className="ghost"
              onClick={removePlayer}
              disabled={names.length <= MIN_PLAYERS}
              aria-label="Einen Spieler entfernen"
            >
              −
            </button>
            <button
              className="ghost"
              onClick={addPlayer}
              disabled={names.length >= MAX_PLAYERS}
              aria-label="Einen Spieler hinzufügen"
            >
              +
            </button>
          </div>
          <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
            {names.map((name, i) => (
              <input
                key={i}
                value={name}
                onChange={(e) => setName(i, e.target.value)}
                placeholder={`Spieler ${i + 1}`}
                aria-label={`Name Spieler ${i + 1}`}
                autoCorrect="off"
                autoCapitalize="words"
                spellCheck={false}
              />
            ))}
          </div>
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
              aria-label="Eigene Rundenzeit in Minuten"
              aria-invalid={customInvalid}
              autoCorrect="off"
              spellCheck={false}
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

        <button onClick={start} disabled={customInvalid}>
          Runde starten · {Math.round(roundSeconds / 60)} Min
        </button>
      </div>
    </div>
  );
}
