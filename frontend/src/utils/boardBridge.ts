/**
 * 洞察板桥接脚本 / Insight Board bridge script
 *
 * 板渲染在 `sandbox="allow-scripts"`（**不给** allow-same-origin）的 iframe 里，
 * 文档落入 opaque origin：父窗口读不到它的 DOM，它也读不到宿主的 DOM/localStorage，
 * 双向都只能走 postMessage。因此 v-html 时代挂在父级的一切委托逻辑必须搬进这里。
 *
 * 协议（5 类，见 docs/insight-board-raw-html-plan.md §4.3）：
 *   iframe → 父：ib:seek {ms} | ib:hover {id,title,top,right} | ib:resize {height} | ib:mermaid {req,src}
 *   父 → iframe：ib:theme {vars,dark} | ib:mermaid:ok {req,svg} | ib:mermaid:err {req,message}
 *
 * ⚠️ 本脚本与磁盘上的板文件无关：它只在内存里随 srcdoc 拼接，绝不写回 data/tasks/。
 * ⚠️ 板内 <script> 是 CLI 的合法产物，因此这里不屏蔽脚本，只屏蔽越界（sandbox + Origin 守卫负责）。
 */

/** sandbox 取值：一旦与 allow-same-origin 同时出现，Origin 守卫与 opaque origin 全部失效 */
export const BOARD_SANDBOX = 'allow-scripts'

/**
 * 桥接脚本正文（纯 ES5 风格字符串，不使用反引号插值，避免与外层模板冲突）。
 * mermaid 首词白名单与后端 core/insight_board.py:_MERMAID_TYPES 同源，改一处须同步另一处。
 */
