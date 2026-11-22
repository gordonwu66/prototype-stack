"use client";

import { Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useSessions, useStoredState } from "@/components/chat/use-chat";
import { type ChatSession, deleteSession, renameSession } from "@/lib/chat";
import {
  EmptyRow,
  InlineInput,
  LoadingRow,
  RowAction,
  RowActions,
  rowClass,
  rowLabel,
  SectionHeader,
} from "./rows";

export function SessionsSection({ pathname }: { pathname: string }) {
  const { sessions, loaded, error } = useSessions();
  const [state, setState] = useStoredState<"open" | "closed">(
    "sidebar:sessions",
    "open",
  );
  const open = state === "open";
  const toggle = () => setState(open ? "closed" : "open");
  const activeId = pathname.startsWith("/chat/")
    ? pathname.slice("/chat/".length)
    : null;

  return (
    <section aria-label="Sessions">
      <SectionHeader label="Sessions" open={open} onToggle={toggle} />
      {open && (
        <div className="flex flex-col gap-0.5">
          {error && <p className="px-2 text-sm text-destructive">{error}</p>}
          {!loaded && <LoadingRow label="Loading sessions" />}
          {loaded && !error && sessions.length === 0 && (
            <EmptyRow>No sessions yet</EmptyRow>
          )}
          {sessions.map((s) => (
            <SessionItem key={s.id} session={s} active={s.id === activeId} />
          ))}
        </div>
      )}
    </section>
  );
}

function SessionItem({
  session,
  active,
}: {
  session: ChatSession;
  active: boolean;
}) {
  const [editing, setEditing] = useState(false);

  // The list updates from session:upserted / session:deleted, so no local state
  // changes here besides the edit box.
  async function rename(title: string | null) {
    setEditing(false);
    if (title && title !== session.title)
      await renameSession(session.id, title);
  }

  async function remove() {
    if (confirm(`Delete "${session.title}"?`)) await deleteSession(session.id);
  }

  if (editing) {
    return (
      <InlineInput
        label="Chat title"
        defaultValue={session.title}
        onDone={rename}
      />
    );
  }

  return (
    <div className={rowClass(active)}>
      <Link
        href={`/chat/${session.id}`}
        className={rowLabel}
        title={session.title}
      >
        {session.title}
      </Link>
      <RowActions>
        <RowAction label="Rename" onClick={() => setEditing(true)}>
          <Pencil />
        </RowAction>
        <RowAction
          label="Delete"
          onClick={remove}
          className="hover:text-destructive"
        >
          <Trash2 />
        </RowAction>
      </RowActions>
    </div>
  );
}
