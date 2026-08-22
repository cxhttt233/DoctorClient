#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('hop')
rel = 'ui/src/main/java/org/apache/hop/ui/hopgui/file/pipeline/HopGuiPipelineGraph.java'
path = root / rel
text = path.read_text(encoding='utf-8')
needle = 'DrillDownGuiPlugin.cleanupOnRunStart();'
count = text.count(needle)
if count != 2:
    raise RuntimeError(f'{rel}: expected 2 cleanupOnRunStart call sites at pinned Hop revision, got {count}')
# Phase1 was originally written for one call site. Pre-patch one execution path and leave the other
# for phase1, so both paths end up run-scoped while phase1 keeps its strict replacement checks.
replacement = 'DrillDownGuiPlugin.cleanupOnRunStart(pipeline == null ? null : pipeline.getLogChannelId());'
text = text.replace(needle, replacement, 1)
path.write_text(text, encoding='utf-8')
print('pre-patched first PipelineGraph drill-down cleanup call')
