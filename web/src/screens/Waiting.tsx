interface Player {
  id: string;
  name: string;
}

interface Props {
  code: string;
  players: Player[];
  me: string;
  roundSeconds: number;
  totalRounds: number;
  roundIdx: number;
  connected: boolean;
  onStart: () => void;
}

function minutes(seconds: number): string {
  if (seconds % 60 === 0) return `${seconds / 60} Min`;
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")} Min`;
}

export function Waiting({
  code,
  players,
  me,
  roundSeconds,
  totalRounds,
  roundIdx,
  connected,
  onStart,
}: Props) {
  const alone = players.length < 2;

  return (
    <div className="app">
      <div className="stack">
        <div className="center">
          <p className="muted" style={{ margin: 0 }}>
            {roundIdx === 0 ? "Spielcode" : `Nächste Runde ${roundIdx + 1} von ${totalRounds}`}
          </p>
          <div className="code">{code}</div>
          <p className="muted" style={{ margin: 0, fontSize: 15 }}>
            {minutes(roundSeconds)} pro Runde · {totalRounds} Runden
          </p>
        </div>

        <section>
          <h2>
            {players.length === 1
              ? "1 Spieler im Raum"
              : `${players.length} Spieler im Raum`}
          </h2>
          <div className="row">
            {players.map((p) => (
              <span className="chip" key={p.id}>
                {p.name}
                {p.id === me ? " (du)" : ""}
              </span>
            ))}
            {alone && <span className="chip missed">wartet auf Mitspieler …</span>}
          </div>
        </section>

        {alone && (
          <p className="muted" style={{ margin: 0 }}>
            Gib den Code weiter — oder starte allein, wenn du üben möchtest.
          </p>
        )}

        <button onClick={onStart} disabled={!connected}>
          {connected ? "Runde starten" : "Verbinde …"}
        </button>
      </div>
    </div>
  );
}
