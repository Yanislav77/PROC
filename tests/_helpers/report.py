import html as _html
import json
from datetime import datetime
from http import HTTPStatus
from pathlib import Path

_DB_CELL_MAX_LEN    = 200  # chars, DB table cell content truncation
_REDIS_CELL_MAX_LEN = 300  # chars, Redis field value truncation

_report_file = None
_http_captures: dict = {}
_call_reports:  dict = {}
_tc_ids:        dict = {}
_test_counter = 0

_REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"


def _make_report_suffix(config) -> str:
    args = [a for a in config.args if not a.startswith("-")]
    if not args:
        return "all"
    raw = args[0].replace("\\", "/")
    if "::" in raw:
        file_part, test_part = raw.split("::", 1)
        stem = Path(file_part).stem
        test_clean = test_part.replace("[", "_").replace("]", "")
        return f"{stem}__{test_clean}"
    stem = Path(raw).stem
    return "all" if stem in ("tests", "test", ".") or not stem else stem


def _esc(text) -> str:
    return _html.escape(str(text))


def _fmt_body_plain(raw) -> str:
    if not raw:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        return json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
    except (ValueError, TypeError):
        return str(raw)


def _fmt_body(raw) -> str:
    if not raw:
        return "    (no body)"
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        lines = json.dumps(json.loads(raw), ensure_ascii=False, indent=2).splitlines()
        return "\n".join("    " + line for line in lines)
    except (ValueError, TypeError):
        return "    " + str(raw)


def _status_phrase(code: int) -> str:
    try:
        return HTTPStatus(code).phrase
    except ValueError:
        return ""


def _sc_class(code: int) -> str:
    if 200 <= code < 300:
        return "s2xx"
    if 400 <= code < 500:
        return "s4xx"
    return "s5xx"


def _render_http_block(f, prep, resp, title, css_class, indent="    ") -> None:
    phrase = _status_phrase(resp.status_code)
    sc = _sc_class(resp.status_code)
    i = indent
    f.write(f'{i}<div class="http-block">\n')
    f.write(f'{i}  <div class="http-block-title {css_class}">{title}</div>\n')
    f.write(f'{i}  <div class="http-block-body">\n')
    f.write(f'{i}    <div class="section-label">Request</div>\n')
    f.write(f'{i}    <p class="http-line"><span class="method">{_esc(prep.method)}</span>'
            f' <span class="url">{_esc(prep.url)}</span></p>\n')
    if prep.headers:
        headers_text = "\n".join(f"{k}: {v}" for k, v in prep.headers.items())
        f.write(f'{i}    <pre class="headers">{_esc(headers_text)}</pre>\n')
    body_text = _fmt_body_plain(prep.body)
    if body_text:
        f.write(f'{i}    <pre class="body">{_esc(body_text)}</pre>\n')
    f.write(f'{i}    <div class="section-label">Response</div>\n')
    f.write(f'{i}    <p class="http-line"><span class="status-code {sc}">'
            f'{resp.status_code} {_esc(phrase)}</span></p>\n')
    resp_text = _fmt_body_plain(resp.text)
    if resp_text:
        f.write(f'{i}    <pre class="body">{_esc(resp_text)}</pre>\n')
    f.write(f'{i}  </div>\n{i}</div>\n')


