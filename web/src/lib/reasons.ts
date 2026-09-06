/** Rejection reasons from the server, in the language the players speak. */
const TEXT: Record<string, string> = {
  too_short: "zu kurz",
  not_a_substring: "nicht im Wort enthalten",
  not_in_dictionary: "kein bekanntes Wort",
  is_source_word: "das ist das Rätselwort",
  malformed: "nur Buchstaben",
  duplicate: "schon gefunden",
  too_late: "zu spät",
};

export function reasonText(reason: string | null): string {
  if (!reason) return "abgelehnt";
  return TEXT[reason] ?? reason;
}
