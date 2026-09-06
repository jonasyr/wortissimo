interface PlayerRef {
  id: string;
  name: string;
}

interface PerPlayer {
  points: number;
  words: number;
  unique: number;
  longest: string | null;
}

interface RoundStat {
  idx: number;
  source_word: string;
  solution_count: number;
  found: number;
  per_player: Record<string, PerPlayer>;
}

export interface GameStats {
  players: PlayerRef[];
  rounds: RoundStat[];
  totals: Record<string, number>;
}

interface Props {
  stats: GameStats;
  onAgain: () => void;
}

const SERIES = ["var(--series-a)", "var(--series-b)"];

function sum(stats: GameStats, id: string, key: keyof PerPlayer): number {
  return stats.rounds.reduce((acc, r) => {
    const v = r.per_player[id]?.[key];
    return acc + (typeof v === "number" ? v : 0);
  }, 0);
}

function longestOverall(stats: GameStats, id: string): string | null {
  let best: string | null = null;
  for (const r of stats.rounds) {
    const w = r.per_player[id]?.longest;
    if (w && (!best || w.length > best.length)) best = w;
  }
  return best;
}

/**
 * Words found per round, grouped bars, one group per round.
 *
 * Grouped bars rather than lines: with 3-15 discrete rounds the question
 * is "who found more in round 4", which is a comparison, not a trend.
 */
function WordsPerRound({ stats }: { stats: GameStats }) {
  const players = stats.players;
  const rounds = stats.rounds;
  if (rounds.length === 0) return null;

  const max = Math.max(
    1,
    ...rounds.flatMap((r) => players.map((p) => r.per_player[p.id]?.words ?? 0)),
  );

  const barW = 14;
  const gap = 4;
  const groupW = players.length * barW + (players.length - 1) * gap;
  const groupGap = 20;
  const padL = 30;
  const padB = 28;
  const padT = 12;
  const plotH = 150;
  const width = padL + rounds.length * (groupW + groupGap) + 12;
  const height = plotH + padT + padB;

  // Ticks at 0, half, max so every label names a value the chart reaches.
  const ticks = [0, Math.round(max / 2), max].filter(
    (v, i, a) => a.indexOf(v) === i,
  );

  return (
    <div className="chart-scroll">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label="Gefundene Wörter pro Runde"
        style={{ display: "block" }}
      >
        {ticks.map((t) => {
          const y = padT + plotH - (t / max) * plotH;
          return (
            <g key={t}>
              <line
                x1={padL}
                x2={width - 6}
                y1={y}
                y2={y}
                stroke="var(--line)"
                strokeWidth={1}
              />
              <text
                x={padL - 8}
                y={y + 4}
                textAnchor="end"
                fontSize="11"
                fill="var(--muted)"
              >
                {t}
              </text>
            </g>
          );
        })}

        {rounds.map((r, ri) => {
          const gx = padL + ri * (groupW + groupGap) + groupGap / 2;
          return (
            <g key={r.idx}>
              {players.map((p, pi) => {
                const value = r.per_player[p.id]?.words ?? 0;
                const h = (value / max) * plotH;
                const x = gx + pi * (barW + gap);
                const y = padT + plotH - h;
                return (
                  <rect
                    key={p.id}
                    x={x}
                    y={h === 0 ? padT + plotH - 2 : y}
                    width={barW}
                    height={h === 0 ? 2 : h}
                    rx={4}
                    fill={SERIES[pi % SERIES.length]}
                  >
                    <title>
                      {p.name}, Runde {r.idx + 1}: {value} Wörter
                    </title>
                  </rect>
                );
              })}
              <text
                x={gx + groupW / 2}
                y={height - 9}
                textAnchor="middle"
                fontSize="11"
                fill="var(--muted)"
              >
                {r.idx + 1}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function Stats({ stats, onAgain }: Props) {
  const players = stats.players;
  const ranked = [...players].sort(
    (a, b) => (stats.totals[b.id] ?? 0) - (stats.totals[a.id] ?? 0),
  );
  const top = stats.totals[ranked[0]?.id] ?? 0;
  const drawn =
    ranked.length > 1 && (stats.totals[ranked[1].id] ?? 0) === top;

  return (
    <div className="app">
      <div className="stack">
        <div className="center">
          <p className="muted" style={{ margin: 0 }}>
            {stats.rounds.length} Runden gespielt
          </p>
          <h1 style={{ marginTop: 6 }}>
            {drawn ? "Unentschieden" : `${ranked[0]?.name ?? "—"} gewinnt`}
          </h1>
        </div>

        <div className="stats-grid">
          {ranked.map((p, i) => (
            <div className="stat" key={p.id}>
              <div className="stat-label">
                <span
                  className="swatch"
                  style={{
                    background: SERIES[players.findIndex((x) => x.id === p.id)],
                    marginRight: 6,
                  }}
                />
                {p.name}
              </div>
              <div
                className={`stat-value${i === 0 && !drawn ? " winner" : ""}`}
              >
                {stats.totals[p.id] ?? 0}
              </div>
              <div className="stat-label">
                {sum(stats, p.id, "words")} Wörter ·{" "}
                {sum(stats, p.id, "unique")} exklusiv
              </div>
            </div>
          ))}
        </div>

        <section>
          <h2>Wörter pro Runde</h2>
          <p className="legend" style={{ marginTop: 0, marginBottom: 10 }}>
            {players.map((p, i) => (
              <span key={p.id}>
                <span className="swatch" style={{ background: SERIES[i] }} />
                {p.name}
              </span>
            ))}
          </p>
          <WordsPerRound stats={stats} />
        </section>

        <section>
          <h2>Längstes Wort</h2>
          <div className="row">
            {players.map((p) => {
              const w = longestOverall(stats, p.id);
              return (
                <span className="chip" key={p.id}>
                  {p.name}: {w ? `${w} (${w.length})` : "—"}
                </span>
              );
            })}
          </div>
        </section>

        <section>
          <h2>Runden</h2>
          <div style={{ display: "grid", gap: 8 }}>
            {stats.rounds.map((r) => (
              <div
                key={r.idx}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 12,
                  borderBottom: "1px solid var(--line)",
                  paddingBottom: 8,
                }}
              >
                <span style={{ wordBreak: "break-all" }}>
                  <span className="muted">{r.idx + 1}.</span> {r.source_word}
                </span>
                <span className="muted" style={{ whiteSpace: "nowrap" }}>
                  {r.found}/{r.solution_count}
                </span>
              </div>
            ))}
          </div>
        </section>

        <button onClick={onAgain} style={{ marginBottom: 40 }}>
          Neues Spiel
        </button>
      </div>
    </div>
  );
}