def _render_db_section(f, db_data: list, indent="    ") -> None:
    if not db_data:
        return
    i = indent
    f.write(f'{i}<div class="section-label">Database</div>\n')
    f.write(f'{i}<div class="db-section">\n')
    grouped: dict = {}
    for record in db_data:
        grouped.setdefault(record["db"], []).append(record)
    order = [db for db in ("secure", "support") if db in grouped]
    order += [db for db in grouped if db not in order]
    for db_name in order:
        safe = _esc(db_name)
        f.write(f'{i}  <div class="db-group">\n')
        f.write(f'{i}    <div class="db-group-header {safe}">{safe}</div>\n')
        f.write(f'{i}    <div class="db-group-body">\n')
        for record in grouped[db_name]:
            f.write(f'{i}      <div class="db-table-block">\n')
            f.write(f'{i}        <div class="db-table-name">{_esc(record["table"])}</div>\n')
            f.write(f'{i}        <div class="db-block">\n')
            f.write(f'{i}          <table class="db-table"><thead><tr>\n')
            for col in record["columns"]:
                f.write(f'{i}            <th>{_esc(col)}</th>\n')
            f.write(f'{i}          </tr></thead><tbody>\n')
            for row in record["rows"]:
                f.write(f'{i}          <tr>\n')
                for val in row:
                    if val is None:
                        cell = "<span style='color:#555'>NULL</span>"
                    else:
                        s = str(val)
                        cell = _esc(s[:_DB_CELL_MAX_LEN] + "…" if len(s) > _DB_CELL_MAX_LEN else s)
                    f.write(f'{i}            <td>{cell}</td>\n')
                f.write(f'{i}          </tr>\n')
            f.write(f'{i}          </tbody></table>\n')
            f.write(f'{i}        </div>\n{i}      </div>\n')
        f.write(f'{i}    </div>\n{i}  </div>\n')
    f.write(f'{i}</div>\n')


def _render_redis_section(f, redis_entry: dict, indent="    ") -> None:
    if not redis_entry:
        return
    i = indent
    api_status = redis_entry.get("api_status") or ""
    rdata      = redis_entry.get("data", {})
    r_status   = rdata.get("status", "")
    match      = (api_status == r_status) if (api_status and r_status) else None
    rbadge     = ('<span class="redis-match">✓ match</span>' if match is True else
                  '<span class="redis-mismatch">✗ mismatch</span>' if match is False else "")
    f.write(f'{i}<div class="section-label">Redis</div>\n')
    f.write(f'{i}<div class="db-section">\n')
    f.write(f'{i}  <div class="db-group">\n')
    f.write(f'{i}    <div class="db-group-header Redis">'
            f'{"API: <b>" + _esc(api_status) + "</b>&nbsp;&nbsp;" if api_status else ""}'
            f'{"Redis: <b>" + _esc(r_status) + "</b>" if r_status else ""}'
            f'{"&nbsp;&nbsp;" + rbadge if rbadge else ""}'
            f'</div>\n')
    f.write(f'{i}    <div class="db-group-body">\n')
    f.write(f'{i}      <div class="db-table-block"><div class="db-block">\n')
    f.write(f'{i}        <table class="db-table"><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>\n')
    for k, v in rdata.items():
        s = str(v)
        cell = _esc(s[:_REDIS_CELL_MAX_LEN] + "…" if len(s) > _REDIS_CELL_MAX_LEN else s)
        f.write(f'{i}          <tr><td>{_esc(k)}</td><td>{cell}</td></tr>\n')
    f.write(f'{i}        </tbody></table>\n')
    f.write(f'{i}      </div></div>\n')
    f.write(f'{i}    </div>\n{i}  </div>\n')
    f.write(f'{i}</div>\n')


