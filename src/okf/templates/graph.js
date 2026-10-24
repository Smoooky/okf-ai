/* okf view: a force layout of the links between documents, with zoom, pan and neighbour highlighting. */
(function () {
  "use strict";
  var svg = document.getElementById("graph");
  var data = document.getElementById("graph-data");
  if (!svg || !data) return;
  var graph = JSON.parse(data.textContent);
  var nodes = graph.nodes, edges = graph.edges, n = nodes.length;
  var groups = Array.prototype.slice.call(svg.querySelectorAll(".node"));
  var lines = Array.prototype.slice.call(svg.querySelectorAll(".edge"));
  var neighbours = nodes.map(function () { return {}; });
  edges.forEach(function (e) { neighbours[e[0]][e[1]] = true; neighbours[e[1]][e[0]] = true; });

  /* Fruchterman-Reingold, a few hundred iterations at load; starts from the circle drawn by the server. */
  var W = 1000, H = 700, k = Math.sqrt((W * H) / Math.max(n, 1)) * 0.62;
  var x = nodes.map(function (p) { return p.x; }), y = nodes.map(function (p) { return p.y; });
  var rounds = 420;
  for (var t = 0; t < rounds && n > 1; t++) {
    var dx = new Array(n).fill(0), dy = new Array(n).fill(0);
    for (var i = 0; i < n; i++) {
      for (var j = i + 1; j < n; j++) {
        var ex = x[i] - x[j], ey = y[i] - y[j], d = Math.max(Math.sqrt(ex * ex + ey * ey), 0.01), f = (k * k) / d;
        dx[i] += (ex / d) * f; dy[i] += (ey / d) * f; dx[j] -= (ex / d) * f; dy[j] -= (ey / d) * f;
      }
    }
    edges.forEach(function (e) {
      var a = e[0], b = e[1], ex = x[a] - x[b], ey = y[a] - y[b], d = Math.max(Math.sqrt(ex * ex + ey * ey), 0.01);
      var f = (d * d) / k;
      dx[a] -= (ex / d) * f; dy[a] -= (ey / d) * f; dx[b] += (ex / d) * f; dy[b] += (ey / d) * f;
    });
    var temp = (W / 8) * (1 - t / rounds) + 1;
    for (i = 0; i < n; i++) {
      dx[i] -= (x[i] - W / 2) * 0.04 * k / 40; dy[i] -= (y[i] - H / 2) * 0.04 * k / 40;  /* gravity */
      var len = Math.max(Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]), 0.01), step = Math.min(len, temp);
      x[i] += (dx[i] / len) * step; y[i] += (dy[i] / len) * step;
    }
  }
  /* A portrait screen gets a portrait layout: swap the axes when the layout is wider than tall. */
  var box = svg.getBoundingClientRect();
  var spanX = Math.max.apply(null, x) - Math.min.apply(null, x), spanY = Math.max.apply(null, y) - Math.min.apply(null, y);
  if (box.width && box.height && box.width < box.height && spanX > spanY) { var swap = x; x = y; y = swap; }
  groups.forEach(function (g) {
    var i = +g.getAttribute("data-i");
    g.setAttribute("transform", "translate(" + x[i].toFixed(1) + "," + y[i].toFixed(1) + ")");
  });
  lines.forEach(function (line) {
    var a = +line.getAttribute("data-a"), b = +line.getAttribute("data-b");
    line.setAttribute("x1", x[a].toFixed(1)); line.setAttribute("y1", y[a].toFixed(1));
    line.setAttribute("x2", x[b].toFixed(1)); line.setAttribute("y2", y[b].toFixed(1));
  });

  /* Fit: every node and its label inside the view. */
  var view;
  function fit() {
    /* The scale that leaves room on screen for the labels (190 px right) and the zoom buttons (56 px top). */
    var r = svg.getBoundingClientRect(), W = r.width || 1000, H = r.height || 700;
    var minX = Math.min.apply(null, x), spanX = Math.max.apply(null, x) - minX;
    var minY = Math.min.apply(null, y), spanY = Math.max.apply(null, y) - minY;
    var s = Math.max(spanX / Math.max(W - 230, 80), spanY / Math.max(H - 100, 80), 0.3);
    var w = W * s, h = H * s;
    view = { x: minX - 30 * s - (w - spanX - 220 * s) / 2, y: minY - 56 * s - (h - spanY - 100 * s) / 2, w: w, h: h };
    draw();
  }
  function draw() {
    svg.setAttribute("viewBox", [view.x, view.y, view.w, view.h].map(function (v) { return v.toFixed(1); }).join(" "));
    /* Nodes and labels keep their size on screen whatever the zoom and the width. */
    var r = svg.getBoundingClientRect(), scale = r.width && r.height ? Math.max(view.w / r.width, view.h / r.height) : 1;
    svg.style.setProperty("--gs", scale.toFixed(3));
  }
  fit();
  window.addEventListener("resize", draw);

  /* Hover or focus: the node and its neighbours stay, the rest fades. */
  function focusOn(i) {
    svg.classList.add("focus");
    groups.forEach(function (g) {
      var j = +g.getAttribute("data-i");
      g.classList.toggle("on", j === i || !!neighbours[i][j]);
    });
    lines.forEach(function (line) {
      var a = +line.getAttribute("data-a"), b = +line.getAttribute("data-b");
      line.classList.toggle("on", a === i || b === i);
    });
  }
  function clear() { svg.classList.remove("focus"); }
  groups.forEach(function (g) {
    var i = +g.getAttribute("data-i");
    g.addEventListener("mouseenter", function () { focusOn(i); });
    g.addEventListener("mouseleave", clear);
    g.addEventListener("focus", function () { focusOn(i); });
    g.addEventListener("blur", clear);
  });

  /* Zoom with the wheel or the buttons, pan by dragging the background. */
  function zoom(factor, cx, cy) {
    var w = Math.min(Math.max(view.w * factor, 120), 6000), scale = w / view.w;
    cx = cx === undefined ? view.x + view.w / 2 : cx; cy = cy === undefined ? view.y + view.h / 2 : cy;
    view = { x: cx - (cx - view.x) * scale, y: cy - (cy - view.y) * scale, w: w, h: view.h * scale };
    draw();
  }
  function point(event) {
    var r = svg.getBoundingClientRect();
    return { x: view.x + ((event.clientX - r.left) / r.width) * view.w, y: view.y + ((event.clientY - r.top) / r.height) * view.h };
  }
  svg.addEventListener("wheel", function (event) {
    event.preventDefault();
    var p = point(event);
    zoom(event.deltaY > 0 ? 1.12 : 1 / 1.12, p.x, p.y);
  }, { passive: false });
  var drag = null;
  svg.addEventListener("pointerdown", function (event) {
    if (event.target.closest && event.target.closest(".node")) return;
    drag = { x: event.clientX, y: event.clientY, view: view };
    svg.classList.add("dragging");
    if (svg.setPointerCapture) svg.setPointerCapture(event.pointerId);
  });
  svg.addEventListener("pointermove", function (event) {
    if (!drag) return;
    var r = svg.getBoundingClientRect();
    view = { x: drag.view.x - ((event.clientX - drag.x) / r.width) * drag.view.w,
             y: drag.view.y - ((event.clientY - drag.y) / r.height) * drag.view.h, w: drag.view.w, h: drag.view.h };
    draw();
  });
  function stop() { drag = null; svg.classList.remove("dragging"); }
  svg.addEventListener("pointerup", stop);
  svg.addEventListener("pointercancel", stop);
  var zin = document.getElementById("zoom-in"), zout = document.getElementById("zoom-out"), zfit = document.getElementById("zoom-fit");
  if (zin) zin.addEventListener("click", function () { zoom(1 / 1.25); });
  if (zout) zout.addEventListener("click", function () { zoom(1.25); });
  if (zfit) zfit.addEventListener("click", fit);
  svg.setAttribute("data-laid-out", "1");
})();
