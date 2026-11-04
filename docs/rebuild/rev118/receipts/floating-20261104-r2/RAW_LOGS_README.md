# Original process output

`RAW_LOGS.zip` retains the original process-output files byte-for-byte, including trailing spaces emitted by Gradle and terminal newlines emitted by JUnit. They were not normalized to make a source-formatting check pass. `MANIFEST.json` version 2 lists the direct committed files and the SHA-256 of every decompressed log member separately. The same original logs remain in the isolated VM workspace.

The staged source check first rejected a trailing empty source line; that line was corrected and actual native component compilation repeated. Later it correctly reported whitespace in the original diagnostic output. Archiving that immutable evidence avoids editing the output or relaxing any source assertion, hook, baseline or repository rule.
