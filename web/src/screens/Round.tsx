import { useEffect, useRef, useState } from "react";
import type { Connection } from "../lib/connection";
import { reasonText } from "../lib/reasons";
import { useKeyboardInset } from "../hooks/useKeyboardInset";

interface Props {
  connection: Connection;
  sourceWord: string;
  endsAt: number;
  solutionCount: number;
  opponentCount: number;
}

export function Round({
  connection,
  sourceWord,
  endsAt,
  solutionCount,
  opponentCount,
}: Props) {
  useKeyboardInset();
  const [remaining, setRemaining] = useState(() =>
    connection.clock.remaining(endsAt),
  );
  const [words, setWords] = useState<string[]>([]);
  const [flash, setFlash] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Recompute from the absolute deadline. The interval is only a repaint
  // trigger; it never accumulates elapsed time, so a frozen tab catches up
  // correctly the instant it wakes (spec section 8.1).
  useEffect(() => {
    const tick = () => setRemaining(connection.clock.remaining(endsAt));
    const id = window.setInterval(tick, 250);
    document.addEventListener("visibilitychange", tick);
    window.addEventListener("pageshow", tick);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
      window.removeEventListener("pageshow", tick);
    };
  }, [connection, endsAt]);

  useEffect(() => {
    connection.on("ack", (msg) => {
      if (msg.accepted) {
        setWords((prev) => (prev.includes(msg.word) ? prev : [msg.word, ...prev]));
      } else {
        setFlash(reasonText(msg.reason));
      }
    });
    connection.on("state", (msg) => {
      setWords([...(msg.my_words as string[])].reverse());
    });
  }, [connection]);

  useEffect(() => {
    if (!flash) return;
    const id = window.setTimeout(() => setFlash(null), 1600);
    return () => window.clearTimeout(id);
  }, [flash]);

  const over = remaining === 0;
  const seconds = Math.ceil(remaining / 1000);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const word = draft.trim();
    if (!word || over) return;
    connection.submit(word);
    setDraft("");
    inputRef.current?.focus(); // keep the keyboard up between words
  };

  return (
    <div className="app">
      <div className="bar">
        <span className={`timer${seconds <= 20 ? " urgent" : ""}`}>
          {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
        </span>
        <span>
          {words.length} / {solutionCount}
        </span>
        <span>Sie: {opponentCount}</span>
      </div>

      <div className="source-word">{sourceWord.toUpperCase()}</div>

      {flash && <div className="flash">{flash}</div>}

      <div className="word-list">
        {words.map((w) => (
          <span className="chip" key={w}>
            {w}
          </span>
        ))}
      </div>

      <form className="input-bar" onSubmit={submit}>
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          /* All four are required. iOS autocorrect silently rewrites German
             words as they are typed, and the player blames the game for the
             rejection that follows (spec section 13). */
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          autoComplete="off"
          enterKeyHint="send"
          inputMode="text"
          lang="de"
          placeholder={over ? "Runde vorbei" : "Wort eingeben"}
          disabled={over}
          aria-label="Gefundenes Wort"
        />
        <button type="submit" disabled={over || !draft.trim()}>
          OK
        </button>
      </form>
    </div>
  );
}
