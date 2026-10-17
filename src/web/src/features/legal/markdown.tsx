// Markdown mínimo para la política de tratamiento (plan D12). Subconjunto admitido:
//   - encabezados `#`, `##`, `###` (al inicio de un bloque);
//   - citas `> …`, listas `- …` o `* …` y párrafos (líneas seguidas se unen);
//   - **negrita** dentro de una línea.
// Lo demás (enlaces, listas numeradas, tablas…) sale como texto literal. Todo se pinta
// como texto de React: nada del contenido puede inyectar HTML.
import type { ReactNode } from "react";

function inline(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={`${keyPrefix}-${index}`}>{part.slice(2, -2)}</strong>
    ) : (
      part
    ),
  );
}

type Block =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "quote"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "paragraph"; text: string };

export function parseMarkdown(source: string): Block[] {
  const blocks: Block[] = [];
  // Bloques separados por líneas en blanco; dentro, las líneas se unen.
  for (const chunk of source.replace(/\r\n/g, "\n").split(/\n\s*\n/)) {
    const lines = chunk.split("\n").map((line) => line.trim()).filter(Boolean);
    const first = lines[0];
    if (!first) continue;
    const heading = /^(#{1,3})\s+(.*)$/.exec(first);
    if (heading?.[1] && heading[2] !== undefined) {
      blocks.push({ kind: "heading", level: heading[1].length as 1 | 2 | 3, text: heading[2] });
      // Un encabezado seguido de texto sin línea en blanco: el resto es otro bloque.
      lines.shift();
      if (lines.length === 0) continue;
    }
    if (lines.every((line) => line.startsWith(">"))) {
      blocks.push({ kind: "quote", text: lines.map((line) => line.replace(/^>\s?/, "")).join(" ") });
    } else if (lines.every((line) => /^[-*]\s+/.test(line))) {
      blocks.push({ kind: "list", items: lines.map((line) => line.replace(/^[-*]\s+/, "")) });
    } else {
      blocks.push({ kind: "paragraph", text: lines.join(" ") });
    }
  }
  return blocks;
}

const HEADING_TAGS = { 1: "h2", 2: "h3", 3: "h4" } as const;

export function Markdown({ source }: { source: string }) {
  return (
    <>
      {parseMarkdown(source).map((block, index) => {
        const key = `b${index}`;
        switch (block.kind) {
          case "heading": {
            // El h1 de la página es el título; los de la política bajan un nivel.
            const Tag = HEADING_TAGS[block.level];
            return <Tag key={key}>{inline(block.text, key)}</Tag>;
          }
          case "quote":
            return <blockquote key={key}>{inline(block.text, key)}</blockquote>;
          case "list":
            return (
              <ul key={key}>
                {block.items.map((item, itemIndex) => (
                  <li key={`${key}-${itemIndex}`}>{inline(item, `${key}-${itemIndex}`)}</li>
                ))}
              </ul>
            );
          default:
            return <p key={key}>{inline(block.text, key)}</p>;
        }
      })}
    </>
  );
}
