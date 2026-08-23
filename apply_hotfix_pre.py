#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('hop')

# The 20260820 HopGuiKeyHandler baseline has Map/SWT imports, but the session-scoped hotfix also
# needs ConcurrentHashMap and Display. Add them before the main patch rewrites the singleton.
key_rel = 'ui/src/main/java/org/apache/hop/ui/hopgui/HopGuiKeyHandler.java'
key_path = root / key_rel
key_text = key_path.read_text(encoding='utf-8')
if 'import java.util.concurrent.ConcurrentHashMap;' not in key_text:
    needle = 'import java.util.Set;'
    if key_text.count(needle) != 1:
        raise RuntimeError(f'{key_rel}: expected one java.util.Set import')
    key_text = key_text.replace(needle, needle + '\nimport java.util.concurrent.ConcurrentHashMap;', 1)
if 'import org.eclipse.swt.widgets.Display;' not in key_text:
    needle = 'import org.eclipse.swt.widgets.Control;'
    if key_text.count(needle) != 1:
        raise RuntimeError(f'{key_rel}: expected one SWT Control import')
    key_text = key_text.replace(needle, needle + '\nimport org.eclipse.swt.widgets.Display;', 1)
key_path.write_text(key_text, encoding='utf-8')
print('pre-patched HopGuiKeyHandler imports')

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
