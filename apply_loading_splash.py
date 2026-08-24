#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: apply_loading_splash.py <hop-source-dir>")

root = Path(sys.argv[1])
hop_web = root / "rap/src/main/java/org/apache/hop/ui/hopgui/HopWeb.java"
entry = root / "rap/src/main/java/org/apache/hop/ui/hopgui/HopWebEntryPoint.java"

web = hop_web.read_text(encoding="utf-8")
entry_text = entry.read_text(encoding="utf-8")

if "hop-loading-splash" in web or "hideLoadingSplash" in entry_text:
    raise SystemExit("loading splash patch already present")

anchor = """  @Override\n  public void configure(Application application) {\n"""
if anchor not in web:
    raise SystemExit("HopWeb.java configure anchor not found")

loading_method = r'''  /**
   * Static HTML shown immediately by the RAP web client while the first UI session is being built.
   * This deliberately has no real percentage: HopGui startup does not expose reliable progress
   * events. HopWebEntryPoint removes the overlay once the Hop GUI event loop is running and the
   * initial queued startup work has had a chance to complete.
   */
  private static String getLoadingSplash(boolean dark) {
    String background = dark ? "#17191d" : "#f3f5f7";
    String foreground = dark ? "#f4f7fb" : "#20242a";
    String secondary = dark ? "#aeb6c2" : "#68717d";
    String track = dark ? "rgba(255,255,255,.16)" : "rgba(20,30,40,.14)";
    return "<style>"
        + "@keyframes hop-loading-spin{to{transform:rotate(360deg)}}"
        + "#hop-loading-splash{position:fixed;inset:0;z-index:2147483647;display:flex;"
        + "align-items:center;justify-content:center;background:"
        + background
        + ";color:"
        + foreground
        + ";font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;"
        + "transition:opacity .18s ease}"
        + "#hop-loading-splash .hop-loading-card{text-align:center;transform:translateY(-3vh)}"
        + "#hop-loading-splash .hop-loading-brand{font-size:14px;letter-spacing:2.8px;"
        + "font-weight:600;margin-bottom:18px}"
        + "#hop-loading-splash .hop-loading-brand strong{font-size:38px;letter-spacing:1px;"
        + "display:block;margin-top:2px}"
        + "#hop-loading-splash .hop-loading-spinner{width:40px;height:40px;margin:0 auto 18px;"
        + "border:4px solid "
        + track
        + ";border-top-color:#2f8de4;border-radius:50%;animation:hop-loading-spin .82s linear infinite}"
        + "#hop-loading-splash .hop-loading-title{font-size:15px;font-weight:600;margin-bottom:7px}"
        + "#hop-loading-splash .hop-loading-subtitle{font-size:12px;color:"
        + secondary
        + "}"
        + "</style>"
        + "<div id='hop-loading-splash' role='status' aria-live='polite'>"
        + "<div class='hop-loading-card'>"
        + "<div class='hop-loading-brand'>APACHE<strong>HOP</strong></div>"
        + "<div class='hop-loading-spinner'></div>"
        + "<div class='hop-loading-title'>正在加载工作区...</div>"
        + "<div class='hop-loading-subtitle'>Loading workspace, please wait...</div>"
        + "</div></div>";
  }

'''
web = web.replace(anchor, loading_method + anchor, 1)

light_anchor = '    propertiesLight.put(WebClient.HEAD_HTML, readTextFromResource("head.html"));\n'
dark_anchor = '    propertiesDark.put(WebClient.HEAD_HTML, readTextFromResource("head.html"));\n'
if light_anchor not in web or dark_anchor not in web:
    raise SystemExit("HopWeb.java WebClient property anchors not found")
web = web.replace(
    light_anchor,
    light_anchor + '    propertiesLight.put(WebClient.BODY_HTML, getLoadingSplash(false));\n',
    1,
)
web = web.replace(
    dark_anchor,
    dark_anchor + '    propertiesDark.put(WebClient.BODY_HTML, getLoadingSplash(true));\n',
    1,
)

open_anchor = """    HopGui.getInstance().open();\n\n    // URL params were only for initial project/file; clear so they don't affect CLI/run.\n"""
if open_anchor not in entry_text:
    raise SystemExit("HopWebEntryPoint.java HopGui.open anchor not found")
entry_text = entry_text.replace(
    open_anchor,
    """    // HopGui.open() owns the SWT/RAP event loop and normally returns only when the UI closes.\n    // Queue splash removal before entering it. The first async callback runs once the event loop is\n    // alive; the short timer then lets HopGui's already-queued startup work run first. If that work\n    // keeps the UI thread busy, the timer naturally waits until the UI thread becomes responsive.\n    display.asyncExec(() -> display.timerExec(250, this::hideLoadingSplash));\n    HopGui.getInstance().open();\n\n    // URL params were only for initial project/file; clear so they don't affect CLI/run.\n""",
    1,
)

method_anchor = """  /** Save the user's theme preference to the audit folder (per-user when authenticated). */\n"""
if method_anchor not in entry_text:
    raise SystemExit("HopWebEntryPoint.java method insertion anchor not found")

hide_method = r'''  /** Fade out and remove the static BODY_HTML splash on the UI thread. */
  private void hideLoadingSplash() {
    try {
      JavaScriptExecutor executor = RWT.getClient().getService(JavaScriptExecutor.class);
      if (executor == null) {
        LogChannel.UI.logDebug("Could not hide Hop Web loading splash: JavaScriptExecutor unavailable");
        return;
      }
      executor.execute(
          "var e=document.getElementById('hop-loading-splash');"
              + "if(e){e.style.opacity='0';e.style.pointerEvents='none';"
              + "window.setTimeout(function(){if(e&&e.parentNode){e.parentNode.removeChild(e);}},190);}");
    } catch (Exception e) {
      LogChannel.UI.logDebug("Could not hide Hop Web loading splash", e);
    }
  }

'''
entry_text = entry_text.replace(method_anchor, hide_method + method_anchor, 1)

hop_web.write_text(web, encoding="utf-8")
entry.write_text(entry_text, encoding="utf-8")

print("Applied Hop Web startup loading splash patch")
print(hop_web)
print(entry)
