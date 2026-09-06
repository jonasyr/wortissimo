import { Clock } from "./clock";
import { Outbox } from "./outbox";

type Handler = (msg: any) => void;

const TOKEN_KEY = "wortissimo.rejoin";
const MAX_BACKOFF = 10_000;

/**
 * WebSocket client written on the assumption that it will be killed.
 *
 * iOS terminates the socket when the screen locks — WebSockets are not a
 * connection type a suspended app may keep. So this reconnects on backoff
 * AND immediately when the page becomes visible again, rejoins with a
 * stored token, and replays the outbox (spec section 8.3).
 */
export class Connection {
  readonly clock = new Clock();
  private ws: WebSocket | null = null;
  private handlers = new Map<string, Set<Handler>>();
  private backoff = 500;
  private outbox: Outbox | null = null;
  private roundIdx = 0;
  private closed = false;

  constructor(
    private readonly code: string,
    private readonly player: string,
  ) {}

  on(type: string, handler: Handler): void {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set());
    this.handlers.get(type)!.add(handler);
  }

  private emit(msg: any): void {
    this.handlers.get(msg.type)?.forEach((h) => h(msg));
  }

  private useRound(idx: number): void {
    this.roundIdx = idx;
    this.outbox = new Outbox(`r${idx}`);
  }

  connect(): void {
    this.closed = false;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    this.ws = ws;

    ws.onopen = () => {
      this.backoff = 500;
      let token: string | null = null;
      try {
        token = localStorage.getItem(TOKEN_KEY);
      } catch {
        /* private mode */
      }
      this.send({
        type: "join",
        code: this.code,
        player: this.player,
        rejoin_token: token,
      });
      this.ping();
    };

    ws.onmessage = (event) => {
      let msg: any;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }

      if (msg.type === "joined") {
        try {
          localStorage.setItem(TOKEN_KEY, msg.rejoin_token);
        } catch {
          /* private mode */
        }
      }
      if (msg.type === "pong") {
        this.clock.observe(msg.t0, msg.server_time, Date.now());
      }
      if (msg.type === "ack") this.outbox?.ack(msg.client_uuid);
      if (msg.type === "round_started") this.useRound(msg.idx);
      if (msg.type === "state") {
        if (msg.round) this.useRound(msg.round.idx);
        // Resync arrives after join; only now is it safe to replay, since
        // we know which round the queued words belong to.
        this.replay();
      }
      this.emit(msg);
    };

    ws.onclose = () => {
      if (this.closed) return;
      setTimeout(() => this.connect(), this.backoff);
      this.backoff = Math.min(this.backoff * 2, MAX_BACKOFF);
    };
  }

  /** Reconnect the moment the phone comes back, not on the next backoff tick. */
  watchVisibility(): () => void {
    const wake = () => {
      if (document.visibilityState !== "visible") return;
      if (this.ws?.readyState !== WebSocket.OPEN) this.connect();
      else this.ping();
    };
    document.addEventListener("visibilitychange", wake);
    window.addEventListener("pageshow", wake);
    return () => {
      document.removeEventListener("visibilitychange", wake);
      window.removeEventListener("pageshow", wake);
    };
  }

  private send(payload: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  private ping(): void {
    this.send({ type: "ping", t0: Date.now() });
  }

  private replay(): void {
    for (const entry of this.outbox?.pending() ?? []) {
      this.send({
        type: "submit",
        client_uuid: entry.clientUuid,
        word: entry.word,
        round_idx: this.roundIdx,
      });
    }
  }

  submit(word: string): void {
    if (!this.outbox) return;
    const entry = this.outbox.add(word);
    this.send({
      type: "submit",
      client_uuid: entry.clientUuid,
      word: entry.word,
      round_idx: this.roundIdx,
    });
  }

  startRound(): void {
    this.send({ type: "start_round" });
  }

  close(): void {
    this.closed = true;
    this.ws?.close();
  }
}
