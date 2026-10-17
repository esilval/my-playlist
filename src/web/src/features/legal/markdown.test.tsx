import { describe, expect, it } from "vitest";

import { parseMarkdown } from "./markdown";

describe("markdown de la política", () => {
  it("reconoce encabezados, citas, listas y párrafos", () => {
    const source = "# Título\n\n## Sección\n\n> Una\n> cita\n\n- uno\n* dos\n\nLínea uno\nlínea dos";

    expect(parseMarkdown(source)).toEqual([
      { kind: "heading", level: 1, text: "Título" },
      { kind: "heading", level: 2, text: "Sección" },
      { kind: "quote", text: "Una cita" },
      { kind: "list", items: ["uno", "dos"] },
      { kind: "paragraph", text: "Línea uno línea dos" },
    ]);
  });

  it("un encabezado seguido de texto sin línea en blanco no se pierde", () => {
    expect(parseMarkdown("# Responsable\nMyPlaylist S.A.S.\nBogotá")).toEqual([
      { kind: "heading", level: 1, text: "Responsable" },
      { kind: "paragraph", text: "MyPlaylist S.A.S. Bogotá" },
    ]);
  });

  it("lo que no admite queda como texto literal", () => {
    expect(parseMarkdown("1. Primero\n\n[enlace](https://ejemplo.com)\n\n#### Muy hondo")).toEqual([
      { kind: "paragraph", text: "1. Primero" },
      { kind: "paragraph", text: "[enlace](https://ejemplo.com)" },
      { kind: "paragraph", text: "#### Muy hondo" },
    ]);
  });

  it("acepta saltos de línea de Windows y bloques vacíos", () => {
    expect(parseMarkdown("Uno\r\n\r\n\r\n\r\nDos")).toEqual([
      { kind: "paragraph", text: "Uno" },
      { kind: "paragraph", text: "Dos" },
    ]);
  });
});
