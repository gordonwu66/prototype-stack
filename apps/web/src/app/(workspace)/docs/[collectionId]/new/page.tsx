import { Suspense } from "react";
import { NewDocumentPage } from "@/components/docs/document-page";

export default function Page({
  params,
}: PageProps<"/docs/[collectionId]/new">) {
  return (
    <Suspense>
      {params.then(({ collectionId }) => (
        <NewDocumentPage key={collectionId} collectionId={collectionId} />
      ))}
    </Suspense>
  );
}
