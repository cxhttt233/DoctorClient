#!/usr/bin/env python3
from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("hop")


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel, text):
    (ROOT / rel).write_text(text, encoding="utf-8")
    print("patched", rel)


def replace_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {n}")
    return text.replace(old, new, 1)


def patch_perspective(rel, cls, construct_fallback=False):
    text = read(rel)
    text = text.replace(f"@Getter private static {cls} instance;", f"private static {cls} instance;")
    field = f"private static {cls} instance;"
    if field not in text:
        raise RuntimeError(f"{rel}: instance field not found")

    fallback = f"return instance;"
    if construct_fallback:
        fallback = f"if (instance == null) {{\n      instance = new {cls}();\n    }}\n    return instance;"

    method = f'''public static {cls} getInstance() {{
    try {{
      HopGui hopGui = HopGui.getInstance();
      if (hopGui != null && hopGui.getPerspectiveManager() != null) {{
        {cls} current = hopGui.getPerspectiveManager().findPerspective({cls}.class);
        if (current != null) {{
          return current;
        }}
      }}
    }} catch (Throwable ignored) {{
      // HopGui can still be under construction; desktop keeps the legacy fallback below.
    }}
    if (org.apache.hop.ui.util.EnvironmentUtils.getInstance().isWeb()) {{
      return null;
    }}
    {fallback}
  }}'''

    explicit = re.compile(
        rf"public static {re.escape(cls)} getInstance\(\) \{{.*?\n  \}}",
        re.S,
    )
    if explicit.search(text):
        text, n = explicit.subn(method, text, count=1)
        if n != 1:
            raise RuntimeError(f"{rel}: failed replacing explicit getInstance")
    else:
        text = replace_once(text, field, field + "\n\n  " + method, rel + " getter")
    write(rel, text)


# Perspective singletons: resolve through the current HopGui/PerspectiveManager in Hop Web.
patch_perspective(
    "ui/src/main/java/org/apache/hop/ui/hopgui/perspective/explorer/ExplorerPerspective.java",
    "ExplorerPerspective",
    True,
)
patch_perspective(
    "ui/src/main/java/org/apache/hop/ui/hopgui/perspective/metadata/MetadataPerspective.java",
    "MetadataPerspective",
)
patch_perspective(
    "ui/src/main/java/org/apache/hop/ui/hopgui/perspective/execution/ExecutionPerspective.java",
    "ExecutionPerspective",
)
patch_perspective(
    "ui/src/main/java/org/apache/hop/ui/hopgui/perspective/configuration/ConfigurationPerspective.java",
    "ConfigurationPerspective",
)
patch_perspective(
    "plugins/misc/git/src/main/java/org/apache/hop/git/GitPerspective.java",
    "GitPerspective",
)
patch_perspective(
    "plugins/misc/git/src/main/java/org/apache/hop/git/GitCommitPerspective.java",
    "GitCommitPerspective",
)


# SashFormMemory: do not keep controls from every RAP session in one JVM-global map.
rel = "ui/src/main/java/org/apache/hop/ui/hopgui/shared/SashFormMemory.java"
text = read(rel)
text = replace_once(
    text,
    "import java.util.Map;",
    "import java.util.Map;\nimport java.util.Set;\nimport java.util.concurrent.ConcurrentHashMap;",
    "SashFormMemory imports",
)
text = replace_once(
    text,
    "private static final Map<String, Tracked> TRACKED = new LinkedHashMap<>();",
    "private static final Map<Display, Map<String, Tracked>> TRACKED = new ConcurrentHashMap<>();\n\n  private static final Set<Display> TRACKED_DISPLAYS = ConcurrentHashMap.newKeySet();",
    "SashFormMemory tracked map",
)
old = '''    int[] defaults = defaultsOrFallback(defaultWeights);
    restore(sashForm, key, defaults);
    TRACKED.put(key, new Tracked(sashForm, defaults));

    Display display = sashForm.getDisplay();'''
new = '''    int[] defaults = defaultsOrFallback(defaultWeights);
    restore(sashForm, key, defaults);

    Display display = sashForm.getDisplay();
    TRACKED.computeIfAbsent(display, d -> new LinkedHashMap<>()).put(key, new Tracked(sashForm, defaults));
    if (TRACKED_DISPLAYS.add(display)) {
      display.addListener(
          SWT.Dispose,
          event -> {
            TRACKED.remove(display);
            TRACKED_DISPLAYS.remove(display);
          });
    }'''
