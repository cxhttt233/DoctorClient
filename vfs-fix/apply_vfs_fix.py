#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('hop')

hop_vfs = root / 'core/src/main/java/org/apache/hop/core/vfs/HopVfs.java'
ns = root / 'core/src/main/java/org/apache/hop/core/vfs/HopVfsNamespaces.java'
test = root / 'core/src/test/java/org/apache/hop/core/vfs/HopVfsMultiTenantBootstrapTest.java'

def replace_once(path, old, new):
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{path}: expected one match, found {count}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')

replace_once(
    ns,
    '  /** Set when the runtime serves several tenants at once, so nobody shares the process manager. */\n  private static boolean isolateEverything;',
    '  /** Set when the runtime serves several tenants at once, so nobody shares the process manager. */\n  private static boolean isolateEverything;\n\n  /** True when a runtime such as Hop Web has installed tenant/session scoped VFS state. */\n  static synchronized boolean isIsolateEverything() {\n    return isolateEverything;\n  }',
)

old = '''  public static synchronized void setBootstrapVariables(IVariables variables) {\n    if (variables == bootstrapVariables) {\n      return;\n    }\n    bootstrapVariables = variables;\n'''
new = '''  public static synchronized void setBootstrapVariables(IVariables variables) {\n    // Hop Web installs a tenant/session scoped VFS namespace. Project activation in one session\n    // must not rebuild the process-wide manager, because reset() also closes every live namespace.\n    // The session's named providers are registered by HopGui.useVfsNamespaceOfOpenProject().\n    // Keep null as an explicit process-level cleanup signal used by tests/shutdown.\n    if (variables != null && HopVfsNamespaces.isIsolateEverything()) {\n      return;\n    }\n    if (variables == bootstrapVariables) {\n      return;\n    }\n    bootstrapVariables = variables;\n'''
replace_once(hop_vfs, old, new)

test.write_text(r'''/* Licensed to the Apache Software Foundation (ASF) under one or more contributor license agreements. */
package org.apache.hop.core.vfs;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;

import java.lang.reflect.Field;
import org.apache.commons.vfs2.impl.DefaultFileSystemManager;
import org.apache.hop.core.scope.IHopScope;
import org.apache.hop.core.variables.Variables;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

class HopVfsMultiTenantBootstrapTest {

  @AfterEach
  void cleanup() throws Exception {
    HopVfsNamespaces.setScope(null);
    setBoolean("namedProvidersRegistered", false);
    setObject("bootstrapVariables", null);
    HopVfs.reset();
  }

  @Test
  void projectBootstrapDoesNotResetProcessManagerInMultiTenantRuntime() throws Exception {
    DefaultFileSystemManager manager = HopVfs.getFileSystemManager();
    assertNotNull(manager);
    setBoolean("namedProvidersRegistered", true);

    HopVfsNamespaces.setScope(IHopScope.process());
    HopVfs.setBootstrapVariables(new Variables());

    assertSame(manager, getObject("fsm"), "Hop Web project activation must not reset process VFS");
  }

  @Test
  void desktopStyleBootstrapStillResetsProcessManager() throws Exception {
    DefaultFileSystemManager manager = HopVfs.getFileSystemManager();
    assertNotNull(manager);
    setBoolean("namedProvidersRegistered", true);

    HopVfsNamespaces.setScope(null);
    HopVfs.setBootstrapVariables(new Variables());

    assertNull(getObject("fsm"), "non multi-tenant behavior must stay unchanged");
  }

  private static Object getObject(String name) throws Exception {
    Field f = HopVfs.class.getDeclaredField(name);
    f.setAccessible(true);
    return f.get(null);
  }

  private static void setObject(String name, Object value) throws Exception {
    Field f = HopVfs.class.getDeclaredField(name);
    f.setAccessible(true);
    f.set(null, value);
  }

  private static void setBoolean(String name, boolean value) throws Exception {
    Field f = HopVfs.class.getDeclaredField(name);
    f.setAccessible(true);
    f.setBoolean(null, value);
  }
}
''', encoding='utf-8')

print('Applied VFS multi-tenant bootstrap guard and regression tests')
