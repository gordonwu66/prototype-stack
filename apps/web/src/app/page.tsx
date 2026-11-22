import type { Metadata } from "next";
import { FadeIn } from "@/components/landing/fade-in";
import { Footer } from "@/components/landing/footer";
import { Hero } from "@/components/landing/hero";
import { Navbar } from "@/components/landing/navbar";
import { Solutions } from "@/components/landing/solutions";

export const metadata: Metadata = {
  title: "Subterranean - AI Agent Teams on Autopilot",
  description:
    "Subterranean is the home for AI that runs businesses. Set up specialist agent teams, shared workspaces, memory, data, and workflows with little to no setup.",
};

export default function Home() {
  return (
    <div className="relative flex min-h-dvh flex-col overflow-x-clip bg-background">
      {/* Gutter matches the hero's so the bare (unscrolled) navbar lines up with
          the headline and the stage frame below it. */}
      <div className="fixed inset-x-0 top-0 z-50 mx-auto mt-4 px-6 lg:px-10">
        <Navbar />
      </div>

      <Hero />

      <div className="mx-auto w-full max-w-7xl px-4 pt-24 pb-16 sm:pt-32">
        <FadeIn>
          <Solutions />
        </FadeIn>
      </div>

      <div className="mt-auto pt-20">
        <FadeIn>
          <Footer />
        </FadeIn>
      </div>
    </div>
  );
}
