# Code mode: audit a screen from its source

Use it when there is no device. It finds less than a capture: nothing about what TalkBack says, where
focus goes or what happens after a tap. Every finding is marked *from code, not verified on device*.

## 1. With a preview of the screen

If the screen has a `@Preview` and the `android` CLI is installed (`android --version`), let the rules
read the semantics Compose really builds:

```bash
android preview list <module>                 # the previews, by fully qualified name
android preview render <module> --component-tree --output <folder> --fqn <preview>
a11y-audit preview <folder>
```

It writes `audits/<date>/<preview>-preview/` with `findings.json`, the rendered image and
`report-draft.md`. Each finding names its file and line. Then follow
[capture.md](capture.md) from step 3 on that folder, keeping in mind:

| The preview | So |
|---|---|
| has no speech and no focus | the draft marks what needs a walk as *Not tested* |
| shows layout sizes, not touch targets | no target size is reported: a `clickable` gets a 48dp minimum touch target, and that is the size accessibility services see (on a device, a 20dp `clickable` Box is a 48x48dp node) |
| shows one state | a tab that is never selected in the preview can't show whether its state is exposed: read the code for it |
| names the line of the composable that sets the semantics | a line in a library file means the control comes from a library component: find its call in the screen |

`android preview render` fails or shows a grey image: the module lacks `ui-tooling`, or the preview
needs something it can't have (an Activity, a ViewModel). Go on with step 2 only.

## 2. Reading the code

Do it always: after the preview for what it can't show, or alone when there is no preview.

Find the screen's composables (or layouts) from the name the user gives, and follow the components
they use, into the design system when the semantics are set there.

**What changes while the screen is used.** No preview shows it, so answer each question from the
code, and write the answer in the report even when it is "nothing found":

| Question | Look for | A problem when |
|---|---|---|
| What can be selected, checked or expanded? | state that only changes a colour or an icon | the state isn't in `selected`, `toggleable` or `stateDescription` (4.1.2, 1.4.1) |
| What text arrives or changes on its own? | a list that grows, a result count, an error, a loading text, a reply | it has no `liveRegion` and focus isn't moved to it (4.1.3) |
| What disappears after an action? | an element removed from the composition by its own tap: a chip, a banner, an option | nothing says where focus goes next (2.4.3). Mark it *to confirm on a device* |
| What opens? | a dialog, a sheet, a menu | it has no title (`paneTitle`, a dialog title) or focus isn't sent into it (2.4.2, 2.4.3) |

**Each control.** When there was no preview, also read for every control:
- its name (`contentDescription`, text, `semantics`);
- its role (`Role`, `clickable(role = …)`, the component used);
- merging (`mergeDescendants`, `clearAndSetSemantics`), headings and `paneTitle`.

**Colours and sizes.**
- Hard-coded colour pairs the preview didn't measure: work out the contrast and report it below 4.5:1.
- Don't report a target size from a `size(…)` below 48dp on a `clickable`: its touch target is 48dp
  all the same. Leave 2.5.8 *Not tested*, and report it only when the code turns that off (`minimumInteractiveComponentSize` disabled, a custom
  pointer input).

Mark each finding *from code, not verified on device*, with `path:line`. Name the capture that would
confirm it: `a11y-audit audit <screen> --activate "<element>"`.

## The report

The format is the one in [capture.md](capture.md). In the conformance table, contrast you didn't work
out, focus visibility, focus order and anything that depends on runtime state are *Not tested*.
