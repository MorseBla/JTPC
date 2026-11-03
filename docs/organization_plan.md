# JTPC Local Organization Plan

Goal: retain both complete source projects on the desktop and deliver an independent JTPC project, raw logs, figures, and reproduction documentation using official DySM directory organization.
Architecture: Scheduler, application, experiment; preserve JTPC multiprocessing, shared memory, and frequency/period control. Model experiments remain separate; historical full source copies remain in the adjacent sources directory.
Technology: original C++/CUDA, Shell, Python/Matplotlib.
Basis: verified official DySM structure and user authorization to proceed.

## Constraints

- Do not modify remote/Windows originals. Verify copies before local organization.
- Use RTR=0.90 for Figure 7(b); retain Figure 7(a), Figures 8/9 initial periods, and stability content.
- Do not launch hardware collection or change algorithms/calibration. Explicitly identify missing Figures 1/2 provenance.
- Offline plotting must not call hardware scripts. Only necessary paths, exports, and authorized data conditions change.

## Tasks and checks

- [x] Copy both full directories; checksum dry runs show no differences.
- [x] Organize shared source, models, three experiments, and paper material; record sources and SHA256.
- [x] Extract notebook cells into section plotting entries; fix local relative paths; retain old figures and export 7(b) from 0.90 logs.
- [x] Verify raw-log hashes, recompute 7(b), check entry use from other working directories, execute plotting and PDF text/collision checks.
- [x] Deliver README, INSTALL, project/figure mapping, reproduction limits, and completion record.

## Areas requiring attention

Path case and C++ includes; historical working-directory assumptions; obsolete Windows paths in plotting cells; different versions with identical filenames; current source versus frozen historical run source.

## Organization completion record

Both full copies passed checksum verification. All 6,152 organized assets have SHA checks; seven extracted scripts have current SHA records. Independent means/std for 15 Figure 7(b) groups passed. Ten collected PDFs are present. Offline plotting succeeded.

The independent organization review found no Critical/Important issue within that scope; stale Figure 7(b) status text was corrected and extracted-script hashes were added to verify.py. This did not validate hardware collection: the later chain review found actual runtime/build issues.

Ruling: retain historical system-identification organization and independent Common/scripts, preserving JTPC calls; do not add unrelated libsmctrl or convert the threading/process model.
Ruling: archive the helper named 090 but setting 0.85 under collection/history; do not treat it as the final 0.90 entry. Historical source-freeze gaps remain.
Ruling: replace only the authorized Figure 7(b) asset. Do not recompile the DAC PDF or historical RTNS manuscript into an artificial final manuscript.
Figure QA is in docs/qa/README.md. Preserve raw clipping-related collision reports and separate geometric review; do not claim that every original automated collision result passed.
Hardware was not built/run during initial organization, and Figures 1/2 generation chains remained incomplete. Later temporary controller builds and collection review are recorded separately in collection_to_plot_review.md.
