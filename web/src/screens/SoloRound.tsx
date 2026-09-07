import { useEffect, useState } from "react";

interface Props {
  sourceWord: string;
  endsAt: number;
  solutionCount: number;
  roundIdx: number;
  totalRounds: number;
  onDone: () => void;
}

/**
 * The word and a clock. No input at all — the paper is the input.
 *
 * The countdown is local rather than server-anchored: there is one device
 * and one clock that everybody can see, so there is nothing to
 * synchronise and no suspension to survive.
 */
export function SoloRound({
  sourceWord,
  endsAt,
  solutionCount,
  roundIdx,
  totalRounds,
  onDone,
}: Props) {
  const [remaining, setRemaining] = useState(() =>
    Math.max(0, endsAt - Date.now()),
  );

  useEffect(() => {
    const tick = () => setRemaining(Math.max(0, endsAt - Date.now()));
    const id = window.setInterval(tick, 250);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [endsAt]);

  useEffect(() => {
    if (remaining === 0) onDone();
  }, [remaining, onDone]);

  const seconds = Math.ceil(remaining / 1000);

  return (
    <div className="app">
      <div className="bar">
        <span className={`timer${seconds <= 20 ? " urgent" : ""}`}>
          {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
        </span>
        <span>
          Runde {roundIdx + 1} von {totalRounds}
        </span>
        <span>{solutionCount} Lösungen</span>
      </div>

      <div className="source-word">{sourceWord.toUpperCase()}</div>

      <div className="stack">
        <p className="muted center" style={{ margin: 0 }}>
          Alle schreiben mit. Danach tippt reihum jeder seine Wörter an.
        </p>
        <button className="ghost" onClick={onDone}>
          Fertig
        </button>
      </div>
    </div>
  );
}
