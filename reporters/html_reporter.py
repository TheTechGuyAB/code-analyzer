"""HTML reporter — polished interactive dark-mode report with cost tracking."""

class HtmlReporter:
    def render(self, report: dict) -> str:
        meta = report.get("meta", {})
        stack = report.get("stack", {})
        findings = report.get("findings", [])
        summary = report.get("summary", {})
        cost = meta.get("cost", {})

        critical = [f for f in findings if f.get("severity") == "critical"]
        warnings = [f for f in findings if f.get("severity") == "warning"]
        infos = [f for f in findings if f.get("severity") == "info"]

        score = summary.get("health_score", 0)
        sc = "#e74c3c" if score < 40 else "#f39c12" if score < 70 else "#27ae60"

        source = meta.get("source") or {}
        src_str = source.get("full_name", source.get("path", meta.get("root_path", "")))
        if source.get("branch"): src_str += f" @ {source['branch']}"
        if source.get("commit_sha"): src_str += f" ({source['commit_sha']})"

        total_cost = cost.get("total_cost_usd", 0)
        cost_rows = "".join(
            f'<tr><td>{c["phase"]}</td><td>{c["provider"]}</td><td>{c["model"]}</td>'
            f'<td>${c["cost_usd"]:.4f}</td><td>{c["latency_ms"]}ms</td></tr>'
            for c in cost.get("calls", [])
        )
        cost_html = f"""<details class="cost-det"><summary>Pipeline cost: ${total_cost:.4f} ({len(cost.get('calls',[]))} calls)</summary>
<table class="ct2"><tr><th>Phase</th><th>Provider</th><th>Model</th><th>Cost</th><th>Latency</th></tr>{cost_rows}</table></details>""" if cost_rows else ""

        stk_cards = []
        for l in stack.get("languages", []):
            stk_cards.append(f'<div class="sc"><div class="l">Language</div><div class="v">{self._e(l["name"])} {self._e(str(l.get("version","")))}</div></div>')
        for fw in stack.get("frameworks", []):
            stk_cards.append(f'<div class="sc"><div class="l">{self._e(fw.get("category","framework"))}</div><div class="v">{self._e(fw["name"])} {self._e(str(fw.get("version","")))}</div></div>')
        for db in stack.get("databases", []):
            stk_cards.append(f'<div class="sc"><div class="l">Database</div><div class="v">{self._e(db)}</div></div>')
        inf = stack.get("infrastructure", {})
        if inf.get("ci_cd"): stk_cards.append(f'<div class="sc"><div class="l">CI/CD</div><div class="v">{self._e(inf["ci_cd"])}</div></div>')
        if inf.get("containerized"): stk_cards.append('<div class="sc"><div class="l">Containers</div><div class="v">Docker</div></div>')

        prio_items = "".join(f"<li>{self._e(p)}</li>" for p in summary.get("top_priorities", []))
        str_items = "".join(f"<li>{self._e(s)}</li>" for s in summary.get("strengths", []))

        order = {"critical": 0, "warning": 1, "info": 2}
        sorted_f = sorted(findings, key=lambda f: order.get(f.get("severity", "info"), 3))
        f_html = []
        for f in sorted_f:
            sv = f.get("severity", "info")
            af = f.get("affected_files", [])
            ev = f.get("evidence", "")
            rec = self._e(f.get("recommendation", ""))
            eff = self._e(f.get("effort", ""))
            files_h = '<div class="lb">Files</div><div class="fs">' + "".join(f'<span class="ftag">{self._e(p)}</span>' for p in af[:8]) + '</div>' if af else ""
            ev_h = f'<div class="lb">Evidence</div><code>{self._e(ev)}</code>' if ev else ""
            rec_h = f'<div class="lb">Recommendation</div><div class="rec">{rec}</div>' if rec else ""
            f_html.append(f'''<div class="f sev-{sv}" data-s="{sv}"><div class="fh">
<span class="sb {sv}">{sv}</span><span class="fi">{self._e(f.get("id",""))}</span>
<span class="ft">{self._e(f.get("title",""))}</span>
{"<span class=fe>" + eff + "</span>" if eff else ""}
<span class="fg">&#x25b6;</span></div>
<div class="fb2"><p>{self._e(f.get("description",""))}</p>{files_h}{ev_h}{rec_h}
<div style="margin-top:.75rem;color:var(--td);font-size:.7rem">Agent: {self._e(f.get("agent",""))}</div></div></div>''')

        return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Codebase Analysis — {self._e(src_str)}</title>
