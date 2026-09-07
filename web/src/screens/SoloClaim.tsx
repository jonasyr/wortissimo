import { useState } from "react";
import { togglePick } from "../lib/solo";

interface Props {
  playerName: string;
  playerIndex: number;
  playerCount: number;
  sourceWord: string;
  solutions: string[];
  onConfirm: (picks: string[]) => void;
}

/**
 * One player at a time ticks off what they wrote down, then hands over.
 *
 * Player-by-player rather than a shared grid: it mirrors reading your own
 * sheet, keeps one name on screen so nobody claims the wrong row, and
 * needs no extra layout for a third or fourth player.
 */
export function SoloClaim({
  playerName,
  playerIndex,
  playerCount,
  sourceWord,
  solutions,
  onConfirm,
}: Props) {
  const [picks, setPicks] = useState<string[]>([]);
  const last = playerIndex + 1 >= playerCount;

  return (
    <div className="app">
      <div className="bar">
        <span className="muted">
          {playerIndex + 1} von {playerCount}
        </span>
        <span>
          {picks.length} angetippt
        </span>
      </div>

      <div className="stack">
        <div className="center">
          <h1>{playerName}</h1>
          <p className="muted" style={{ margin: "4px 0 0" }}>
            Tippe an, was du gefunden hast.
          </p>
        </div>

        <p className="muted center" style={{ margin: 0, wordBreak: "break-all" }}>
          {sourceWord.toUpperCase()}
        </p>

        <div className="row">
          {solutions.map((word) => {
            const picked = picks.includes(word);
            return (
              <button
                key={word}
                type="button"
                className={picked ? "" : "ghost"}
                aria-pressed={picked}
                onClick={() => setPicks((p) => togglePick(p, word))}
                style={{ minHeight: 44, padding: "0 14px", fontSize: 16 }}
              >
                {word}
              </button>
            );
          })}
        </div>

        <button onClick={() => onConfirm(picks)} style={{ marginBottom: 40 }}>
          {last ? "Auswerten" : "Weiter"}
        </button>
      </div>
    </div>
  );
}
