# Seeded defects of the sample screen

`:sample` (`io.github.asanre.a11ylogger.sample`) is a support chat with known accessibility defects.
It is the answer key for the tool's rules and for measuring how well an agent audits with the skills.
The source carries no hint of them on purpose: don't add comments that name them.

| # | Defect | Where | WCAG | Expected evidence |
|---|---|---|---|---|
| 1 | The screen title is not a heading | "Soporte" | 1.3.1 | `NO_HEADING` |
| 2 | Low contrast text | "Horario de atención: de 9 a 18 h" (#BDBDBD on #F5F5F5) | 1.4.3 | `TEXT_CONTRAST` or `ATF:TextContrastCheck` |
| 3 | The active filter is shown by colour only, not as a state | "Todos" / "Sin leer" | 1.4.1, 4.1.2 | judgement: no `selected` in the tree or the speech |
| 4 | A clickable text with no role | "Ver mis pedidos" | 4.1.2 | `NO_ROLE` |
| 5 | The options vanish 1.5 s after one is chosen and focus jumps to the message field | "Envío", "Devolución", "Factura" | 2.4.3 | focus after `press activate` |
| 6 | The reply that arrives is not announced | "Gracias. Un agente revisará…" | 4.1.3 | `appeared` |
| 7 | The field's only label is its placeholder | "Escribe un mensaje" | 3.3.2 | judgement, or `EDIT_NO_HINT` |
| 8 | The send button has no name and no role | blue circle next to the field | 1.1.1, 4.1.2 | `NO_LABEL`, `NO_ROLE` |

A trap for audits from code: "Cerrar aviso" is drawn at 20dp, but `clickable` gives it a 48dp target on
the device, so it is not a 2.5.8 failure.

Not defects, but they stress the tool: 41 messages in a lazy list that scrolls as TalkBack moves, and
message 21, which is 5,200 characters long (one log record has to carry it).

```bash
./gradlew :sample:installDebug
adb shell am start -n io.github.asanre.a11ylogger.sample/.SupportActivity
```
