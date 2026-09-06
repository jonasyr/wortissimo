import { describe, expect, it } from "vitest";
import { Connection } from "./connection";

describe("Connection subscriptions", () => {
  it("returns an unsubscribe that actually removes the handler", () => {
    const c = new Connection("ABCD", "jw");
    const seen: string[] = [];
    const off = c.on("ack", () => seen.push("first"));
    c.on("ack", () => seen.push("second"));

    (c as any).emit({ type: "ack" });
    expect(seen).toEqual(["first", "second"]);

    off();
    seen.length = 0;
    (c as any).emit({ type: "ack" });
    // Without cleanup, a screen remounting each round stacks up stale
    // handlers and every one of them fires.
    expect(seen).toEqual(["second"]);
  });

  it("does not fire handlers for other message types", () => {
    const c = new Connection("ABCD", "jw");
    let hits = 0;
    c.on("ack", () => hits++);
    (c as any).emit({ type: "state" });
    expect(hits).toBe(0);
  });
});
