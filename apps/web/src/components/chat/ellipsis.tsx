const DELAYS = ["0ms", "150ms", "300ms"];

/** Three staggered bouncing dots: a reply is on its way but has no text yet. */
export function Ellipsis() {
  return (
    // <output> carries the implicit "status" role.
    <output
      aria-label="Generating"
      className="flex items-center gap-1 text-muted-foreground"
    >
      {DELAYS.map((delay) => (
        <span
          key={delay}
          className="size-1.5 rounded-full bg-current motion-safe:animate-bounce"
          style={{ animationDelay: delay }}
        />
      ))}
    </output>
  );
}
