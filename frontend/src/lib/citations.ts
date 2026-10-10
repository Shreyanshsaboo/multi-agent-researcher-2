/** Evidence citations like [E3] in a report; a following "(" means it is already a link. */
export const CITATION = /\[(E\d+)\](?!\()/g;

/** Evidence ids in order of first citation, so sources can be numbered 1, 2, 3 for readers. */
export function citationOrder(markdown: string): string[] {
  return [...new Set([...markdown.matchAll(CITATION)].map((m) => m[1]))];
}
