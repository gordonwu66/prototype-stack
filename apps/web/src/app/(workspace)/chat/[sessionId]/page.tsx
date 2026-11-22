import { Suspense } from "react";
import { Chat } from "@/components/chat/chat";

export default function ChatPage({ params }: PageProps<"/chat/[sessionId]">) {
  // Session ids are runtime params, so read them inside Suspense.
  return (
    <Suspense>
      {params.then(({ sessionId }) => (
        <Chat key={sessionId} sessionId={sessionId} />
      ))}
    </Suspense>
  );
}