export const BOARD_BRIDGE_SCRIPT = `
(function () {
  'use strict';
  var MERMAID_TYPES = ['flowchart', 'graph', 'sequenceDiagram', 'stateDiagram-v2',
                       'stateDiagram', 'mindmap', 'timeline'];
  var DIRECTIVE = /^%%\\{.*\\}%%\\s*$/;
  var seq = 0, pending = {}, lastH = 0, lastW = 0, lastDark = null;

  function post(type, payload) {
    var msg = { __ib: type };
    if (payload) { for (var k in payload) { if (Object.prototype.hasOwnProperty.call(payload, k)) msg[k] = payload[k]; } }
    try { parent.postMessage(msg, '*'); } catch (e) { /* 宿主不可达时静默 */ }
  }

  function mermaidSource(pre) {
    var t = (pre.textContent || '').replace(/^\\s+|\\s+$/g, '');
    return t ? t : null;
  }

  /** 按形态识别 mermaid：首个非 %%{ }%% 指令行的首词命中图类型白名单（不认类名） */
  function isMermaidPre(pre) {
    var src = mermaidSource(pre);
    if (!src) return false;
    var lines = src.split('\\n');
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].replace(/^\\s+|\\s+$/g, '');
      if (!line || DIRECTIVE.test(line)) continue;
      var first = line.split(/\\s+/)[0];
      return MERMAID_TYPES.indexOf(first) >= 0;
    }
    return false;
  }

  function renderMermaids() {
    var pres = document.querySelectorAll('pre');
    for (var i = 0; i < pres.length; i++) {
      var pre = pres[i];
      if (pre.getAttribute('data-ib-done') === '1') continue;
      if (!isMermaidPre(pre)) continue;
      var src = mermaidSource(pre);
      if (!src) continue;
      pre.setAttribute('data-ib-done', '1');
      (function (p, code) {
        var req = 'r' + (++seq);
        pending[req] = p;
        post('ib:mermaid', { req: req, src: code });
      })(pre, src);
    }
    measure();
  }

  /**
   * 深浅色切换后重画图：主题变量只能影响板自己的 CSS，渲好的 SVG 已经把颜色写死在节点里。
   * 旧 v-html 容器有 rethemeMermaidBlocks，换成 iframe 后那一层整体退役了，
   * 不补就会「板底跟了主题、图仍是上一套明暗」。
   * 保留 <pre> 节点不删（只收起），回退时重走一次请求即可拿新主题的 SVG。
   */
  function retriggerMermaid() {
    var pres = document.querySelectorAll('pre');
    for (var i = 0; i < pres.length; i++) {
      var pre = pres[i];
      if (pre.getAttribute('data-ib-done') !== '1') continue;
      var nxt = pre.nextElementSibling;
      if (nxt && (nxt.className === 'ib-mermaid-box' || nxt.className === 'ib-mermaid-err')) {
        nxt.parentNode.removeChild(nxt);
      }
      pre.style.display = '';
      pre.removeAttribute('data-ib-done');
    }
    renderMermaids();
  }

  function applySvg(p, svg) {
    var box = document.createElement('div');
    box.setAttribute('class', 'ib-mermaid-box');
    box.setAttribute('style', 'display:flex;justify-content:center;padding:4px 0;overflow-x:auto;');
    box.innerHTML = svg;
    var s = box.querySelector('svg');
    if (s) { s.removeAttribute('width'); s.setAttribute('style', 'max-width:100%;height:auto;'); }
    // 不替换 <pre>（替换后就拿不到源码、无法随主题重画）：收起它、图排在它后面
    p.style.display = 'none';
    p.parentNode.insertBefore(box, p.nextSibling);
    measure();
  }

  function applyErr(p, message) {
    var err = document.createElement('div');
    err.setAttribute('class', 'ib-mermaid-err');
    err.setAttribute('style', 'color:#b45309;font-size:12px;padding:6px;border:1px dashed #b45309;border-radius:6px;word-break:break-all;');
    err.textContent = 'mermaid: ' + (message || 'render failed');
    p.parentNode.insertBefore(err, p.nextSibling);
    measure();
  }

  /**
   * 高度上报：srcdoc iframe 不自适应，父侧据此设 style.height。
   * 只量 body 的内容高度，**不量 documentElement.scrollHeight/offsetHeight**：
   * 后者等于 iframe 视口高度，一旦父侧把 iframe 拉高就回灌成更大的值、永不回落
   * （首屏卡在 1787px、reload 才恢复的偏差正是这个自馈环）。body 高度由内容决定、
   * 不随视口拉伸，量它才能真正跟踪内容（包括 mermaid 异步注入后的二次变矮）。
   */
  /**
   * 以「文档序最前」注入样式（同优先级下后来者胜，因此板自己的规则始终覆盖我们）。
   * 已存在则原地更新文本，主题切换走同一条路径，不重复插入节点。
   */
  function injectFirst(id, css) {
    var host = document.head || document.documentElement;
    var el = document.getElementById(id);
    if (!el) {
      el = document.createElement('style');
      el.id = id;
      host.insertBefore(el, host.firstChild);
    }
    el.textContent = css;
    return el;
  }

  function measure() {
    var b = document.body;
    if (!b) return;
    var h = Math.max(b.scrollHeight || 0, b.offsetHeight || 0,
                    Math.ceil(b.getBoundingClientRect().height) || 0);
    if (h && Math.abs(h - lastH) > 1) { lastH = h; post('ib:resize', { height: h }); }
  }

  /**
   * 宽度变化重测：父侧按我们上报的高度设 iframe，板变窄时内容会变高，
   * 而 body 的 ResizeObserver 只关心内容尺寸驱动的变化、列宽拖拽不一定触发它
   * （实测 531→437 后 frameH 恒为 6859，板底被裁）。因此补接 window resize。
   * 只在**宽度真的变了**时才重测：父侧改 iframe 高度同样会触发子文档的 resize，
   * 若板内用了 vh 单位就会形成高度自馈环（与量 documentElement 同类陷阱）。
   */
  function onWinResize() {
    if (window.innerWidth === lastW) return;
    lastW = window.innerWidth;
    measure();
  }

  /** 悬停上报：命中顶层 [data-ib-id] 节则回传其相对板文档左上角的偏移（父侧加 iframe 偏移定位按钮） */
  function hover(e) {
    var t = e.target;
    while (t && t !== document.body && !(t.getAttribute && t.getAttribute('data-ib-id'))) t = t.parentNode;
    if (!t || t === document.body || !t.getAttribute || !t.getAttribute('data-ib-id')) {
      post('ib:hover', { id: '', title: '', top: 0, right: 0 });
      return;
    }
    var sr = t.getBoundingClientRect();
    post('ib:hover', {
      id: t.getAttribute('data-ib-id') || '',
      title: (t.getAttribute('data-ib-title') || '').replace(/^\\s+|\\s+$/g, ''),
      top: Math.max(sr.top + window.scrollY, 0),
      right: Math.max(document.documentElement.scrollWidth - (sr.right + window.scrollX), 0)
    });
  }

  function click(e) {
    var t = e.target;
    while (t && t !== document.body && !(t.getAttribute && t.getAttribute('data-seek-ms') !== null)) t = t.parentNode;
    if (!t || t === document.body || !t.getAttribute) return;
    var raw = t.getAttribute('data-seek-ms');
    if (raw === null || raw === '') return;
    var ms = Number(raw);
    if (isFinite(ms) && ms >= 0) { e.preventDefault(); post('ib:seek', { ms: ms }); }
  }

  window.addEventListener('message', function (e) {
    var d = e.data;
    if (!d || typeof d !== 'object' || !d.__ib) return;
    if (d.__ib === 'ib:theme') {
      var de = document.documentElement;
      /*
       * 令牌注入必须走「低优先级样式表」（插到 head 最前），不能用 inline style 逐条覆盖：
       * inline 的优先级高于板自己的 :root 规则，会把板自定义的同名令牌逐条打穿——板只重定义了
       * 8 个变量里的 4 个时，剩下 4 个仍是板自己的值，结果就是「背景跟宿主、文字跟板」的
       * 半混合状态（实测宿主浅色主题下 body 变白而 --ink 仍是 #e8edf6，页头白底白字不可读）。
       * 插到最前 = 板后续样式表里的同名声明后来者胜：板定义了就听板的，没定义才由宿主兜底。
       */
      var decls = '';
      if (d.vars) { for (var k in d.vars) {
        if (Object.prototype.hasOwnProperty.call(d.vars, k) && k !== '__ib_reset') decls += k + ':' + d.vars[k] + ';';
      } }
      injectFirst('ib-theme-vars', ':root{' + decls + '}');
      de.setAttribute('data-theme', d.dark ? 'dark' : 'light');
      // 几何兜底同样让板自己的规则优先（它写了 box-sizing 就不需要我们替它决定）
      injectFirst('ib-reset', (d.vars && d.vars.__ib_reset) || '');
      // 明暗真变了才重画图（初次下发 lastDark=null 时图已在首屏渲染流程里）
      var dark = !!d.dark;
      if (lastDark !== null && dark !== lastDark) retriggerMermaid();
      lastDark = dark;
      requestAnimationFrame(measure);
    } else if (d.__ib === 'ib:mermaid:ok' || d.__ib === 'ib:mermaid:err') {
      var p = pending[d.req];
      if (!p) return;
      delete pending[d.req];
      if (d.__ib === 'ib:mermaid:ok') { try { applySvg(p, d.svg || ''); } catch (err) { /* 保持源码可见 */ } }
      else applyErr(p, d.message);
    }
  });

  function boot() {
    lastW = window.innerWidth;
    document.addEventListener('mousemove', hover);
    document.addEventListener('click', click);
    window.addEventListener('resize', onWinResize);
    if (window.ResizeObserver) {
      try { new ResizeObserver(measure).observe(document.body); } catch (e) { /* 退化到手动测量 */ }
    }
    renderMermaids();
    measure();
    // mermaid SVG 由父侧异步回传后就地替换，尺寸会二/三次变化：多补几次延后重测，
    // 覆盖字体加载、图注入、布局稳定三个时机，避免首屏高度一次测早了定死
    [80, 250, 600].forEach(function (ms) { setTimeout(measure, ms); });
    if (document.fonts && document.fonts.ready && document.fonts.ready.then) {
      document.fonts.ready.then(function () { measure(); });
    }
    post('ib:ready', {});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
`

/**
 * srcdoc 组装：片段（存量板/无外壳产物）补最小主体骨架，完整文档原样使用。
 *
 * 只补两行**几何地板**（body margin + 100% 宽度）：没有它们，浏览器默认的 body margin
 * 会在 iframe 里凭空多出滚动条，而 iframe 高度又只能靠内容上报——这是容器问题不是排版问题。
 * 板自己写了 body 样式时，它的规则在后（同优先级后来者胜）。
 */
export function composeBoardDoc(html: string): string {
  const floor = '<style>html{width:100%}body{margin:0;min-width:100%}</style>'
  const doc = /<!DOCTYPE|<html[\s>]/i.test(html)
    ? html
    : `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">`
      + `<meta name="viewport" content="width=device-width, initial-scale=1"></head><body>${html}</body></html>`
  const withFloor = doc.includes('</head>')
    ? doc.replace('</head>', floor + '</head>')
    : doc + floor
  return `${withFloor}<script>${BOARD_BRIDGE_SCRIPT}</script>`
}
