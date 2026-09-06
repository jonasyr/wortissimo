import { beforeEach, describe, expect, it } from "vitest";
import { Outbox } from "./outbox";

describe("Outbox", () => {
  beforeEach(() => sessionStorage.clear());

  it("returns a uuid for each added word", () => {
    const o = new Outbox("round-0");
    expect(o.add("bahn").clientUuid).not.toBe(o.add("halte").clientUuid);
  });

  it("keeps unacked words pending", () => {
    const o = new Outbox("round-0");
    o.add("bahn");
    expect(o.pending().map((e) => e.word)).toEqual(["bahn"]);
  });

  it("drops a word once acked", () => {
    const o = new Outbox("round-0");
    o.ack(o.add("bahn").clientUuid);
    expect(o.pending()).toEqual([]);
  });

  it("survives being rebuilt from sessionStorage", () => {
    // The iOS case: the tab was suspended and the object is gone, but the
    // word the player typed must not be.
    new Outbox("round-0").add("bahn");
    expect(new Outbox("round-0").pending().map((e) => e.word)).toEqual(["bahn"]);
  });

  it("keeps separate queues per round", () => {
    new Outbox("round-0").add("bahn");
    expect(new Outbox("round-1").pending()).toEqual([]);
  });

  it("ignores an ack for an unknown uuid", () => {
    const o = new Outbox("round-0");
    o.add("bahn");
    o.ack("nope");
    expect(o.pending()).toHaveLength(1);
  });

  it("preserves order across a rebuild", () => {
    const o = new Outbox("round-0");
    o.add("bahn");
    o.add("halte");
    o.add("strasse");
    expect(new Outbox("round-0").pending().map((e) => e.word)).toEqual([
      "bahn",
      "halte",
      "strasse",
    ]);
  });

  it("does not throw when storage is unavailable", () => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new Error("quota");
    };
    try {
      // A private window or a full quota must not block the player.
      expect(() => new Outbox("round-0").add("bahn")).not.toThrow();
    } finally {
      Storage.prototype.setItem = original;
    }
  });
});
