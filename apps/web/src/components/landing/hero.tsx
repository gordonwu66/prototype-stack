import { Calendar, ChevronRight } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const VISUAL_DESCRIPTION =
  "Workspace showing an agent, task board, project files and tables, and code and UI results";

// Each hero row drops in from above, staggered by `delay`.
const enter =
  "animate-in fade-in slide-in-from-top-6 fill-mode-both duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] motion-reduce:animate-none";

const providers = [
  { src: "/claude_logo.svg", alt: "Claude", label: "Claude", size: 20 },
  // Solid black mark on transparent: invert it so it reads in dark mode.
  {
    src: "/openai_logo.svg",
    alt: "OpenAI",
    label: "GPT",
    size: 24,
    className: "-mx-0.5 dark:invert",
  },
  { src: "/deepseek_logo.svg", alt: "DeepSeek", label: "DeepSeek", size: 20 },
];

// Copy and CTAs lead, followed by an inset "stage": the photo is bounded inside
// a rounded frame, with the product screenshot floating on top of it.
export function Hero() {
  return (
    <div className="w-full pt-32 sm:pt-40">
      {/* Same container shape as the stage below (gutter outside the max-width)
          so the headline starts exactly on the frame's left edge. */}
      <div className="px-6 lg:px-10">
        <div className="mx-auto grid max-w-7xl grid-cols-1 items-center gap-8 lg:grid-cols-12 lg:gap-12">
          <div className="flex flex-col gap-5 lg:col-span-7">
            <h1
              className={`${enter} font-serif text-4xl leading-[1.08] tracking-tight text-foreground delay-150 duration-600 sm:text-5xl lg:text-6xl`}
            >
              Ship your fleet of agents with full control
            </h1>
            <p
              className={`${enter} max-w-lg text-lg text-muted-foreground delay-300`}
            >
              The managed agent ops layer where you own the intelligence
            </p>
          </div>

          {/* On desktop the CTA row sets the column's width, so both rows share a
              left edge while the buttons meet the stage's right edge. */}
          <div className="flex flex-col gap-6 lg:col-span-5 lg:ml-auto lg:w-fit">
            <div className={`${enter} flex items-center gap-3 delay-[420ms]`}>
              <Link
                href="/chat"
                className="group inline-flex items-center justify-center gap-1.5 rounded-lg bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
              >
                Get Started
                <ChevronRight className="-mr-1.5 size-4 transition-transform duration-200 ease-out group-hover:translate-x-1" />
              </Link>
              <Link
                href="#"
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border bg-background px-6 py-2.5 text-sm font-semibold text-foreground transition-colors hover:bg-secondary"
              >
                <Calendar className="-ml-0.5 size-4" />
                Book Demo
              </Link>
            </div>

            <div
              className={`${enter} flex items-center gap-3.5 text-foreground delay-[540ms]`}
            >
              <span className="text-sm font-semibold tracking-wide">
                Works with
              </span>
              <div className="flex items-center gap-3.5">
                {providers.map((p) => (
                  <Tooltip key={p.label}>
                    <TooltipTrigger asChild>
                      <Image
                        src={p.src}
                        alt={p.alt}
                        width={p.size}
                        height={p.size}
                        className={`shrink-0 object-cover object-center ${p.className ?? ""}`}
                        style={{ width: p.size, height: p.size }}
                      />
                    </TooltipTrigger>
                    <TooltipContent side="bottom">{p.label}</TooltipContent>
                  </Tooltip>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-12 animate-in px-6 fade-in slide-in-from-bottom-8 fill-mode-both delay-700 duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] motion-reduce:animate-none sm:mt-16 lg:px-10">
        <div className="relative isolate mx-auto max-w-7xl overflow-hidden rounded-xl sm:rounded-2xl">
          <Image
            src="/landscapes/volcanic-highland.jpg"
            alt=""
            fill
            priority
            sizes="(min-width: 80rem) 80rem, 100vw"
            className="absolute inset-0 z-0 object-cover object-center"
          />
          {/* Dark mode knocks the daylight photo down so it doesn't glare
              against a dark page. */}
          <div className="absolute inset-0 z-0 dark:bg-background/25" />

          {/* Horizontal inset stays wide; vertical is trimmed so the photo reads
              as a band rather than an even border around the screenshot. */}
          <div className="relative z-10 px-4 py-3 sm:px-14 sm:py-11 lg:px-24 lg:py-20">
            <div className="overflow-hidden rounded-lg shadow-2xl ring-1 ring-black/10 sm:rounded-xl">
              <Image
                src="/marketing_light.png"
                alt={VISUAL_DESCRIPTION}
                width={1200}
                height={675}
                priority
                className="block h-auto w-full dark:hidden"
              />
              <Image
                src="/marketing_dark.png"
                alt={VISUAL_DESCRIPTION}
                width={1200}
                height={675}
                priority
                className="hidden h-auto w-full dark:block"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
