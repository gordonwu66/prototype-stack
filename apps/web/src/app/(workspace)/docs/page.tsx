import { Suspense } from "react";
import { DocsHome } from "@/components/docs/docs-home";

export default function DocsPage() {
  // The search query is read from the URL, so render inside Suspense.
  return (
    <Suspense>
      <DocsHome />
    </Suspense>
  );
}
