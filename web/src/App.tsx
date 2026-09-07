import { useEffect, useRef, useState } from "react";
import { Connection } from "./lib/connection";
import { Lobby } from "./screens/Lobby";
import { Waiting } from "./screens/Waiting";
import { Round } from "./screens/Round";
import { Results, type RoundResult } from "./screens/Results";
import { Stats, type GameStats } from "./screens/Stats";
import { SoloSetup } from "./screens/SoloSetup";
import { SoloRound } from "./screens/SoloRound";
import { SoloClaim } from "./screens/SoloClaim";
import {
  fetchPuzzle, scoreClaims,
  type SoloConfig, type SoloPuzzle,
} from "./lib/solo";
import "./styles.css";

interface Player {
  id: string;
  name: string;
}

type View =
  | { kind: "lobby" }
  | { kind: "waiting" }
  | { kind: "round"; sourceWord: string; endsAt: number; solutionCount: number }
  | { kind: "results"; result: RoundResult; finished: boolean }
  | { kind: "stats"; stats: GameStats }
  | { kind: "solo_setup" }
  | { kind: "solo_round"; puzzle: SoloPuzzle; endsAt: number }
  | { kind: "solo_claim"; puzzle: SoloPuzzle; claimant: number }
  | { kind: "solo_result"; result: RoundResult };

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
  const [finalStats, setFinalStats] = useState<GameStats | null>(null);
  const [blind, setBlind] = useState(false);
  const [solo, setSolo] = useState<SoloConfig | null>(null);
  const [claims, setClaims] = useState<Record<string, string[]>>({});
  const [soloRoundIdx, setSoloRoundIdx] = useState(0);
  const [soloError, setSoloError] = useState<string | null>(null);
  const connectionRef = useRef<Connection | null>(null);

  // ---- solo (single device) ----

  const startSoloRound = async (config: SoloConfig) => {
    setSoloError(null);
    try {
      const puzzle = await fetchPuzzle(config.difficulty);
      setClaims({});
      setView({
        kind: "solo_round",
        puzzle,
        endsAt: Date.now() + config.roundSeconds * 1000,
      });
    } catch {
      setSoloError("Kein Rätsel erhalten. Server erreichbar?");
      setView({ kind: "solo_setup" });
    }
  };

  const finishClaims = async (puzzle: SoloPuzzle, all: Record<string, string[]>) => {
    const scored = await scoreClaims(puzzle.solutions, all);
    setView({
      kind: "solo_result",
      result: {
        source_word: puzzle.source_word,
        solution_count: puzzle.solution_count,
        scores: scored.scores.map((s) => ({ ...s, name: s.player })),
        shared_words: scored.shared_words,
        missed_words: scored.missed_words,
        totals: Object.fromEntries(scored.scores.map((s) => [s.player, s.points])),
      },
    });
  };

  const join = (gameCode: string, player: string, isBlind: boolean) => {
    setBlind(isBlind);
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
      if (typeof m.blind === "boolean") setBlind(m.blind);
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

    connection.on("game_ended", (m) => {
      setFinalStats(m.stats);
      setView((v) => (v.kind === "results" ? { ...v, finished: true } : v));
    });

    connection.connect();
    setView({ kind: "waiting" });
  };

  useEffect(() => connectionRef.current?.watchVisibility(), [view.kind]);

  if (view.kind === "lobby") {
    return (
      <Lobby onJoin={join} onSolo={() => setView({ kind: "solo_setup" })} />
    );
  }

  if (view.kind === "solo_setup") {
    return (
      <>
        {soloError && <div className="flash">{soloError}</div>}
        <SoloSetup
          onBack={() => setView({ kind: "lobby" })}
          onStart={(config) => {
            setSolo(config);
            setSoloRoundIdx(0);
            void startSoloRound(config);
          }}
        />
      </>
    );
  }

  if (view.kind === "solo_round") {
    return (
      <SoloRound
        sourceWord={view.puzzle.source_word}
        endsAt={view.endsAt}
        solutionCount={view.puzzle.solution_count}
        roundIdx={soloRoundIdx}
        totalRounds={solo?.rounds ?? 1}
        onDone={() =>
          setView({ kind: "solo_claim", puzzle: view.puzzle, claimant: 0 })
        }
      />
    );
  }

  if (view.kind === "solo_claim") {
    const names = solo?.names ?? [];
    return (
      <SoloClaim
        key={view.claimant}
        playerName={names[view.claimant] ?? "Spieler"}
        playerIndex={view.claimant}
        playerCount={names.length}
        sourceWord={view.puzzle.source_word}
        solutions={view.puzzle.solutions}
        onConfirm={(picks) => {
          const all = { ...claims, [names[view.claimant]]: picks };
          setClaims(all);
          const next = view.claimant + 1;
          if (next < names.length) {
            setView({ kind: "solo_claim", puzzle: view.puzzle, claimant: next });
          } else {
            void finishClaims(view.puzzle, all);
          }
        }}
      />
    );
  }

  if (view.kind === "solo_result") {
    const done = soloRoundIdx + 1 >= (solo?.rounds ?? 1);
    return (
      <Results
        result={view.result}
        finished={done}
        flagged
        roundIdx={soloRoundIdx + 1}
        totalRounds={solo?.rounds ?? 1}
        onFlagRound={() => undefined}
        onNext={() => {
          if (!solo) return;
          setSoloRoundIdx((i) => i + 1);
          void startSoloRound(solo);
        }}
      />
    );
  }

  if (view.kind === "stats") {
    return (
      <Stats
        stats={view.stats}
        onAgain={() => {
          connectionRef.current?.close();
          connectionRef.current = null;
          setFinalStats(null);
          setPlayers([]);
          setRoundIdx(0);
          setView({ kind: "lobby" });
        }}
      />
    );
  }

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
        blind={blind}
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
      onShowStats={
        finalStats ? () => setView({ kind: "stats", stats: finalStats! }) : undefined
      }
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
