import { describe, expect, it } from "vitest";
import { Clock } from "./clock";

describe("Clock", () => {
  it("computes offset from a round trip", () => {
    const c = new Clock();
    // Sent at 1000, server said 5500, reply seen at 1200.
    // Midpoint of the round trip is 1100, so the server is 4400 ahead.
    c.observe(1000, 5500, 1200);
    expect(c.offset).toBe(4400);
  });

  it("computes remaining time from an absolute deadline", () => {
    const c = new Clock();
    c.observe(1000, 5500, 1200);
    // Server deadline 9400 -> local 5000. At local 4000, 1000ms remain.
    expect(c.remaining(9400, 4000)).toBe(1000);
  });

  it("never reports negative remaining time", () => {
    const c = new Clock();
    expect(c.remaining(1000, 99999)).toBe(0);
  });

  it("prefers the sample with the lowest round-trip time", () => {
    const c = new Clock();
    c.observe(0, 1000, 400); // rtt 400, noisy
    c.observe(1000, 2000, 1020); // rtt 20, trustworthy -> offset 990
    expect(c.offset).toBe(990);
  });

  it("ignores a noisier later sample", () => {
    const c = new Clock();
    c.observe(1000, 2000, 1020);
    c.observe(0, 9999, 800);
    expect(c.offset).toBe(990);
  });

  it("works before any sample, assuming zero offset", () => {
    const c = new Clock();
    expect(c.remaining(5000, 4000)).toBe(1000);
  });

  it("is unaffected by how much wall time passes between reads", () => {
    // The property that makes it survive iOS freezing the tab: the answer
    // depends only on `now`, never on how often it was asked.
    const c = new Clock();
    c.observe(1000, 1000, 1000);
    expect(c.remaining(60_000, 10_000)).toBe(50_000);
    expect(c.remaining(60_000, 59_000)).toBe(1_000);
  });
});