def _write_report_entry(nodeid: str, status: str, error, ungrouped: list, tc_id: str = "", groups: list = None) -> None:
    global _test_counter
    _test_counter += 1
    idx = _test_counter
    f = _report_file

    if status == "PASSED":
        css, badge = "passed", "✓ PASSED"
    elif status == "SKIPPED":
        css, badge = "skipped", "⊘ SKIPPED"
    else:
        css, badge = "failed", "✗ FAILED"

    f.write(f'<div class="panel {css}" id="p{idx}" data-name="{_esc(nodeid)}" data-status="{css}" data-tcid="{_esc(tc_id)}">\n')
    f.write(f'  <div class="panel-header">\n')
    f.write(f'    <span class="badge">{badge}</span>\n')
    if tc_id:
        f.write(f'    <span class="tc-id">{_esc(tc_id)}</span>\n')
    f.write(f'    <span class="panel-name">{_esc(nodeid)}</span>\n')
    f.write(f'  </div>\n')
    f.write(f'  <div class="panel-body">\n')

    if error:
        f.write('    <div class="section-label">Error</div>\n')
        f.write(f'    <div class="error-block"><pre>{_esc(error)}</pre></div>\n')

    for prep, resp, title, css_class in (ungrouped or []):
        _render_http_block(f, prep, resp, title, css_class)

    for grp in (groups or []):
        title       = grp.get("title", "")
        tr_id       = grp.get("tr_id")
        css_class   = grp.get("css_class", "create")
        http_blocks = grp.get("http_blocks", [])
        db_data     = grp.get("db_data") or []
        redis_entry = grp.get("redis")

        final_status = ""
        for _, resp, lbl, _ in reversed(http_blocks):
            if lbl.startswith("Статус"):
                try:
                    final_status = resp.json().get("status", "")
                except Exception:
                    pass
                break

        meta = f"tr_id: {tr_id}" if tr_id is not None else ""
        status_span = (f'<span class="tx-status s2xx">{_esc(final_status)}</span>'
                       if final_status else "")

        f.write(f'  <details class="tx-group">\n')
        f.write(f'    <summary>'
                f'<span class="tx-title {css_class}">{_esc(title)}</span>'
                f'{" · <span class=\"tx-meta\">" + _esc(meta) + "</span>" if meta else ""}'
                f'{" · " + status_span if status_span else ""}'
                f'</summary>\n')
        f.write(f'    <div class="tx-body">\n')
        for prep, resp, lbl, cc in http_blocks:
            _render_http_block(f, prep, resp, lbl, cc, indent="      ")
        _render_db_section(f, db_data, indent="      ")
        _render_redis_section(f, redis_entry, indent="      ")
        f.write(f'    </div>\n  </details>\n')

    f.write('  </div>\n</div>\n')
    f.flush()


