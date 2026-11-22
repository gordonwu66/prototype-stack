import { Suspense } from "react";
import { CollectionPage } from "@/components/docs/collection-page";

export default function Page({ params }: PageProps<"/docs/[collectionId]">) {
  // Ids and the search query are runtime values, so read them inside Suspense.
  return (
    <Suspense>
      {params.then(({ collectionId }) => (
        <CollectionPage key={collectionId} collectionId={collectionId} />
      ))}
    </Suspense>
  );
}
