import { useEffect, useRef, useState } from "react";
import { Connection } from "./lib/connection";
import { Lobby } from "./screens/Lobby";
import { Round } from "./screens/Round";
import { Results, type RoundResult } from "./screens/Results";
import "./styles.css";

type View =
  | { kind: "lobby" }
  | { kind: "waiting"; code: string }
  | { kind: "round"; sourceWord: string; endsAt: number; solutionCount: number }
  | { kind: "results"; result: RoundResult; finished: boolean };

export default function App() {
  const [view, setView] = useState<View>({ kind: "lobby" });
  const [opponentCount, setOpponentCount] = useState(0);
  const [flagged, setFlagged] = useState(false);
  const connectionRef = useRef<Connection | null>(null);

  const join = (gameCode: string, player: string) => {
    const connection = new Connection(gameCode, player);
    connectionRef.current = connection;

    connection.on("round_started", (m) => {
      setOpponentCount(0);
      setFlagged(false);
      setView({
        kind: "round",
        sourceWord: m.source_word,
        endsAt: m.round_ends_at,
        solutionCount: m.solution_count,
      });
    });

    connection.on("state", (m) => {
      if (m.round) {
        setView({
          kind: "round",
          sourceWord: m.round.source_word,
          endsAt: m.round.round_ends_at,
          solutionCount: m.round.solution_count,
        });
      } else if (m.state === "lobby" || m.state === "between") {
        setView((v) => (v.kind === "results" ? v : { kind: "waiting", code: gameCode }));
      }
    });

    connection.on("opponent_progress", (m) => setOpponentCount(m.count));
    connection.on("round_ended", (m) =>
      setView({ kind: "results", result: m.result, finished: false }),
    );
    connection.on("game_ended", () =>
      setView((v) => (v.kind === "results" ? { ...v, finished: true } : v)),
    );

    connection.connect();
    setView({ kind: "waiting", code: gameCode });
  };

  useEffect(() => connectionRef.current?.watchVisibility(), [view.kind]);

  if (view.kind === "lobby") return <Lobby onJoin={join} />;

  if (view.kind === "waiting") {
    return (
      <div className="app">
        <div className="stack center">
          <p className="muted">Spielcode — teile ihn mit deiner Mitspielerin</p>
          <div className="code">{view.code}</div>
          <button onClick={() => connectionRef.current?.startRound()}>
            Runde starten
          </button>
        </div>
      </div>
    );
  }

  if (view.kind === "round") {
    return (
      <Round
        connection={connectionRef.current!}
        sourceWord={view.sourceWord}
        endsAt={view.endsAt}
        solutionCount={view.solutionCount}
        opponentCount={opponentCount}
      />
    );
  }

  return (
    <Results
      result={view.result}
      finished={view.finished}
      flagged={flagged}
      onNext={() => connectionRef.current?.startRound()}
      onFlagRound={() => {
        setFlagged(true);
        void fetch("/api/flag", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source_word: view.result.source_word }),
        }).catch(() => setFlagged(false));
      }}
    />
  );
}
