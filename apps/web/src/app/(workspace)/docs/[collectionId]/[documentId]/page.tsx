import { Suspense } from "react";
import { DocumentPage } from "@/components/docs/document-page";

export default function Page({
  params,
}: PageProps<"/docs/[collectionId]/[documentId]">) {
  return (
    <Suspense>
      {params.then(({ collectionId, documentId }) => (
        <DocumentPage
          key={documentId}
          collectionId={collectionId}
          documentId={documentId}
        />
      ))}
    </Suspense>
  );
}