text = replace_once(text, old, new, "SashFormMemory persist")
old = '''  public static void resetAll() {
    for (Map.Entry<String, Tracked> entry : TRACKED.entrySet()) {
      Tracked tracked = entry.getValue();
      SashForm sashForm = tracked.sashForm();
      int[] defaults = tracked.defaultWeights();
      if (sashForm != null && !sashForm.isDisposed() && defaults != null && defaults.length > 0) {
        sashForm.setWeights(defaults);
      }
      forget(entry.getKey());
    }
  }'''
new = '''  public static void resetAll() {
    Display display = Display.getCurrent();
    if (display == null) {
      return;
    }
    Map<String, Tracked> trackedForDisplay = TRACKED.get(display);
    if (trackedForDisplay == null) {
      return;
    }
    for (Map.Entry<String, Tracked> entry : new LinkedHashMap<>(trackedForDisplay).entrySet()) {
      Tracked tracked = entry.getValue();
      SashForm sashForm = tracked.sashForm();
      int[] defaults = tracked.defaultWeights();
      if (sashForm != null && !sashForm.isDisposed() && defaults != null && defaults.length > 0) {
        sashForm.setWeights(defaults);
      }
      forget(entry.getKey());
    }
  }'''
text = replace_once(text, old, new, "SashFormMemory resetAll")
write(rel, text)


# HopGuiKeyHandler: one handler per Display/session instead of one process-wide UI root.
rel = "ui/src/main/java/org/apache/hop/ui/hopgui/HopGuiKeyHandler.java"
text = read(rel)
text = replace_once(
    text,
    "private static HopGuiKeyHandler singleton;",
    "private static final Map<Display, HopGuiKeyHandler> INSTANCES = new ConcurrentHashMap<>();\n\n  private static HopGuiKeyHandler fallbackSingleton;",
    "HopGuiKeyHandler singleton field",
)
old = '''  public static HopGuiKeyHandler getInstance() {
    if (singleton == null) {
      singleton = new HopGuiKeyHandler();
    }
    return singleton;
  }'''
new = '''  public static HopGuiKeyHandler getInstance() {
    Display display = Display.getCurrent();
    if (display == null || display.isDisposed()) {
      synchronized (HopGuiKeyHandler.class) {
        if (fallbackSingleton == null) {
          fallbackSingleton = new HopGuiKeyHandler();
        }
        return fallbackSingleton;
      }
    }
    return INSTANCES.computeIfAbsent(
        display,
        d -> {
          HopGuiKeyHandler handler = new HopGuiKeyHandler();
          d.addListener(SWT.Dispose, event -> INSTANCES.remove(d));
          return handler;
        });
  }'''
text = replace_once(text, old, new, "HopGuiKeyHandler getInstance")
write(rel, text)


# SwtGc: partition SVG universal-image and SWT Image caches by Device/Display and clean only that device.
rel = "ui/src/main/java/org/apache/hop/ui/hopgui/shared/SwtGc.java"
text = read(rel)
text = replace_once(text, "import java.util.Map;", "import java.util.Map;\nimport java.util.Set;", "SwtGc imports")
text = replace_once(
    text,
    "private static final Map<String, SwtUniversalImage> SVG_IMAGE_CACHE = new ConcurrentHashMap<>();",
    "private static final Map<Device, Map<String, SwtUniversalImage>> SVG_IMAGE_CACHE =\n      new ConcurrentHashMap<>();",
    "SwtGc cache",
)
text = replace_once(
    text,
    "private static volatile boolean svgCacheDisposeHookRegistered;",
    "private static final Set<Device> SVG_CACHE_DISPOSE_HOOKS = ConcurrentHashMap.newKeySet();",
    "SwtGc hook state",
)
old = '''    ensureSvgImageCacheDisposeHook(gc.getDevice());
    return SVG_IMAGE_CACHE.computeIfAbsent(
        cacheKey,
        key -> new SwtUniversalImageSvg(new SvgImage(cacheEntry.getSvgDocument()), false));'''
