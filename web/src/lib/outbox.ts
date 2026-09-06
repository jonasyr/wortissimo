/**
 * Durable submission queue.
 *
 * A word is persisted BEFORE it is sent and removed only once the server
 * acknowledges it. If iOS suspends the app between those two moments — a
 * lock, a call, a notification — the word survives and is replayed on
 * reconnect. The server deduplicates by clientUuid, so replaying is free
 * (spec section 8.2).
 */
export interface Entry {
  clientUuid: string;
  word: string;
}

function newUuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export class Outbox {
  private readonly key: string;

  constructor(roundKey: string) {
    this.key = `wortissimo.outbox.${roundKey}`;
  }

  private read(): Entry[] {
    try {
      const raw = sessionStorage.getItem(this.key);
      return raw ? (JSON.parse(raw) as Entry[]) : [];
    } catch {
      return [];
    }
  }

  private write(entries: Entry[]): void {
    try {
      sessionStorage.setItem(this.key, JSON.stringify(entries));
    } catch {
      /* Private mode, or quota exhausted. The in-flight send still
         happens; we lose only the crash-safety net. Never block the
         player over storage. */
    }
  }

  add(word: string): Entry {
    const entry: Entry = { clientUuid: newUuid(), word };
    this.write([...this.read(), entry]);
    return entry;
  }

  ack(clientUuid: string): void {
    this.write(this.read().filter((e) => e.clientUuid !== clientUuid));
  }

  pending(): Entry[] {
    return this.read();
  }
}
