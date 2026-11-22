"use client";

import { Plus, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeSelector } from "@/components/theme-selector";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { DocumentsSection } from "./documents";
import { SessionsSection } from "./sessions";

const frame =
  "flex w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground";

/** Top-of-sidebar actions: borderless, with the same hover as the tree rows. */
const navButton =
  "w-full justify-start rounded-md px-2 hover:bg-sidebar-accent/60 dark:hover:bg-sidebar-accent/60";

/** Placeholder with the same footprint, for the Suspense boundary in the layout. */
export function SidebarFallback() {
  return <aside className={frame} />;
}

/** Chat sessions and documents as two collapsible branches of one tree. */
export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className={frame}>
      <div className="flex flex-col gap-0.5 p-2">
        <Button asChild variant="ghost" className={navButton}>
          <Link href="/chat">
            <Plus />
            New Session
          </Link>
        </Button>
        {/* Placeholder: not wired up yet. */}
        <Button type="button" variant="ghost" className={navButton}>
          <Search />
          Search
        </Button>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <nav className="flex flex-col gap-2 px-2 pb-3">
          <SessionsSection pathname={pathname} />
          <DocumentsSection pathname={pathname} />
        </nav>
      </ScrollArea>
      <div className="border-t border-sidebar-border p-2">
        <ThemeSelector />
      </div>
    </aside>
  );
}
