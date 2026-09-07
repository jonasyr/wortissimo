import { describe, expect, it } from "vitest";
import { nextClaimant, resolveNames, togglePick, uniqueNames } from "./solo";

describe("nextClaimant", () => {
  it("advances to the next player", () => {
    expect(nextClaimant(0, 2)).toBe(1);
    expect(nextClaimant(1, 3)).toBe(2);
  });

  it("returns null once everyone has claimed", () => {
    expect(nextClaimant(1, 2)).toBeNull();
    expect(nextClaimant(2, 3)).toBeNull();
  });

  it("handles a single player", () => {
    expect(nextClaimant(0, 1)).toBeNull();
  });
});

describe("togglePick", () => {
  it("adds a word that was not picked", () => {
    expect(togglePick(["bahn"], "halte")).toEqual(["bahn", "halte"]);
  });

  it("removes a word that was picked", () => {
    expect(togglePick(["bahn", "halte"], "bahn")).toEqual(["halte"]);
  });

  it("does not mutate its input", () => {
    const before = ["bahn"];
    togglePick(before, "halte");
    expect(before).toEqual(["bahn"]);
  });

  it("round-trips", () => {
    expect(togglePick(togglePick(["bahn"], "halte"), "halte")).toEqual(["bahn"]);
  });
});

describe("resolveNames", () => {
  it("fills blanks with numbered defaults", () => {
    expect(resolveNames(["Jonas", ""])).toEqual(["Jonas", "Spieler 2"]);
  });

  it("gives two blanks different names", () => {
    // The networked mode collapsed two players into one over exactly this.
    expect(resolveNames(["", ""])).toEqual(["Spieler 1", "Spieler 2"]);
  });

  it("trims whitespace-only names", () => {
    expect(resolveNames(["   "])).toEqual(["Spieler 1"]);
  });
});

describe("uniqueNames", () => {
  it("leaves distinct names alone", () => {
    expect(uniqueNames(["Jonas", "Freundin"])).toEqual(["Jonas", "Freundin"]);
  });

  it("disambiguates a repeated name", () => {
    // Names are the identity in solo mode, so duplicates would merge two
    // players' scores into one.
    expect(uniqueNames(["Jonas", "Jonas"])).toEqual(["Jonas", "Jonas 2"]);
  });

  it("handles three of a kind", () => {
    expect(uniqueNames(["A", "A", "A"])).toEqual(["A", "A 2", "A 3"]);
  });
});
