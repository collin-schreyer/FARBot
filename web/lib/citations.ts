import { marked } from "marked";

export function acquisitionGovUrl(section: string): string {
  return `https://www.acquisition.gov/far/${section.trim()}`;
}

export type Source = { section: string; title: string; url: string };

const CITE = /\b(?:FAR\s+)?(\d{1,2}\.\d{2,4}(?:-\d+)?)\b/g;

marked.setOptions({ gfm: true, breaks: true });

// Linkify FAR section numbers in text only — never inside HTML tags/attributes.
function linkifyFar(html: string): string {
  return html
    .split(/(<[^>]+>)/)
    .map((seg, i) =>
      i % 2 === 1
        ? seg
        : seg.replace(
            CITE,
            (m, sec: string) =>
              `<a class="usa-link" target="_blank" rel="noreferrer" href="${acquisitionGovUrl(sec)}">${m}</a>`,
          ),
    )
    .join("");
}

// Full markdown -> HTML (lists, headings, bold, paragraphs) with FAR citations linked.
// Safe to call on partial text during streaming.
export function renderAnswerHtml(text: string): string {
  if (!text) return "";
  const html = marked.parse(text, { async: false }) as string;
  return linkifyFar(html);
}
