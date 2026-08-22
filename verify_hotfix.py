#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('hop')
checks = []

def file_text(path):
    return (root / path).read_text(encoding='utf-8')

def require(path, needle, label):
    if needle not in file_text(path):
        raise SystemExit(f'FAIL {label}: expected marker not found in {path}: {needle!r}')
    checks.append(label)

def forbid(path, needle, label):
    if needle in file_text(path):
        raise SystemExit(f'FAIL {label}: forbidden marker remains in {path}: {needle!r}')
    checks.append(label)

perspectives = [
    ('ui/src/main/java/org/apache/hop/ui/hopgui/perspective/explorer/ExplorerPerspective.java', 'ExplorerPerspective'),
    ('ui/src/main/java/org/apache/hop/ui/hopgui/perspective/metadata/MetadataPerspective.java', 'MetadataPerspective'),
    ('ui/src/main/java/org/apache/hop/ui/hopgui/perspective/execution/ExecutionPerspective.java', 'ExecutionPerspective'),
    ('ui/src/main/java/org/apache/hop/ui/hopgui/perspective/configuration/ConfigurationPerspective.java', 'ConfigurationPerspective'),
    ('plugins/misc/git/src/main/java/org/apache/hop/git/GitPerspective.java', 'GitPerspective'),
    ('plugins/misc/git/src/main/java/org/apache/hop/git/GitCommitPerspective.java', 'GitCommitPerspective'),
]
for path, cls in perspectives:
    forbid(path, f'@Getter private static {cls} instance;', f'{cls} lombok static getter removed')
    require(path, f'findPerspective({cls}.class)', f'{cls} resolves through current perspective manager')

path = 'ui/src/main/java/org/apache/hop/ui/hopgui/HopGui.java'
require(path, 'perspectiveManager.addPerspective(perspective);\n        perspective.initialize(this, mainPerspectivesComposite);', 'Perspective registered before initialize')

path = 'ui/src/main/java/org/apache/hop/ui/hopgui/shared/SashFormMemory.java'
forbid(path, 'private static final Map<String, Tracked> TRACKED', 'SashFormMemory no process-wide control map')
require(path, 'Map<Display, Map<String, Tracked>> TRACKED', 'SashFormMemory partitioned by Display')
require(path, 'TRACKED.remove(display)', 'SashFormMemory cleans Display bucket')

path = 'ui/src/main/java/org/apache/hop/ui/hopgui/HopGuiKeyHandler.java'
forbid(path, 'private static HopGuiKeyHandler singleton;', 'KeyHandler process singleton removed')
require(path, 'Map<Display, HopGuiKeyHandler> INSTANCES', 'KeyHandler partitioned by Display')
require(path, 'INSTANCES.remove(d)', 'KeyHandler cleans Display instance')

path = 'ui/src/main/java/org/apache/hop/ui/hopgui/shared/SwtGc.java'
forbid(path, 'Map<String, SwtUniversalImage> SVG_IMAGE_CACHE = new ConcurrentHashMap<>()', 'SwtGc global SVG image cache removed')
require(path, 'Map<Device, Map<String, SwtUniversalImage>> SVG_IMAGE_CACHE', 'SwtGc partitioned by Device')
require(path, 'SVG_IMAGE_CACHE.remove(device)', 'SwtGc cleans only disposed Device cache')

path = 'plugins/misc/git/src/main/java/org/apache/hop/git/GitGuiPlugin.java'
forbid(path, 'private static UIGit git;', 'GitGuiPlugin UIGit no longer JVM-global')
forbid(path, 'private UIGit git;', 'GitGuiPlugin does not isolate state per widget instance')
require(path, 'Map<String, GitSessionState> GIT_SESSION_STATES', 'Git repository state scoped by HopGui id')
require(path, 'private UIGit sessionGit;', 'Git session holder stores UIGit')
require(path, 'state().sessionGit', 'Git operations resolve current HopGui state')
require(path, 'GIT_SESSION_STATES.remove(hopGuiId)', 'Git session state cleaned on Display dispose')
require(path, 'Map<Display, GitGuiPlugin> INSTANCES', 'GuiCallback getInstance partitioned by Display')

path = 'plugins/misc/git/src/main/java/org/apache/hop/git/GitResource.java'
forbid(path, 'private static GitResource instance;', 'GitResource JVM singleton removed')
require(path, 'Map<Display, GitResource> INSTANCES', 'GitResource partitioned by Display')

path = 'ui/src/main/java/org/apache/hop/ui/hopgui/file/shared/DrillDownGuiPlugin.java'
forbid(path, 'runningPipelines.clear();', 'DrillDown no global running pipeline clear')
forbid(path, 'runningWorkflows.clear();', 'DrillDown no global running workflow clear')
require(path, 'cleanupOnRunStart(String previousRootLogChannelId)', 'DrillDown cleanup is run-scoped')

print(f'PASS: {len(checks)} hotfix invariants verified')
