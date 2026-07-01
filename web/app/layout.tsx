import type { Metadata } from "next";
import "./globals.css";
import GovBanner from "@/components/GovBanner";
import SiteHeader from "@/components/SiteHeader";
import SiteFooter from "@/components/SiteFooter";

export const metadata: Metadata = {
  title: "FAR Assistant · Acquisition.gov",
  description:
    "AI assistant over the Federal Acquisition Regulation — grounded answers with citations that link to the official FAR sections.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/npm/@uswds/uswds@3.8.1/dist/css/uswds.min.css"
        />
        <a className="usa-skipnav" href="#main-content">
          Skip to main content
        </a>
        <GovBanner />
        <SiteHeader />
        <main id="main-content" className="far-main">
          {children}
        </main>
        <SiteFooter />
      </body>
    </html>
  );
}
