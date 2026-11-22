import { Suspense } from "react";
import { ChatSocketProvider } from "@/components/chat/socket-provider";
import { DocsProvider } from "@/components/docs/docs-provider";
import { Sidebar, SidebarFallback } from "@/components/sidebar/sidebar";

// The sidebar, the single Socket.IO connection and the document lists live
// here, so the landing page at `/` opens no socket and loads no documents.
export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ChatSocketProvider>
      <DocsProvider>
        <div className="flex h-dvh overflow-hidden">
          {/* usePathname suspends on dynamic routes during prerendering. */}
          <Suspense fallback={<SidebarFallback />}>
            <Sidebar />
          </Suspense>
          <main className="flex min-w-0 flex-1 flex-col">{children}</main>
        </div>
      </DocsProvider>
    </ChatSocketProvider>
  );
}
