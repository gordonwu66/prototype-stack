"use client";

import { ChevronRight, Loader2 } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/** A sidebar row; the active one is the page that's open. */
export const rowClass = (active: boolean) =>
  cn(
    "group flex h-8 items-center rounded-md text-sm",
    active
      ? "bg-sidebar-accent text-sidebar-accent-foreground"
      : "hover:bg-sidebar-accent/60",
  );

/** The label of a row: a link or button that fills the space left of the actions. */
export const rowLabel = "min-w-0 flex-1 truncate px-2 py-1.5 text-left";

/** Chevron that opens and closes a branch of the tree. */
export function Toggle({
  open,
  label,
  onClick,
}: {
  open: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <Button
      variant="ghost"
      size="icon-xs"
      aria-expanded={open}
      aria-label={`${open ? "Collapse" : "Expand"} ${label}`}
      onClick={onClick}
      className="ml-1 text-muted-foreground hover:bg-transparent dark:hover:bg-transparent"
    >
      <ChevronRight
        className={cn("transition-transform", open && "rotate-90")}
      />
    </Button>
  );
}

/**
 * Heading of a top-level section: a small muted label with its chevron at the
 * far right, and no background. Without `href` the whole heading toggles;
 * with one the label links there and only the chevron toggles.
 */
export function SectionHeader({
  label,
  open,
  onToggle,
  href,
  active = false,
  actions,
}: {
  label: string;
  open: boolean;
  onToggle: () => void;
  href?: string;
  active?: boolean;
  /** Shown on hover, left of the chevron. */
  actions?: ReactNode;
}) {
  const chevron = (
    <ChevronRight
      className={cn(
        "size-3.5 shrink-0 transition-transform",
        open && "rotate-90",
      )}
    />
  );
  const toggleProps = {
    type: "button" as const,
    "aria-expanded": open,
    onClick: onToggle,
  };

  return (
    <div
      className={cn(
        "group flex h-7 items-center text-xs font-medium transition-colors",
        active
          ? "text-sidebar-foreground"
          : "text-muted-foreground hover:text-[color-mix(in_oklch,var(--muted-foreground),var(--sidebar-foreground)_40%)]",
      )}
    >
      {href ? (
        <>
          <Link href={href} className="min-w-0 flex-1 truncate px-2 py-1">
            {label}
          </Link>
          {actions && <RowActions>{actions}</RowActions>}
          <button
            {...toggleProps}
            aria-label={`${open ? "Collapse" : "Expand"} ${label}`}
            className="mr-1 flex size-6 items-center justify-center"
          >
            {chevron}
          </button>
        </>
      ) : (
        <button
          {...toggleProps}
          className="flex min-w-0 flex-1 items-center gap-2 py-1 pr-2.5 pl-2 text-left"
        >
          <span className="min-w-0 flex-1 truncate">{label}</span>
          {chevron}
        </button>
      )}
    </div>
  );
}

/** Children of a row, indented under a guide line that starts below its chevron. */
export function Branch({ children }: { children: ReactNode }) {
  return (
    <div className="ml-4 flex flex-col gap-0.5 border-l border-sidebar-border py-0.5 pl-1.5">
      {children}
    </div>
  );
}

/** Hover actions at the right end of a row. */
export function RowActions({ children }: { children: ReactNode }) {
  return (
    <div className="hidden shrink-0 pr-1 group-focus-within:flex group-hover:flex">
      {children}
    </div>
  );
}

export function RowAction({
  label,
  onClick,
  className,
  children,
}: {
  label: string;
  onClick: () => void;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label={label}
          onClick={onClick}
          className={cn(
            "text-muted-foreground hover:bg-transparent dark:hover:bg-transparent",
            className,
          )}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

/** One-line edit box in place of a row: Enter or blur commits, Escape cancels. */
export function InlineInput({
  label,
  defaultValue = "",
  placeholder,
  onDone,
}: {
  label: string;
  defaultValue?: string;
  placeholder?: string;
  /** The trimmed text, or null when cancelled or left empty. */
  onDone: (value: string | null) => void;
}) {
  return (
    <Input
      aria-label={label}
      autoFocus
      defaultValue={defaultValue}
      placeholder={placeholder}
      className="h-8 bg-background focus-visible:ring-0"
      onBlur={(e) => onDone(e.currentTarget.value.trim() || null)}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") {
          // Clear first so the blur that follows reads as a cancel.
          e.currentTarget.value = "";
          e.currentTarget.blur();
        }
      }}
    />
  );
}

export function EmptyRow({ children }: { children: ReactNode }) {
  return (
    <p className="px-2 py-1.5 text-xs text-muted-foreground">{children}</p>
  );
}

/** Stands in for a list's rows until its first load finishes. */
export function LoadingRow({ label }: { label: string }) {
  return (
    <output aria-label={label} className="flex h-8 items-center px-2">
      <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
    </output>
  );
}
