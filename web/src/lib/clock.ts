/**
 * Server-anchored clock.
 *
 * The timer must NEVER be a tick count. iOS freezes timers when the tab is
 * suspended — which happens every time the phone locks — so accumulated
 * elapsed time drifts arbitrarily and silently. Instead the server issues
 * an absolute deadline and we render the difference against corrected
 * local time (spec section 8.1).
 *
 * The consequence worth stating: remaining() depends only on `now`, never
 * on how often it is called. Missing a thousand ticks costs nothing.
 */
export class Clock {
  offset = 0;
  private bestRtt = Number.POSITIVE_INFINITY;

  /** Fold in one ping/pong round trip. */
  observe(t0: number, serverTime: number, t1: number): void {
    const rtt = t1 - t0;
    if (rtt > this.bestRtt) return;
    this.bestRtt = rtt;
    this.offset = serverTime - (t0 + rtt / 2);
  }

  /** Milliseconds until an absolute server deadline. Never negative. */
  remaining(endsAt: number, now: number = Date.now()): number {
    return Math.max(0, endsAt - (now + this.offset));
  }
}
