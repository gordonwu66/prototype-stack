"use client";

import { cn } from "cn";
import { ChevronDown, Menu } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ThemeSelector } from "@/components/theme-selector";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { solutions } from "./solutions";

const SCROLL_THRESHOLD = 24;

// Docs and Blog aren't built yet; they stay in the bar as placeholders.
const LINKS = [
  { href: "#", label: "Docs" },
  { href: "#", label: "Blog" },
  { href: "/chat", label: "Login" },
];

const desktopLink =
  "text-sm text-primary transition-colors duration-300 hover:text-muted-foreground dark:text-muted-foreground dark:hover:text-primary";
const mobileLink =
  "text-lg text-muted-foreground transition-colors duration-300 hover:text-primary";

// The bar starts at content width with no pill behind it, and collapses into a
// compact pill once the page is scrolled.
export function Navbar() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const read = () => setScrolled(window.scrollY > SCROLL_THRESHOLD);
    read();
    window.addEventListener("scroll", read, { passive: true });
    return () => window.removeEventListener("scroll", read);
  }, []);

  return (
    <div
      className={cn(
        "mx-auto w-full transition-[max-width] duration-300 ease-out",
        scrolled ? "max-w-3xl" : "max-w-7xl",
      )}
    >
      <div className="relative">
        {/* Pill chrome sits on its own layer so it can fade out at the top of the
            page, blur included (backdrop-filter doesn't transition on its own). */}
        <div
          aria-hidden
          className={cn(
            "pointer-events-none absolute inset-0 rounded-lg bg-secondary/50 shadow-sm backdrop-blur-sm transition-opacity duration-300 ease-out",
            scrolled ? "opacity-100" : "opacity-0",
          )}
        />
        {/* The bare state drops horizontal padding so the logo sits flush with
            the page gutter; the pill takes it back when it fades in. */}
        <nav
          className={cn(
            "relative flex items-center justify-between py-2 transition-[padding] duration-300 ease-out",
            scrolled ? "px-4" : "px-0",
          )}
        >
          <Link href="/" className="flex items-center gap-1">
            <Image
              src="/logo.svg"
              alt="Subterranean logo"
              // Matches the SVG's 7:6 box, so CSS doesn't stretch one side.
              width={35}
              height={30}
              className="pb-0.5"
            />
            <span className="font-serif text-lg font-medium text-primary">
              Subterranean.
            </span>
          </Link>

          <div className="hidden items-center gap-4 md:flex">
            <DropdownMenu>
              <DropdownMenuTrigger
                className={cn(
                  desktopLink,
                  "flex cursor-pointer items-center gap-1 outline-none",
                )}
              >
                Solutions
                <ChevronDown className="size-3.5" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-72">
                {solutions.map((s) => (
                  <DropdownMenuItem
                    key={s.slug}
                    asChild
                    className="cursor-pointer"
                  >
                    <a
                      href={s.href}
                      className="flex flex-col items-start gap-0.5 py-2"
                    >
                      <span className="text-sm font-medium text-foreground">
                        {s.name}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {s.headline}
                      </span>
                    </a>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            {LINKS.map((l) => (
              <Link key={l.label} href={l.href} className={desktopLink}>
                {l.label}
              </Link>
            ))}
            <ThemeSelector className="-ml-2" />
          </div>

          <Sheet>
            <SheetTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="md:hidden"
                aria-label="Open menu"
              >
                <Menu className="size-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="right">
              <SheetTitle className="sr-only">Menu</SheetTitle>
              <div className="flex flex-col gap-6 p-6">
                <div className="flex flex-col gap-3">
                  <span className="text-xs font-medium tracking-wider text-muted-foreground/60 uppercase">
                    Solutions
                  </span>
                  {solutions.map((s) => (
                    <SheetClose asChild key={s.slug}>
                      <a href={s.href} className={mobileLink}>
                        {s.name}
                      </a>
                    </SheetClose>
                  ))}
                </div>
                {LINKS.map((l) => (
                  <SheetClose asChild key={l.label}>
                    <Link href={l.href} className={mobileLink}>
                      {l.label}
                    </Link>
                  </SheetClose>
                ))}
                <div className="border-t pt-4">
                  <ThemeSelector className="-ml-2" />
                </div>
              </div>
            </SheetContent>
          </Sheet>
        </nav>
      </div>
    </div>
  );
}
