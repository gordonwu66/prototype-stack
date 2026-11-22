import Link from "next/link";

const link =
  "text-sm text-muted-foreground transition-colors duration-300 hover:text-primary";

export function Footer() {
  return (
    // Narrow screens stack everything flush left on the same 24px gutter as the
    // hero and sections; from md up the label centers with links pinned right.
    <footer className="relative w-full px-6 py-6 md:px-4">
      <div className="flex flex-col items-start gap-2 md:block">
        <p className="text-sm text-muted-foreground md:text-center">
          Built with ❤️ in NYC
        </p>
        <div className="flex items-center gap-4 md:absolute md:top-1/2 md:right-4 md:-translate-y-1/2">
          <Link href="#" className={link}>
            Privacy Policy
          </Link>
          <a href="mailto:hi@subterranean.io" className={link}>
            hi@subterranean.io
          </a>
        </div>
      </div>
    </footer>
  );
}
