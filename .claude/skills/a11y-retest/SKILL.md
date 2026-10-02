---
name: a11y-retest
description: Checks whether a reported accessibility issue on an Android screen is fixed, and gives a verdict with its evidence. Use when asked to retest, re-verify or confirm the fix of an accessibility issue, given the issue's text (pasted or in a file) and a capture folder, the app's source, or a connected device.
---

# Retest of an accessibility issue

The issue arrives as text in any format: an audit finding, a ticket pasted by the user, a file. No issue
tracker is read or written. Use the evidence there is, best first:

1. **A capture** taken after the fix (`audits/<date>/<screen>/`). If there is none, check whether a device
   is connected (`adb devices`).
2. **A targeted capture.** With a device, ask the user for one and tell them exactly what to do:
   - the command, `python3 tools/audit.py capture <screen>`, or `keyboard <screen>` for keyboard issues;
   - the screen and state to open;
   - the elements to swipe to, in order;
   - when to press Enter.
3. **The code**, when there is no device or the user doesn't want to capture. The verdict is then weaker.

## Steps

1. **Restate the issue** in one line:
   - the element;
   - what the user experienced;
   - the WCAG criterion, from the issue or from the `a11y-audit` skill's
     [reference](../a11y-audit/references/wcag-mobile.md);
   - what passes. For example: "the sort button is read as Sort, Button, and its expanded state is spoken".
2. **Collect the evidence.**
   - From a capture, run `python3 tools/audit.py rules <folder>` if `findings.json` is missing, then:
     - find the element in the timeline, the tree and the screenshot;
     - quote what TalkBack said;
     - check the findings on that element.
     Verify the findings as the `a11y-audit` skill says.
   - From the code, find the element (test tag, text, screen name). Compare its semantics with the pattern
     in the `compose-a11y` skill and give `path:line`.
3. **Check for regressions on the same element** with the same capture: a new finding, or a change that
   breaks a neighbour (a merged container that now hides a button, a new duplicate label).
4. **Give the verdict.**

## Verdict

| Verdict | When |
|---|---|
| **Fixed** | The pass condition holds and nothing new fails on the element |
| **Partially fixed** | Part of it holds (the name is right, the state still isn't spoken), or it holds in one place and not in another |
| **Not fixed** | The capture or the code shows the same problem |
| **Not verifiable** | The evidence doesn't reach it: the state wasn't visited, the element wasn't swiped to, or the code is dynamic |

Write the answer in the language the user asked in, with:

- the verdict, and the **evidence source**: *device capture* (folder) or *code only, not verified on
  device*;
- the evidence: the speech quoted exactly, the node fields or `path:line`;
- for anything other than Fixed, what is still wrong and the fix (`compose-a11y`);
- what is left to check: the capture that would confirm a code-only verdict, or the states not covered.

Never mark **Fixed** from code alone when the issue is about what TalkBack says, contrast or focus. Mark
it **Fixed (code only)** and name the capture that would confirm it.