new = '''    Device device = gc.getDevice();
    ensureSvgImageCacheDisposeHook(device);
    Map<String, SwtUniversalImage> deviceCache =
        SVG_IMAGE_CACHE.computeIfAbsent(device, d -> new ConcurrentHashMap<>());
    return deviceCache.computeIfAbsent(
        cacheKey,
        key -> new SwtUniversalImageSvg(new SvgImage(cacheEntry.getSvgDocument()), false));'''
text = replace_once(text, old, new, "SwtGc getCachedSvgImage")
pattern = re.compile(
    r"  private static void ensureSvgImageCacheDisposeHook\(Device device\) \{.*?\n  \}\n\n  @Override\n  public boolean drawFileImage",
    re.S,
)
replacement = '''  private static void ensureSvgImageCacheDisposeHook(Device device) {
    if (!(device instanceof Display display) || !SVG_CACHE_DISPOSE_HOOKS.add(device)) {
      return;
    }
    display.addListener(
        SWT.Dispose,
        event -> {
          Map<String, SwtUniversalImage> deviceCache = SVG_IMAGE_CACHE.remove(device);
          if (deviceCache != null) {
            for (SwtUniversalImage image : deviceCache.values()) {
              try {
                image.dispose();
              } catch (Exception ignored) {
                // best-effort cleanup at display shutdown
              }
            }
            deviceCache.clear();
          }
          SVG_CACHE_DISPOSE_HOOKS.remove(device);
        });
  }

  @Override
  public boolean drawFileImage'''
text, n = pattern.subn(replacement, text, count=1)
if n != 1:
    raise RuntimeError("SwtGc dispose hook method not found")
write(rel, text)


# Drill-down: clear only the previous execution family for the current graph, never every user's state.
rel = "ui/src/main/java/org/apache/hop/ui/hopgui/file/shared/DrillDownGuiPlugin.java"
text = read(rel)
text = replace_once(text, "import java.util.List;", "import java.util.HashSet;\nimport java.util.List;", "DrillDown imports 1")
text = replace_once(text, "import java.util.Map;", "import java.util.Map;\nimport java.util.Set;", "DrillDown imports 2")
old = '''  public static void cleanupOnRunStart() {
    runningPipelines.clear();
    runningWorkflows.clear();
    dataSnifferBuffersByLogChannelId.clear();
    dataSnifferHopBuffersByLogChannelId.clear();
  }'''
new = '''  public static void cleanupOnRunStart(String previousRootLogChannelId) {
    if (previousRootLogChannelId == null || previousRootLogChannelId.isBlank()) {
      return;
    }
    Set<String> executionIds =
        new HashSet<>(LoggingRegistry.getInstance().getLogChannelChildren(previousRootLogChannelId));
    executionIds.add(previousRootLogChannelId);
    for (String logChannelId : executionIds) {
      runningPipelines.remove(logChannelId);
      runningWorkflows.remove(logChannelId);
      dataSnifferBuffersByLogChannelId.remove(logChannelId);
      dataSnifferHopBuffersByLogChannelId.remove(logChannelId);
    }
  }'''
text = replace_once(text, old, new, "DrillDown cleanup")
write(rel, text)

for rel, variable in [
    ("ui/src/main/java/org/apache/hop/ui/hopgui/file/pipeline/HopGuiPipelineGraph.java", "pipeline"),
    ("ui/src/main/java/org/apache/hop/ui/hopgui/file/workflow/HopGuiWorkflowGraph.java", "workflow"),
]:
    text = read(rel)
    text = replace_once(
        text,
        "DrillDownGuiPlugin.cleanupOnRunStart();",
        f"DrillDownGuiPlugin.cleanupOnRunStart({variable} == null ? null : {variable}.getLogChannelId());",
        rel + " drilldown cleanup call",
    )
    write(rel, text)


# GitResource: resources obtained from session-scoped GuiResource must also be Display scoped.
rel = "plugins/misc/git/src/main/java/org/apache/hop/git/GitResource.java"
text = read(rel)
text = replace_once(
    text,
    "import lombok.Getter;",
    "import java.util.Map;\nimport java.util.concurrent.ConcurrentHashMap;\nimport lombok.Getter;",
    "GitResource imports",
)
text = replace_once(
    text,
    "import org.eclipse.swt.graphics.Image;",
    "import org.eclipse.swt.graphics.Image;\nimport org.eclipse.swt.widgets.Display;",
    "GitResource Display import",
)
text = replace_once(
    text,
    "private static GitResource instance;",
    "private static final Map<Display, GitResource> INSTANCES = new ConcurrentHashMap<>();\n\n  private static GitResource fallbackInstance;",
    "GitResource singleton field",
)
old = '''  public static GitResource getInstance() {
    if (instance == null) {
      instance = new GitResource();
    }
    return instance;
  }'''
