/**
 * touch.js — harness-added touch controls for the generated games.
 *
 * The models were asked for keyboard games only, so their HTML listens to
 * keydown/keyup on window and nothing else. This layer adds on-screen
 * controls that dispatch the SAME real KeyboardEvents the game already
 * listens for, so the model's code is untouched and desktop play is unchanged.
 *
 * Added by the llmbench harness, not by the model. Injected as:
 *   <script src="../touch.js"></script>
 */
(function () {
  var touchCapable = ("ontouchstart" in window) || navigator.maxTouchPoints > 0;
  // Still render on desktop when the URL has ?touch=1 (useful for demos/tests).
  var force = /[?&]touch=1\b/.test(location.search);
  if (!touchCapable && !force) return;

  var KEYMAP = [
    { id: "left",  key: "ArrowLeft",  code: "ArrowLeft",  label: "\u25C0", side: "left",  order: 1 },
    { id: "right", key: "ArrowRight", code: "ArrowRight", label: "\u25B6", side: "left",  order: 2 },
    { id: "fire",  key: " ",          code: "Space",      label: "FIRE",  side: "right", order: 1 }
  ];

  var css = ""
    + "#om-touch{position:fixed;inset:auto 0 0 0;height:0;z-index:2147483647;pointer-events:none;}"
    + "#om-touch .grp{position:fixed;bottom:18px;display:flex;gap:14px;pointer-events:none;}"
    + "#om-touch .grp.l{left:18px}#om-touch .grp.r{right:18px}"
    + "#om-touch button{pointer-events:auto;-webkit-user-select:none;user-select:none;touch-action:none;"
    + "width:74px;height:74px;border-radius:18px;border:2px solid rgba(255,255,255,.35);"
    + "background:rgba(10,16,24,.55);color:#eaf2ff;font:700 22px/1 system-ui,sans-serif;"
    + "backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);}"
    + "#om-touch button.fire{width:96px;border-color:rgba(245,197,66,.75);color:#f5c542;}"
    + "#om-touch button.on{background:rgba(245,197,66,.35);transform:scale(.96);}"
    + "#om-touch .hint{position:fixed;left:0;right:0;bottom:104px;text-align:center;color:rgba(230,240,255,.55);"
    + "font:500 12px/1.3 system-ui,sans-serif;pointer-events:none;}";

  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  var root = document.createElement("div");
  root.id = "om-touch";

  var groups = { left: document.createElement("div"), right: document.createElement("div") };
  groups.left.className = "grp l";
  groups.right.className = "grp r";

  function send(type, k) {
    window.dispatchEvent(new KeyboardEvent(type, {
      key: k.key, code: k.code, bubbles: true, cancelable: true
    }));
  }

  KEYMAP.forEach(function (k) {
    var b = document.createElement("button");
    b.type = "button";
    b.textContent = k.label;
    b.setAttribute("aria-label", k.id);
    if (k.id === "fire") b.className = "fire";
    var down = false;
    function press(e) {
      e.preventDefault();
      if (down) return;
      down = true;
      b.classList.add("on");
      send("keydown", k);
    }
    function release(e) {
      if (e) e.preventDefault();
      if (!down) return;
      down = false;
      b.classList.remove("on");
      send("keyup", k);
    }
    b.addEventListener("pointerdown", press);
    b.addEventListener("pointerup", release);
    b.addEventListener("pointercancel", release);
    b.addEventListener("pointerleave", release);
    b.addEventListener("contextmenu", function (e) { e.preventDefault(); });
    groups[k.side].appendChild(b);
  });

  var hint = document.createElement("div");
  hint.className = "hint";
  hint.textContent = "touch controls added by the benchmark harness";

  root.appendChild(groups.left);
  root.appendChild(groups.right);
  root.appendChild(hint);
  document.body.appendChild(root);

  // Some games call preventDefault on keys; make sure scrolling never eats the press.
  document.addEventListener("touchmove", function (e) {
    if (e.target.closest && e.target.closest("#om-touch")) e.preventDefault();
  }, { passive: false });
})();
