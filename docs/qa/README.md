# Figure QA Record

Seven locally regenerated figures were checked: FC, DFS, JTPC, RTR sweep, power sweep, utility, and task arrival. Original paper assets were not redrawn or overwritten.

- Actual plot-area alignment passed for all four multipanel figures; the three single-panel figures are NOT APPLICABLE. No relaxed thresholds or geometry exemptions.
- Final PDFs all passed the 5 pt minimum font-size check. Figure 7(b) source preflight: 19 PASS, 0 FAIL. Two notices concerned missing TIFF and the retained 4-inch canvas; neither affects this PDF/SVG delivery.
- The original collision tool reported FAIL/WARN for six PDFs because get_drawings did not apply PDF clipping, counting invisible curve/bar outlines and legend hatching. These raw results must not be relabeled PASS.
- On the same final PDFs, get_drawings(extended=True) was used to recover nested scissor rectangles. Every reported collision object was effectively clipped away at the text position. clip_review files retain item-level evidence. The original task-arrival check itself reported 0 FAIL/0 WARN.
- Full figures and individual panels were visually inspected: no visible text occlusion, clipping, or displaced legends. The requested Figure 7(a) data-axis clipping remains; its scientific-value discrepancy was outside this change.
- Figure 7(b) retains editable PDF text and vector graphics, plus SVG and 600 dpi PNG. Rasterization was not used to hide collision reports.

contact.png is the review contact sheet; individual previews are QA renders. initial_* files are original reports from the first export. run_*_review.py records local checks and depends on the local nature-figure skill directory. Delivered experiment plotting entries need neither those skills nor the audit scripts.