def pytest_configure(config):
    global _report_file, _test_counter
    _test_counter = 0
    config.addinivalue_line("markers", "tcid(id): test case identifier shown in HTML report")
    _REPORTS_DIR.mkdir(exist_ok=True)
    suffix = _make_report_suffix(config)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path = _REPORTS_DIR / f"{ts}_{suffix}.html"
    _report_file = path.open("w", encoding="utf-8")
    _report_file.write(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Report — {_esc(suffix)}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#1a1a2e;color:#e0e0e0;display:flex;flex-direction:column;height:100vh;overflow:hidden}}
.top-bar{{background:#12122a;border-bottom:1px solid #2a2a4a;padding:10px 20px;flex-shrink:0;display:flex;align-items:center;gap:16px}}
.top-bar h1{{color:#fff;font-size:1.1em;white-space:nowrap}}
.top-bar .meta{{color:#666;font-size:.8em}}
#summary{{display:flex;gap:14px;font-size:.88em;margin-left:auto;align-items:center;white-space:nowrap}}
.sum-p{{color:#4caf50;font-weight:bold}}
.sum-f{{color:#f44336;font-weight:bold}}
.sum-s{{color:#e8e860;font-weight:bold}}
.sum-t{{color:#777}}
.layout{{display:flex;flex:1;overflow:hidden}}
.sidebar{{width:290px;background:#12122a;border-right:1px solid #2a2a4a;overflow-y:auto;flex-shrink:0;padding:6px 0}}
.nav-item{{padding:7px 12px 7px 14px;cursor:pointer;border-left:3px solid transparent;font-family:'Consolas',monospace;font-size:.76em;color:#999;line-height:1.4;word-break:break-all;user-select:none;display:flex;align-items:flex-start;gap:6px}}
.nav-item:hover{{background:#1a1a38;color:#ddd}}
.nav-item.active{{background:#1e1e3a;color:#fff;border-left-color:#5c7aaa}}
.nav-badge{{flex-shrink:0;margin-top:1px}}
.nav-item.passed .nav-badge{{color:#4caf50}}
.nav-item.failed .nav-badge{{color:#f44336}}
.nav-item.skipped .nav-badge{{color:#e8e860}}
.main{{flex:1;overflow-y:auto;padding:20px}}
.panel{{display:none}}
.panel.active{{display:block}}
.panel-header{{display:flex;align-items:center;gap:12px;padding:10px 14px;border-radius:6px 6px 0 0}}
.panel.passed .panel-header{{background:#1b3a1b;border:1px solid #2d4a2d;border-bottom:none}}
.panel.failed .panel-header{{background:#3a1b1b;border:1px solid #4a2020;border-bottom:none}}
.panel.skipped .panel-header{{background:#2a2a1b;border:1px solid #4a4a20;border-bottom:none}}
.badge{{font-size:.75em;font-weight:bold;padding:2px 8px;border-radius:10px;flex-shrink:0}}
.panel.passed .badge{{background:#2e7d32;color:#a5d6a7}}
.panel.failed .badge{{background:#b71c1c;color:#ffcdd2}}
.panel.skipped .badge{{background:#5a5a00;color:#e8e860}}
.panel-name{{font-family:'Consolas',monospace;font-size:.88em;color:#ddd;word-break:break-all}}
.panel-body{{padding:14px 16px;background:#16213e;border-radius:0 0 6px 6px}}
.panel.passed .panel-body{{border:1px solid #2d4a2d;border-top:none}}
.panel.failed .panel-body{{border:1px solid #4a2020;border-top:none}}
.panel.skipped .panel-body{{border:1px solid #4a4a20;border-top:none}}
.section-label{{font-size:.72em;font-weight:bold;letter-spacing:.08em;color:#5c7aaa;text-transform:uppercase;margin:12px 0 6px}}
.section-label:first-child{{margin-top:0}}
.http-line{{font-family:monospace;font-size:.85em;margin-bottom:6px}}
.method{{color:#82aaff;font-weight:bold}}
.url{{color:#c3e88d}}
.status-code{{font-family:monospace;font-weight:bold;font-size:.85em}}
.s2xx{{color:#4caf50}}.s4xx{{color:#ff9800}}.s5xx{{color:#f44336}}
.tc-id{{font-family:'Consolas',monospace;font-size:.72em;font-weight:bold;color:#e0b060;background:#2a1f00;border:1px solid #4a3800;padding:1px 7px;border-radius:4px;flex-shrink:0}}
.nav-tcid{{font-family:'Consolas',monospace;font-size:.72em;color:#c9963a;flex-shrink:0;white-space:nowrap}}
pre.body{{background:#0d1117;border:1px solid #2a2a4a;border-radius:4px;padding:10px 12px;
  font-family:'Consolas',monospace;font-size:.82em;color:#cdd9e5;
  white-space:pre-wrap;word-break:break-all;max-height:340px;overflow-y:auto;margin:0}}
pre.headers{{background:#0a0f1a;border:1px solid #1e2a3a;border-radius:4px;padding:8px 12px;
  font-family:'Consolas',monospace;font-size:.78em;color:#7a9abf;
  white-space:pre-wrap;word-break:break-all;max-height:160px;overflow-y:auto;margin:0 0 6px}}
.error-block{{background:#1a0a0a;border-left:3px solid #f44336;border-radius:0 4px 4px 0;padding:12px;margin-top:8px}}
.error-block pre{{color:#ff8a80;font-size:.82em;white-space:pre-wrap;word-break:break-all;
  max-height:400px;overflow-y:auto;margin:0}}
.http-block{{border:1px solid #2a2a4a;border-radius:6px;margin-top:12px;overflow:hidden}}
.http-block-title{{background:#1a1a38;padding:6px 12px;font-size:.75em;font-weight:bold;letter-spacing:.07em;text-transform:uppercase;border-bottom:1px solid #2a2a4a}}
.http-block-title.create{{color:#82aaff}}.http-block-title.operation{{color:#ffb74d}}.http-block-title.poll{{color:#c3e88d}}
.http-block-body{{padding:10px 14px}}
details.tx-group{{border:1px solid #2a2a4a;border-radius:6px;margin-top:12px;overflow:hidden}}
details.tx-group>summary{{background:#1a1a38;padding:9px 14px;cursor:pointer;list-style:none;display:flex;align-items:center;gap:10px;user-select:none;border-bottom:1px solid transparent}}
details.tx-group>summary::-webkit-details-marker{{display:none}}
details.tx-group>summary::before{{content:'▶';font-size:.6em;color:#5c7aaa;flex-shrink:0;transition:transform .15s}}
details[open].tx-group>summary{{border-bottom-color:#2a2a4a}}
details[open].tx-group>summary::before{{transform:rotate(90deg)}}
.tx-title{{font-weight:bold;text-transform:uppercase;letter-spacing:.06em;font-size:.75em}}
.tx-title.create{{color:#82aaff}}.tx-title.operation{{color:#ffb74d}}.tx-title.poll{{color:#c3e88d}}
.tx-meta{{color:#666;font-size:.78em;font-family:'Consolas',monospace}}
.tx-status{{font-family:'Consolas',monospace;font-size:.78em;font-weight:bold;color:#cdd9e5}}
.tx-body{{padding:10px 14px;background:#13192e}}
.db-section{{margin-top:12px}}
.db-group{{border-radius:6px;margin-top:10px;overflow:hidden;border:1px solid #2a2a4a}}
.db-group-header{{padding:7px 14px;font-size:.76em;font-weight:bold;letter-spacing:.08em;text-transform:uppercase}}
.db-group-header.secure{{background:#1a1333;color:#c9a8ff;border-bottom:1px solid #3a2a5a}}
.db-group-header.support{{background:#0f1f2a;color:#82aaff;border-bottom:1px solid #1e3a4a}}
.db-group-header.Redis{{background:#1a1a0a;color:#e8cc60;border-bottom:1px solid #3a3a10;font-weight:normal;font-size:.8em;letter-spacing:.03em}}
.redis-match{{color:#4caf50;font-weight:bold;margin-left:8px}}
.redis-mismatch{{color:#f44336;font-weight:bold;margin-left:8px}}
.db-group-body{{padding:10px 12px;display:flex;flex-direction:column;gap:10px}}
.db-table-block{{border:1px solid #222240;border-radius:4px;overflow:hidden}}
.db-table-name{{background:#16163a;padding:4px 10px;font-family:'Consolas',monospace;font-size:.74em;color:#aaa;border-bottom:1px solid #222240}}
.db-block{{max-height:220px;overflow:auto}}
.db-table{{border-collapse:collapse;font-family:'Consolas',monospace;font-size:.78em;width:100%}}
.db-table th{{background:#1e1433;color:#c9a8ff;padding:4px 10px;text-align:left;border:1px solid #3a2a5a;white-space:nowrap;position:sticky;top:0}}
.db-table td{{padding:4px 10px;border:1px solid #2a1e40;color:#cdd9e5;vertical-align:top;word-break:break-all;max-width:360px}}
.db-table tr:nth-child(even) td{{background:#130f1e}}
</style>
</head>
<body>
<div class="top-bar">
  <h1>Test Report</h1>
  <span class="meta">Suite: <b>{_esc(suffix)}</b> &nbsp;|&nbsp; {started}</span>
  <div id="summary"></div>
</div>
<div class="layout">
  <div class="sidebar" id="sidebar"></div>
  <div class="main" id="main">
""")
    _report_file.flush()


def pytest_unconfigure(config):
    global _report_file
    if _report_file:
        finished = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _report_file.write(f"""
  </div>
</div>
<script>
(function(){{
  function parseTcid(t){{
    if(!t)return['ZZZZ',99999];
    var m=t.match(/^([A-Z0-9]+)-(\\d+)$/);
    return m?[m[1],parseInt(m[2])]:[t,0];
  }}
  var main=document.getElementById('main');
  var sidebar=document.getElementById('sidebar');
  var panels=Array.from(document.querySelectorAll('.panel'));
  panels.sort(function(a,b){{
    var ta=parseTcid(a.dataset.tcid),tb=parseTcid(b.dataset.tcid);
    if(ta[0]!==tb[0])return ta[0]<tb[0]?-1:1;
    return ta[1]-tb[1];
  }});
  panels.forEach(function(p){{main.appendChild(p);}});
  var passed=0,failed=0,skipped=0,firstFailed=null,navItems=[];
  panels.forEach(function(p){{
    var st=p.dataset.status,nm=p.dataset.name;
    if(st==='passed')passed++;else if(st==='skipped')skipped++;else{{failed++;if(!firstFailed)firstFailed=p;}}
    var tcid=p.dataset.tcid;
    var item=document.createElement('div');
    item.className='nav-item '+st;
    item.innerHTML='<span class="nav-badge">'+(st==='passed'?'✓':st==='skipped'?'⊘':'✗')+'</span>'+(tcid?'<span class="nav-tcid">['+tcid+']</span> ':'')+nm;
    (function(panel,navItem){{
      navItem.onclick=function(){{
        panels.forEach(function(x){{x.classList.remove('active');}});
        navItems.forEach(function(x){{x.classList.remove('active');}});
        panel.classList.add('active');
        navItem.classList.add('active');
      }};
    }})(p,item);
    sidebar.appendChild(item);
    navItems.push(item);
  }});
  var toShow=firstFailed||panels[0];
  if(toShow){{
    toShow.classList.add('active');
    navItems[panels.indexOf(toShow)].classList.add('active');
  }}
  var total=passed+failed+skipped;
  document.getElementById('summary').innerHTML=
    '<span class="sum-p">✓ '+passed+' passed</span>'+
    (failed?'<span class="sum-f">&nbsp;&nbsp;✗ '+failed+' failed</span>':'')+
    (skipped?'<span class="sum-s">&nbsp;&nbsp;⊘ '+skipped+' skipped</span>':'')+
    '<span class="sum-t">&nbsp;&nbsp;/ '+total+' total</span>';
  document.querySelector('.meta').innerHTML+=
    '&nbsp;|&nbsp; Finished: {finished}';
}})();
</script>
</body>
</html>
""")
        _report_file.close()
        _report_file = None


def pytest_collection_finish(session) -> None:
    """Warn about duplicate @pytest.mark.tcid values after collection."""
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for item in session.items:
        marker = item.get_closest_marker("tcid")
        if not marker:
            continue
        tc_id = marker.args[0]
        if tc_id in seen:
            duplicates.append(f"  {tc_id}: {seen[tc_id]}  vs  {item.nodeid}")
        else:
            seen[tc_id] = item.nodeid
    if duplicates:
        msg = "Duplicate @pytest.mark.tcid values found:\n" + "\n".join(duplicates)
        import warnings
        warnings.warn(msg, stacklevel=2)


def pytest_runtest_logreport(report):
    if _report_file is None:
        return
    if report.when == "setup" and report.failed:
        tc_id = _tc_ids.get(report.nodeid, "")
        _write_report_entry(report.nodeid, "ERROR (setup failed)", str(report.longrepr), [], tc_id)
    elif report.when == "call":
        _call_reports[report.nodeid] = report
    elif report.when == "teardown":
        call = _call_reports.pop(report.nodeid, None)
        if call is None:
            return
        ungrouped, groups = _http_captures.pop(report.nodeid, ([], []))
        if call.passed:
            status = "PASSED"
        elif call.skipped:
            status = "SKIPPED"
        else:
            status = "FAILED"
        error = str(call.longrepr) if call.failed or call.skipped else None
        tc_id = _tc_ids.get(report.nodeid, "")
        _write_report_entry(report.nodeid, status, error, ungrouped, tc_id, groups)
