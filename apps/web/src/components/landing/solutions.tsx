import { ArrowUpRight } from "lucide-react";
import Link from "next/link";

// Solution pages aren't built yet, so every solution points back at this
// section. Swap in real paths (e.g. `/solutions/${slug}`) once they exist.
const PLACEHOLDER_HREF = "#solutions";

export const solutions = [
  {
    slug: "company-brain",
    href: PLACEHOLDER_HREF,
    name: "Company Brain",
    headline: "One place that knows everything your company knows",
  },
  {
    slug: "self-evolving-team",
    href: PLACEHOLDER_HREF,
    name: "Self-Evolving Agent Team",
    headline: "The AI team that builds and improves itself",
  },
  {
    slug: "crm",
    href: PLACEHOLDER_HREF,
    name: "AI-Native CRM",
    headline: "A CRM you talk to instead of fill in",
  },
  {
    slug: "support",
    href: PLACEHOLDER_HREF,
    name: "Support Triage",
    headline: "Tickets arrive triaged, not stacked",
  },
];

export function Solutions() {
  return (
    <section
      id="solutions"
      aria-labelledby="solutions-heading"
      className="scroll-mt-28 px-2 sm:px-4"
    >
      <div className="mb-6 max-w-2xl">
        <h2
          id="solutions-heading"
          className="mt-2 text-3xl tracking-tight text-foreground sm:text-4xl"
        >
          Start with proven systems
        </h2>
        <p className="mt-3 text-base leading-relaxed text-muted-foreground">
          Choose the outcome you need, then inspect the complete team behind it.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border lg:grid-cols-4">
        {solutions.map((solution) => (
          <Link
            key={solution.slug}
            href={solution.href}
            aria-label={`Explore ${solution.name}`}
            className="group flex min-h-44 flex-col bg-background p-4 transition-colors hover:bg-secondary/45 focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset active:bg-secondary/70 sm:min-h-48 sm:p-5"
          >
            <div className="flex items-start justify-between gap-3">
              <h3 className="text-sm font-semibold leading-snug text-foreground sm:text-base">
                {solution.name}
              </h3>
              <ArrowUpRight className="size-4 shrink-0 text-muted-foreground transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-foreground group-active:translate-x-1 group-active:-translate-y-1" />
            </div>
            <p className="mt-auto text-xs leading-relaxed text-muted-foreground sm:text-sm">
              {solution.headline}
            </p>
          </Link>
        ))}
      </div>
    </section>
  );
}
