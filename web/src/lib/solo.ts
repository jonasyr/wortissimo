/**
 * Single-device "on paper" mode.
 *
 * No socket, no room, no game record — with one device there is nothing to
 * synchronise. The server supplies a puzzle and settles the scoring; every
 * other piece of state lives in React for the length of one sitting.
 */

export interface SoloPuzzle {
  source_word: string;
  solutions: string[];
  solution_count: number;
}

export interface SoloScore {
  player: string;
  points: number;
  words: string[];
  unique_words: string[];
}

export interface SoloResult {
  scores: SoloScore[];
  shared_words: string[];
  missed_words: string[];
}

export interface SoloConfig {
  names: string[];
  difficulty: string;
  roundSeconds: number;
  rounds: number;
}

export async function fetchPuzzle(difficulty: string): Promise<SoloPuzzle> {
  const res = await fetch(`/api/solo/puzzle?difficulty=${encodeURIComponent(difficulty)}`);
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

export async function scoreClaims(
  solutions: string[],
  claims: Record<string, string[]>,
): Promise<SoloResult> {
  const res = await fetch("/api/solo/score", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ solutions, claims }),
  });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

/** Index of the next player to claim, or null once everyone has. */
export function nextClaimant(current: number, total: number): number | null {
  return current + 1 < total ? current + 1 : null;
}

/** Immutably toggle a word in one player's picks. */
export function togglePick(picks: string[], word: string): string[] {
  return picks.includes(word)
    ? picks.filter((w) => w !== word)
    : [...picks, word];
}

/**
 * Fill in blank names.
 *
 * Two blank fields must not produce two players called the same thing —
 * the networked mode already learned that lesson the hard way.
 */
export function resolveNames(raw: string[]): string[] {
  return raw.map((name, i) => name.trim() || `Spieler ${i + 1}`);
}

/** Names are the identity in this mode, so they have to be distinct. */
export function uniqueNames(names: string[]): string[] {
  const seen = new Map<string, number>();
  return names.map((name) => {
    const count = seen.get(name) ?? 0;
    seen.set(name, count + 1);
    return count === 0 ? name : `${name} ${count + 1}`;
  });
}
