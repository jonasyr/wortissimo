import { useEffect, useRef, useState } from "react";
import { Connection } from "./lib/connection";
import { Lobby } from "./screens/Lobby";
import { Waiting } from "./screens/Waiting";
import { Round } from "./screens/Round";
import { Results, type RoundResult } from "./screens/Results";
import "./styles.css";

interface Player {
  id: string;
  name: string;
}

type View =
  | { kind: "lobby" }
  | { kind: "waiting" }
  | { kind: "round"; sourceWord: string; endsAt: number; solutionCount: number }
  | { kind: "results"; result: RoundResult; finished: boolean };

export default function App() {
  const [view, setView] = useState<View>({ kind: "lobby" });
  const [opponentCount, setOpponentCount] = useState(0);
  const [flagged, setFlagged] = useState(false);
  const [players, setPlayers] = useState<Player[]>([]);
  const [me, setMe] = useState("");
  const [code, setCode] = useState("");
  const [connected, setConnected] = useState(false);
  const [roundSeconds, setRoundSeconds] = useState(180);
  const [totalRounds, setTotalRounds] = useState(10);
  const [roundIdx, setRoundIdx] = useState(0);
  const connectionRef = useRef<Connection | null>(null);

  const join = (gameCode: string, player: string) => {
    const connection = new Connection(gameCode, player);
    connectionRef.current = connection;
    setCode(gameCode);

    connection.on("joined", (m) => {
      setMe(m.player_id);
      setConnected(true);
    });

    connection.on("players", (m) => setPlayers(m.players));

    connection.on("round_started", (m) => {
      setOpponentCount(0);
      setFlagged(false);
      setRoundIdx(m.idx);
      setView({
        kind: "round",
        sourceWord: m.source_word,
        endsAt: m.round_ends_at,
        solutionCount: m.solution_count,
      });
    });

    connection.on("state", (m) => {
      if (m.players) setPlayers(m.players);
      if (m.round_seconds) setRoundSeconds(m.round_seconds);
      if (m.total_rounds) setTotalRounds(m.total_rounds);
      if (m.round) {
        setRoundIdx(m.round.idx);
        setView({
          kind: "round",
          sourceWord: m.round.source_word,
          endsAt: m.round.round_ends_at,
          solutionCount: m.round.solution_count,
        });
      } else if (m.state === "lobby" || m.state === "between") {
        setView((v) => (v.kind === "results" ? v : { kind: "waiting" }));
      }
    });

    connection.on("opponent_progress", (m) => setOpponentCount(m.count));

    connection.on("round_ended", (m) => {
      setRoundIdx(m.idx + 1);
      setView({ kind: "results", result: m.result, finished: false });
    });

    connection.on("game_ended", () =>
      setView((v) => (v.kind === "results" ? { ...v, finished: true } : v)),
    );

    connection.connect();
    setView({ kind: "waiting" });
  };

  useEffect(() => connectionRef.current?.watchVisibility(), [view.kind]);

  if (view.kind === "lobby") return <Lobby onJoin={join} />;

  if (view.kind === "waiting") {
    return (
      <Waiting
        code={code}
        players={players}
        me={me}
        roundSeconds={roundSeconds}
        totalRounds={totalRounds}
        roundIdx={roundIdx}
        connected={connected}
        onStart={() => connectionRef.current?.startRound()}
      />
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
      finished={view.finished || roundIdx >= totalRounds}
      flagged={flagged}
      roundIdx={roundIdx}
      totalRounds={totalRounds}
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
