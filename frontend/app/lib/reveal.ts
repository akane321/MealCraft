// A new assistant reply shows word by word (Chinese character by character), over at most REVEAL_MAX_MS.
export const REVEAL_MAX_MS = 1500;
const STEP_MS = 45;

/** The reply split into words and the spaces between them, so the joined pieces are the reply unchanged. */
export function revealTokens(text: string): string[] {
  return text.match(/[㐀-鿿豈-﫿]|[^\s㐀-鿿豈-﫿]+|\s+/g) ?? [];
}

/** The pause between two words, so the whole reply is out within REVEAL_MAX_MS. */
export function revealStep(text: string): number {
  const words = revealTokens(text).filter(token => token.trim()).length;
  return words > 1 ? Math.min(STEP_MS, REVEAL_MAX_MS / words) : 0;
}

/** How long the reveal of `text` takes: its last word starts then, and fades in over a further 200 ms (within the cap). */
export function revealDuration(text: string): number {
  const words = revealTokens(text).filter(token => token.trim()).length;
  return Math.min(REVEAL_MAX_MS, Math.max(0, words - 1) * revealStep(text) + 200);
}