new = '''  public static GitResource getInstance() {
    Display display = Display.getCurrent();
    if (display == null || display.isDisposed()) {
      synchronized (GitResource.class) {
        if (fallbackInstance == null) {
          fallbackInstance = new GitResource();
        }
        return fallbackInstance;
      }
    }
    return INSTANCES.computeIfAbsent(
        display,
        d -> {
          GitResource resource = new GitResource();
          d.addListener(org.eclipse.swt.SWT.Dispose, event -> INSTANCES.remove(d));
          return resource;
        });
  }'''
text = replace_once(text, old, new, "GitResource getInstance")
write(rel, text)


# GitGuiPlugin: remove JVM-global UIGit and make getInstance Display-scoped. The GUI callback binds
# the per-Display plugin object into each Explorer listener list.
rel = "plugins/misc/git/src/main/java/org/apache/hop/git/GitGuiPlugin.java"
text = read(rel)
text = replace_once(
    text,
    "import java.util.Map;",
    "import java.util.Map;\nimport java.util.concurrent.ConcurrentHashMap;",
    "GitGuiPlugin imports",
)
text = replace_once(
    text,
    "import org.eclipse.swt.widgets.Control;",
    "import org.eclipse.swt.widgets.Control;\nimport org.eclipse.swt.widgets.Display;",
    "GitGuiPlugin Display import",
)
text = replace_once(
    text,
    "private static GitGuiPlugin instance;\n\n  private static UIGit git;",
    "private static final Map<Display, GitGuiPlugin> INSTANCES = new ConcurrentHashMap<>();\n\n  private static GitGuiPlugin fallbackInstance;\n\n  private UIGit git;",
    "GitGuiPlugin singleton state",
)
old = '''  public static GitGuiPlugin getInstance() {
    if (instance == null) {
      instance = new GitGuiPlugin();
    }
    return instance;
  }'''
new = '''  public static GitGuiPlugin getInstance() {
    Display display = Display.getCurrent();
    if (display == null || display.isDisposed()) {
      synchronized (GitGuiPlugin.class) {
        if (fallbackInstance == null) {
          fallbackInstance = new GitGuiPlugin();
        }
        return fallbackInstance;
      }
    }
    return INSTANCES.computeIfAbsent(
        display,
        d -> {
          GitGuiPlugin plugin = new GitGuiPlugin();
          d.addListener(SWT.Dispose, event -> INSTANCES.remove(d));
          return plugin;
        });
  }'''
text = replace_once(text, old, new, "GitGuiPlugin getInstance")
old = '''  public void addRootChangedListener() {
    git = null;
    ExplorerPerspective explorerPerspective = ExplorerPerspective.getInstance();

    // Listener to what's going on in the explorer perspective...
    //
    explorerPerspective.getRootChangedListeners().add(this);
    explorerPerspective.getFilePaintListeners().add(this);
    explorerPerspective.getRefreshListeners().add(this);
    explorerPerspective.getSelectionListeners().add(this);

    enableButtons();
  }'''
new = '''  public void addRootChangedListener() {
    GitGuiPlugin sessionPlugin = getInstance();
    sessionPlugin.git = null;
    ExplorerPerspective explorerPerspective = ExplorerPerspective.getInstance();
    if (explorerPerspective == null) {
      return;
    }

    // Listener state must belong to the current Explorer/Display, not to the application plugin.
    //
    explorerPerspective.getRootChangedListeners().add(sessionPlugin);
    explorerPerspective.getFilePaintListeners().add(sessionPlugin);
    explorerPerspective.getRefreshListeners().add(sessionPlugin);
    explorerPerspective.getSelectionListeners().add(sessionPlugin);

    sessionPlugin.enableButtons();
  }'''
text = replace_once(text, old, new, "GitGuiPlugin listener binding")
write(rel, text)

print("Hotfix patch application completed")
