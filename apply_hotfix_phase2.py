#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('hop')


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


def write(rel, text):
    (ROOT / rel).write_text(text, encoding='utf-8')
    print('phase2 patched', rel)


def replace_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f'{label}: expected exactly one match, got {n}')
    return text.replace(old, new, 1)


def replace_java_identifier(text, identifier, replacement):
    """Replace a Java identifier outside comments and string/char literals."""
    out = []
    i = 0
    n = len(text)
    state = 'normal'
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ''
        if state == 'normal':
            if c == '/' and nxt == '/':
                out.extend([c, nxt]); i += 2; state = 'line'; continue
            if c == '/' and nxt == '*':
                out.extend([c, nxt]); i += 2; state = 'block'; continue
            if c == '"':
                out.append(c); i += 1; state = 'string'; continue
            if c == "'":
                out.append(c); i += 1; state = 'char'; continue
            if c.isalpha() or c in '_$':
                j = i + 1
                while j < n and (text[j].isalnum() or text[j] in '_$'):
                    j += 1
                token = text[i:j]
                out.append(replacement if token == identifier else token)
                i = j
                continue
            out.append(c); i += 1; continue
        if state == 'line':
            out.append(c); i += 1
            if c == '\n': state = 'normal'
            continue
        if state == 'block':
            if c == '*' and nxt == '/':
                out.extend([c, nxt]); i += 2; state = 'normal'; continue
            out.append(c); i += 1; continue
        if state in ('string', 'char'):
            out.append(c); i += 1
            if c == '\\' and i < n:
                out.append(text[i]); i += 1; continue
            if (state == 'string' and c == '"') or (state == 'char' and c == "'"):
                state = 'normal'
            continue
    return ''.join(out)


# 1) Register each perspective in the current HopGui manager before initialize().
# This lets any getInstance() invoked from initialize()/GUI callbacks resolve the current session object.
rel = 'ui/src/main/java/org/apache/hop/ui/hopgui/HopGui.java'
text = read(rel)
old = '''        final IHopPerspective perspective = perspectiveClass.getConstructor().newInstance();
        perspective.initialize(this, mainPerspectivesComposite);
        perspectiveManager.addPerspective(perspective);'''
new = '''        final IHopPerspective perspective = perspectiveClass.getConstructor().newInstance();
        perspectiveManager.addPerspective(perspective);
        perspective.initialize(this, mainPerspectivesComposite);'''
text = replace_once(text, old, new, 'HopGui perspective registration order')
write(rel, text)


# 2) GitGuiPlugin: BaseGuiWidgets may create multiple plugin objects inside one HopGui session.
# The old static UIGit shared state across all sessions. Phase1 made it instance-local, which would
# break same-session toolbar/menu instances. Replace it with a HopGui-id scoped state holder.
rel = 'plugins/misc/git/src/main/java/org/apache/hop/git/GitGuiPlugin.java'
text = read(rel)
old = '''  private static final Map<Display, GitGuiPlugin> INSTANCES = new ConcurrentHashMap<>();

  private static GitGuiPlugin fallbackInstance;

  private UIGit git;'''
new = '''  private static final Map<Display, GitGuiPlugin> INSTANCES = new ConcurrentHashMap<>();

  private static GitGuiPlugin fallbackInstance;

  private static final Map<String, GitSessionState> GIT_SESSION_STATES = new ConcurrentHashMap<>();
  private static final Set<String> GIT_SESSION_CLEANUPS = ConcurrentHashMap.newKeySet();

  private static final class GitSessionState {
    private UIGit git;
  }

  private static String currentHopGuiId() {
    HopGui hopGui = HopGui.getInstance();
    return hopGui == null ? "__fallback__" : hopGui.getId();
  }

  private static GitSessionState state() {
    HopGui hopGui = HopGui.getInstance();
    String hopGuiId = hopGui == null ? "__fallback__" : hopGui.getId();
    GitSessionState state = GIT_SESSION_STATES.computeIfAbsent(hopGuiId, k -> new GitSessionState());
    if (hopGui != null && GIT_SESSION_CLEANUPS.add(hopGuiId)) {
      Display display = hopGui.getDisplay();
      if (display != null && !display.isDisposed()) {
        display.addListener(
            SWT.Dispose,
            event -> {
              GitSessionState removed = GIT_SESSION_STATES.remove(hopGuiId);
              GIT_SESSION_CLEANUPS.remove(hopGuiId);
              if (removed != null && removed.git != null) {
                try {
                  removed.git.closeRepo();
                } catch (Exception e) {
                  LogChannel.UI.logError("Error closing Git repository at session shutdown", e);
                }
              }
            });
      }
    }
    return state;
  }'''
text = replace_once(text, old, new, 'GitGuiPlugin session state holder')

# Convert every former field access/assignment to the current session state. Imports/comments/strings
# are protected by the lexical scanner. There are no method parameters/local variables named `git`
# in this class at this revision.
class_start = text.index('public class GitGuiPlugin')
prefix = text[:class_start]
body = text[class_start:]
body = replace_java_identifier(body, 'git', 'state().git')
text = prefix + body

# Phase1 callback used an explicit sessionPlugin field access. Normalize it after lexical conversion.
old_callback = '''  public void addRootChangedListener() {
    GitGuiPlugin sessionPlugin = getInstance();
    sessionPlugin.state().git = null;
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
new_callback = '''  public void addRootChangedListener() {
    state().git = null;
    ExplorerPerspective explorerPerspective = ExplorerPerspective.getInstance();
    if (explorerPerspective == null) {
      return;
    }

    // The callback object is already Display-scoped by getInstance(); the Git repository itself is
    // shared by all GUI plugin instances belonging to this HopGui session through state().
    //
    explorerPerspective.getRootChangedListeners().add(this);
    explorerPerspective.getFilePaintListeners().add(this);
    explorerPerspective.getRefreshListeners().add(this);
    explorerPerspective.getSelectionListeners().add(this);

    enableButtons();
  }'''
text = replace_once(text, old_callback, new_callback, 'GitGuiPlugin callback normalization')

# Remove an unused helper introduced above if the compiler/style checker flags it; state() is the
# single authority for choosing the HopGui scope, so no callers need a separate id method.
unused = '''  private static String currentHopGuiId() {
    HopGui hopGui = HopGui.getInstance();
    return hopGui == null ? "__fallback__" : hopGui.getId();
  }

'''
text = text.replace(unused, '', 1)
write(rel, text)

print('Hotfix phase2 completed')
