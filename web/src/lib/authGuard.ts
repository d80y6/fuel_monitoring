export function isAuthed(token: string | null | undefined): boolean {
  return Boolean(token && token.length > 0);
}