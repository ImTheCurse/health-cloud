import { useState } from "react";

/** Which legend entries are switched off, and a toggle for one. */
export function useHidden(initial = []) {
  const [hidden, setHidden] = useState(() => new Set(initial));
  const toggle = (id) =>
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  return [hidden, toggle];
}
