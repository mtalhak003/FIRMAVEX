# FIRMAVEX Step 19 paper revision: transfer only

This isolated branch distributes an unchanged ZIP at the user's request.
It does not modify main, FIRMAVEX source, the frozen protocol, any campaign
archive or backup, or the existing analysis. It is not an implementation change.

**PRELIMINARY, JOURNAL-DERIVED. Execution verification remains FAILED.**
Supplementary evidence is missing at zero-based plan position 7:
`multi_variable / random / seed 6`, whose journal retains discovery at charged
attempt 13. The archive does not repair that evidence gap or establish verified
physical firmware executions. No firmware experiment was rerun for this transfer.

## Download and verify

Open `firmavex-step19-paper-revision.zip` in GitHub and use **Download raw file**.
Save the ZIP, then run this in the same directory:

```bash
printf '%s\n' '96e5826d28f86e029d746b538a43e1587e761434ccb739dcf8dbe89700f07ea0  firmavex-step19-paper-revision.zip' | sha256sum -c -
python3 -m zipfile -t firmavex-step19-paper-revision.zip
```

Both checks must pass before extracting. The ZIP contains revised plotting
code, captions, manuscript draft, tests, and newly regenerated example figures.
Use its README to extract into new tools/output directories without overwriting
existing analysis outputs. No analysis runs merely by downloading or extracting.

ZIP SHA-256:
`96e5826d28f86e029d746b538a43e1587e761434ccb739dcf8dbe89700f07ea0`
