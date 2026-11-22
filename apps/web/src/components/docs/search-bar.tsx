"use client";

import { Search, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { SearchMode } from "@/lib/search";
import { MODES, useSearchQuery } from "./use-search";

// The chat composer's toolbar select, so both read as the same control.
const toolbarTrigger =
  "border-transparent bg-transparent px-2 text-xs text-muted-foreground shadow-none hover:bg-muted hover:text-foreground dark:bg-transparent dark:hover:bg-muted";

/**
 * One line, styled like the chat composer. Enter searches; each search embeds
 * the query, so nothing runs while typing. Escape clears.
 */
export function SearchBar({ scope }: { scope?: string }) {
  const { q, mode, setQuery } = useSearchQuery();
  const [draft, setDraft] = useState(q);
  // Follow the URL when it changes underneath us (Back, Clear, a link).
  const [synced, setSynced] = useState(q);
  if (q !== synced) {
    setSynced(q);
    setDraft(q);
  }

  const clear = () => {
    setDraft("");
    if (q) setQuery({ q: "", mode });
  };

  return (
    <search>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setQuery({ q: draft.trim(), mode });
        }}
        className="flex h-11 items-center gap-1 rounded-xl border border-input bg-card pr-1.5 pl-3.5 shadow-xs transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50"
      >
        <Search className="size-4 shrink-0 text-muted-foreground" />
        <input
          aria-label="Search documents"
          placeholder={scope ? `Search ${scope}…` : "Search all documents…"}
          enterKeyHint="search"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") clear();
          }}
          className="h-full min-w-0 flex-1 bg-transparent px-1.5 text-sm outline-none placeholder:text-muted-foreground"
        />
        {(draft || q) && (
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label="Clear search"
            onClick={clear}
            className="text-muted-foreground"
          >
            <X />
          </Button>
        )}
        <Select
          value={mode}
          onValueChange={(value) =>
            setQuery({ q: draft.trim(), mode: value as SearchMode })
          }
        >
          <SelectTrigger
            size="sm"
            aria-label="Search mode"
            className={toolbarTrigger}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent position="popper" align="end">
            <SelectGroup className="p-1.5">
              <SelectLabel className="px-2.5 py-1.5">Search mode</SelectLabel>
              {MODES.map((m) => (
                <SelectItem
                  key={m.value}
                  value={m.value}
                  className="py-1.5 pl-2.5"
                >
                  {m.label}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      </form>
    </search>
  );
}