<style>
:root{{--bg:#0f1117;--s:#1a1d27;--s2:#232733;--bd:#2d3140;--t:#e4e6ef;--td:#8b8fa3;--cr:#ff4757;--crb:rgba(255,71,87,.08);--wa:#ffa502;--wab:rgba(255,165,2,.08);--in:#3498db;--inb:rgba(52,152,219,.08);--ac:#6c5ce7;--gn:#2ed573}}
*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:'SF Mono','Cascadia Code','JetBrains Mono',monospace;background:var(--bg);color:var(--t);line-height:1.6;padding:2rem;max-width:1200px;margin:0 auto}}
.hdr{{border-bottom:1px solid var(--bd);padding-bottom:2rem;margin-bottom:2rem}}.hdr h1{{font-size:1.5rem;font-weight:600}}.hdr .meta{{color:var(--td);font-size:.78rem;margin-top:.5rem}}
.qb{{background:linear-gradient(135deg,rgba(108,92,231,.15),rgba(108,92,231,.05));border:1px solid rgba(108,92,231,.3);border-radius:8px;padding:1rem 1.25rem;margin-bottom:2rem;font-size:.85rem}}.qb span{{color:var(--ac);font-weight:600}}
.ss{{display:grid;grid-template-columns:auto 1fr;gap:2rem;align-items:center;margin-bottom:2rem;padding:1.5rem;background:var(--s);border-radius:12px;border:1px solid var(--bd)}}
.sr{{width:120px;height:120px;position:relative}}.sr svg{{transform:rotate(-90deg)}}.sr .vl{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:2rem;font-weight:700}}
.sd{{font-size:.85rem}}.sd .ct{{display:flex;gap:1.5rem;margin-bottom:1rem}}.ct .c{{display:flex;align-items:center;gap:.4rem}}.ct .d{{width:8px;height:8px;border-radius:50%}}.ct .d.cr{{background:var(--cr)}}.ct .d.wa{{background:var(--wa)}}.ct .d.in{{background:var(--in)}}
.sg{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.75rem;margin-bottom:2rem}}.sc{{background:var(--s);border:1px solid var(--bd);border-radius:8px;padding:.75rem 1rem;font-size:.8rem}}.sc .l{{color:var(--td);font-size:.68rem;text-transform:uppercase;letter-spacing:.05em}}.sc .v{{font-weight:600;margin-top:.2rem}}
.pr{{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:2rem}}@media(max-width:768px){{.pr{{grid-template-columns:1fr}}}}.pc{{background:var(--s);border:1px solid var(--bd);border-radius:8px;padding:1.25rem}}.pc h3{{font-size:.85rem;margin-bottom:.75rem;color:var(--td)}}.pc ol,.pc ul{{padding-left:1.25rem;font-size:.82rem}}.pc li{{margin-bottom:.4rem}}.pc.st li{{color:var(--gn)}}
h2{{font-size:1.1rem;font-weight:600;margin-bottom:1rem;padding-bottom:.5rem;border-bottom:1px solid var(--bd)}}
.fl{{display:flex;gap:.5rem;margin-bottom:1rem;flex-wrap:wrap}}.fb{{background:var(--s);border:1px solid var(--bd);color:var(--td);padding:.35rem .75rem;border-radius:6px;cursor:pointer;font-size:.75rem;font-family:inherit;transition:all .15s}}.fb:hover{{border-color:var(--ac);color:var(--t)}}.fb.act{{background:var(--ac);border-color:var(--ac);color:#fff}}
.f{{background:var(--s);border:1px solid var(--bd);border-radius:8px;margin-bottom:.75rem;overflow:hidden;transition:all .15s}}.f:hover{{border-color:var(--ac)}}.f.sev-critical{{border-left:3px solid var(--cr)}}.f.sev-warning{{border-left:3px solid var(--wa)}}.f.sev-info{{border-left:3px solid var(--in)}}
.fh{{padding:.75rem 1rem;cursor:pointer;display:flex;align-items:center;gap:.75rem}}.fh:hover{{background:var(--s2)}}
.sb{{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;padding:.15rem .5rem;border-radius:4px;flex-shrink:0}}.sb.critical{{background:var(--crb);color:var(--cr)}}.sb.warning{{background:var(--wab);color:var(--wa)}}.sb.info{{background:var(--inb);color:var(--in)}}
.fi{{color:var(--td);font-size:.75rem;flex-shrink:0;min-width:70px}}.ft{{font-size:.85rem;font-weight:500;flex-grow:1}}.fe{{font-size:.7rem;color:var(--td);background:var(--s2);padding:.15rem .5rem;border-radius:4px;flex-shrink:0}}.fg{{color:var(--td);flex-shrink:0;transition:transform .2s}}.f.open .fg{{transform:rotate(90deg)}}
.fb2{{display:none;padding:0 1rem 1rem;font-size:.82rem;border-top:1px solid var(--bd)}}.f.open .fb2{{display:block}}.fb2 p{{margin:.5rem 0}}.fb2 .lb{{color:var(--td);font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;margin-top:.75rem}}
.fb2 code{{display:block;background:var(--bg);padding:.75rem;border-radius:6px;font-size:.78rem;overflow-x:auto;white-space:pre-wrap;margin-top:.25rem;border:1px solid var(--bd)}}.fb2 .fs{{display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.25rem}}.fb2 .ftag{{background:var(--s2);padding:.15rem .5rem;border-radius:4px;font-size:.72rem;color:var(--td)}}.fb2 .rec{{background:rgba(46,213,115,.06);border:1px solid rgba(46,213,115,.15);border-radius:6px;padding:.75rem;margin-top:.5rem}}
.cost-det{{margin-bottom:2rem;font-size:.78rem}}.cost-det summary{{cursor:pointer;color:var(--td);padding:.5rem 0}}.ct2{{width:100%;border-collapse:collapse;margin-top:.5rem}}.ct2 th,.ct2 td{{padding:.4rem .75rem;text-align:left;border-bottom:1px solid var(--bd)}}.ct2 th{{color:var(--td);font-size:.7rem;text-transform:uppercase}}
.foot{{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--bd);color:var(--td);font-size:.72rem;text-align:center}}
</style></head><body>
<div class="hdr"><h1>&#x1f50d; Codebase Analysis Report</h1><div class="meta">{self._e(src_str)} &middot; {meta.get('analyzed_at','')[:19]} &middot; {meta.get('duration_seconds',0)}s</div></div>
{f'<div class="qb"><span>&#x1f4ac; Query:</span> {self._e(meta.get("user_query"))}</div>' if meta.get('user_query') else ''}
<div class="ss"><div class="sr"><svg viewBox="0 0 120 120" width="120" height="120"><circle cx="60" cy="60" r="52" fill="none" stroke="var(--s2)" stroke-width="8"/><circle cx="60" cy="60" r="52" fill="none" stroke="{sc}" stroke-width="8" stroke-dasharray="{score*3.267} 326.7" stroke-linecap="round"/></svg><div class="vl" style="color:{sc}">{score}</div></div>
<div class="sd"><div class="ct"><div class="c"><span class="d cr"></span>{len(critical)} critical</div><div class="c"><span class="d wa"></span>{len(warnings)} warnings</div><div class="c"><span class="d in"></span>{len(infos)} info</div></div><div style="color:var(--td);font-size:.8rem">{len(findings)} findings</div></div></div>
{'<div class="sg">' + "".join(stk_cards) + '</div>' if stk_cards else ''}
{cost_html}
<div class="pr"><div class="pc"><h3>&#x1f6a8; Top Priorities</h3><ol>{prio_items}</ol></div><div class="pc st"><h3>&#x2705; Strengths</h3><ul>{str_items}</ul></div></div>
<h2>Findings</h2>
<div class="fl"><button class="fb act" onclick="flt('all')">All ({len(findings)})</button><button class="fb" onclick="flt('critical')">Critical ({len(critical)})</button><button class="fb" onclick="flt('warning')">Warning ({len(warnings)})</button><button class="fb" onclick="flt('info')">Info ({len(infos)})</button></div>
<div id="fl">{chr(10).join(f_html)}</div>
<div class="foot">Codebase Analyzer v2.0 &middot; Multi-agent &middot; Multi-provider &middot; by <a href="https://thetechguy.se" style="color:var(--td);text-decoration:none" target="_blank">Marcus Johansson</a> &middot; <a href="mailto:marcus@thetechguy.se" style="color:var(--td);text-decoration:none">marcus@thetechguy.se</a></div>
<script>document.querySelectorAll('.fh').forEach(e=>e.addEventListener('click',()=>e.parentElement.classList.toggle('open')));function flt(s){{document.querySelectorAll('.fb').forEach(b=>b.classList.remove('act'));event.target.classList.add('act');document.querySelectorAll('.f').forEach(f=>{{f.style.display=s==='all'||f.dataset.s===s?'':'none'}})}}</script>
</body></html>"""

    def _e(self, t):
        return str(t or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")
