import { describe, expect, it } from "vitest";
import { MAX_MINUTES, MIN_MINUTES, parseMinutes } from "./Lobby";

describe("parseMinutes", () => {
  it("accepts the whole supported range", () => {
    expect(parseMinutes("1")).toBe(1);
    expect(parseMinutes("12")).toBe(12);
    expect(parseMinutes("30")).toBe(30);
  });

  it("rejects the empty string explicitly", () => {
    // Number("") is 0, so without an explicit guard an empty box would
    // start validating as legal the moment MIN_MINUTES reached 0.
    expect(parseMinutes("")).toBeNull();
    expect(parseMinutes("   ")).toBeNull();
  });

  it("rejects values outside the range", () => {
    expect(parseMinutes("0")).toBeNull();
    expect(parseMinutes("31")).toBeNull();
    expect(parseMinutes("99")).toBeNull();
  });

  it("rejects non-integers and junk", () => {
    expect(parseMinutes("1.5")).toBeNull();
    expect(parseMinutes("abc")).toBeNull();
    expect(parseMinutes("1e3")).toBeNull();
  });

  it("agrees with the server bounds", () => {
    expect(MIN_MINUTES * 60).toBe(60);
    expect(MAX_MINUTES * 60).toBe(1800);
  });

  it("never returns a value the server would reject", () => {
    for (let i = -5; i <= 120; i++) {
      const parsed = parseMinutes(String(i));
      if (parsed !== null) {
        const seconds = parsed * 60;
        expect(seconds).toBeGreaterThanOrEqual(60);
        expect(seconds).toBeLessThanOrEqual(1800);
      }
    }
  });
});
