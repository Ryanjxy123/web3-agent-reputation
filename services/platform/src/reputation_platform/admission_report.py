"""Render a readable admission report without inventing evaluation results."""

from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import urlsplit

from reputation_core import AdmissionReport, CandidateAdmission, ProbeObservation, Verdict

CHECK_NAMES = {
    "registration": "公开注册身份",
    "functional_declaration": "具体功能声明",
    "service_interface": "可调用业务接口",
    "independent_oracle": "独立核验依据",
    "execution_binding": "执行身份关联",
    "execution_history": "可归属交易历史",
}
CHECK_HINTS = {
    "registration": "确认这是哪个 Agent，以及它登记在哪条链上。",
    "functional_declaration": "找到能检验的具体承诺，而不只是名称或宣传语。",
    "service_interface": "明确怎样调用业务、费用和限制；网页可打开不等于业务可用。",
    "independent_oracle": "用独立事实核对结果，不能只相信接口自己说成功。",
    "execution_binding": "证明哪个钱包或合约实际执行任务；收款地址不直接算执行者。",
    "execution_history": "把历史交易与具体任务、执行者和结果对应起来。",
}
STATUS = {
    Verdict.PASS: ("pass", "已核实"),
    Verdict.FAIL: ("fail", "未通过"),
    Verdict.UNKNOWN: ("unknown", "待核实"),
    Verdict.NOT_APPLICABLE: ("na", "不适用"),
}
PURPOSES = {"availability": "接口响应采集", "functional": "业务响应采集（尚未判分）", "behavioral": "交易证据采集（尚未判分）", "background": "资料采集"}


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _source(value: str) -> str:
    try:
        parsed = urlsplit(value)
        allowed = parsed.scheme.lower() == "https" and bool(parsed.hostname)
        allowed = allowed and not any(ord(char) < 32 for char in value)
    except ValueError:
        allowed = False
    if allowed:
        return f'<a href="{_text(value)}" rel="noreferrer">{_text(value)}</a>'
    return f'<span class="source">{_text(value)}</span>'


def _items(values: list[str], *, sources: bool = False) -> str:
    if not values:
        return '<p class="muted">尚无记录。</p>'
    render = _source if sources else _text
    return "<ul>" + "".join(f"<li>{render(value)}</li>" for value in values) + "</ul>"


def _when(value: datetime) -> str:
    if value.tzinfo is None:
        return value.strftime("%Y-%m-%d %H:%M:%S") + "（时区未记录）"
    return value.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S") + "（北京时间）"


def _candidate(candidate: CandidateAdmission, index: int) -> str:
    verified = [CHECK_NAMES[check.code] for check in candidate.checks if check.status == Verdict.PASS]
    missing = [f"{CHECK_NAMES[check.code]}：{check.explanation}" for check in candidate.checks if check.status != Verdict.PASS]
    state = "具备完整评价前提" if candidate.ready_for_full_score else "暂不能完整评分"
    checks = []
    for check in candidate.checks:
        css, label = STATUS[check.status]
        checks.append(
            f'<section class="check"><div class="check-title"><h4>{CHECK_NAMES[check.code]}</h4>'
            f'<span class="badge {css}">{label}</span></div><p class="muted">{CHECK_HINTS[check.code]}</p>'
            f'<p>{_text(check.explanation)}</p><details><summary>查看这项检查的证据</summary>'
            f'{_items(check.evidence, sources=True)}</details></section>'
        )
    return (
        f'<article class="candidate" aria-labelledby="candidate-{index}"><header class="candidate-header">'
        f'<div><p class="eyebrow">候选 {index}</p><h2 id="candidate-{index}">{_text(candidate.name)}</h2></div>'
        f'<span class="badge {"pass" if candidate.ready_for_full_score else "unknown"}">{state}</span></header>'
        f'<p class="muted identity">注册线索：{_text(candidate.registration_reference)}</p>'
        f'<div class="overview"><section><h3>已核实什么</h3>{_items(verified)}</section>'
        f'<section><h3>还缺什么</h3>{_items(missing) if missing else "<p>六项准入前提已齐，接下来需要真实评价采样。</p>"}</section></div>'
        f'<h3>六项检查，逐项说明</h3><div class="checks">{"".join(checks)}</div>'
        f'<section class="next"><h3>下一步怎么做</h3>{_items(candidate.next_actions)}</section>'
        f'<details class="sources"><summary>资料来源与定位线索</summary>{_items(candidate.source_urls, sources=True)}</details></article>'
    )


def _observation(observation: ProbeObservation) -> str:
    css, label = STATUS[observation.outcome]
    label = "已取得响应，未判业务正确" if observation.outcome == Verdict.PASS else "采集待确认"
    status = str(observation.http_status) if observation.http_status is not None else "未取得 HTTP 状态"
    payload = "无请求体" if observation.request_json is None else observation.request_json
    return (
        f'<details class="request"><summary>{_text(observation.request_key)} · {_text(observation.method)} · '
        f'{_text(status)}</summary><p><span class="badge {css}">{label}</span> '
        f'{PURPOSES[observation.purpose]} · {_text(_when(observation.observed_at))}</p>'
        f'<p>请求地址：{_source(observation.url)}</p><p>耗时：{observation.elapsed_ms:.1f} 毫秒；'
        f'响应是否完整保存：{"是" if observation.body_complete else "否"}；'
        f'错误类型：{_text(observation.error_kind or "无记录")}</p>'
        f'<p>请求内容：</p><pre>{_text(payload)}</pre>'
        f'<p>响应文件：<code>{_text(observation.response_file or "未保存")}</code></p>'
        f'<p>响应 SHA-256：<code>{_text(observation.response_sha256 or "未取得")}</code></p></details>'
    )


def render_admission_report(report: AdmissionReport, observations: list[ProbeObservation]) -> str:
    """Return self-contained HTML; admission checks never become reputation scores."""
    ready = sum(candidate.ready_for_full_score for candidate in report.candidates)
    explanation = (
        "本次检查中，还没有候选同时具备完整评价所需的六项证据，因此暂不能给出完整三维评分。"
        if ready == 0 else
        f"已有 {ready} 个候选具备完整评价的资料前提；仍需真实采样和独立核验，才能形成三维评分。"
    )
    cards = "".join(_candidate(candidate, index) for index, candidate in enumerate(report.candidates, 1))
    requests = "".join(_observation(observation) for observation in observations)
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light"><title>候选可评价性检查 · Web3 Agent 声誉平台</title>
<style>
:root{{font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;color:#1d2c3a;background:#f5f6f4;line-height:1.7}}
*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1080px;margin:auto;padding:48px 24px 72px}}a{{color:#175c80;text-underline-offset:3px;overflow-wrap:anywhere}}
a:focus-visible,summary:focus-visible{{outline:3px solid #177b77;outline-offset:4px}}h1,h2,h3,h4,p{{margin:0}}h1{{font-size:clamp(28px,5vw,42px);letter-spacing:-.03em}}
h2{{font-size:26px}}h3{{font-size:18px;margin-bottom:12px}}h4{{font-size:16px}}p+p{{margin-top:10px}}ul{{margin:8px 0;padding-left:22px}}li+li{{margin-top:7px}}
.eyebrow{{font-size:12px;letter-spacing:.1em;color:#526b70;font-weight:700;margin-bottom:5px}}.muted{{color:#5b6973;font-size:14px}}.intro{{max-width:820px;margin:18px 0 12px;font-size:17px}}
.metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:28px 0}}.metric{{background:#fff;border:1px solid #dce4e0;border-radius:14px;padding:20px}}
.metric strong{{display:block;font-size:34px;line-height:1.2;color:#17635d}}.metric span{{font-size:14px}}.notice{{border-left:4px solid #b88626;background:#fff7e8;padding:18px 20px;border-radius:0 10px 10px 0;margin-bottom:30px}}
.candidate{{padding:28px;background:#fff;border:1px solid #dce4e0;border-radius:18px;margin-top:24px}}.candidate-header,.check-title{{display:flex;justify-content:space-between;align-items:center;gap:14px}}
.badge{{display:inline-block;white-space:nowrap;border-radius:999px;font-size:12px;padding:3px 10px;font-weight:650}}.pass{{background:#e0f1e9;color:#185d45}}.unknown{{background:#fff0d2;color:#775312}}
.fail{{background:#f9e5e1;color:#853727}}.na{{background:#e9edf1;color:#4a5b6d}}.identity{{margin-top:14px;overflow-wrap:anywhere}}.overview{{display:grid;grid-template-columns:1fr 1.5fr;gap:24px;margin:24px 0;padding:22px;background:#f6f8f7;border-radius:12px}}
.checks{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.check{{border:1px solid #e0e6e3;border-radius:12px;padding:18px}}.check .muted{{margin:7px 0 10px}}.check p{{overflow-wrap:anywhere}}
details{{margin-top:12px}}summary{{cursor:pointer;color:#315c68;font-size:14px;font-weight:600}}details ul{{font-size:13px}}.next{{margin-top:24px}}.sources{{padding-top:16px;border-top:1px solid #e4e9e6;margin-top:24px}}
.technical{{margin-top:36px;padding:24px;background:#edf1f0;border-radius:14px}}.request{{padding:14px 0;border-top:1px solid #d5ded9}}.request p{{font-size:13px;margin-top:10px;overflow-wrap:anywhere}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#fff;padding:12px;border-radius:8px;font-size:12px}}code,.source{{overflow-wrap:anywhere}}footer{{margin-top:28px;color:#5b6973;font-size:13px}}
@media(max-width:640px){{main{{padding:28px 16px 48px}}.metrics{{gap:8px}}.metric{{padding:14px 10px}}.metric strong{{font-size:28px}}.metric span{{font-size:12px}}.candidate{{padding:20px 16px}}.candidate-header{{align-items:flex-start;flex-direction:column}}.overview,.checks{{grid-template-columns:1fr}}.overview{{padding:16px;gap:18px}}.technical{{padding:18px 16px}}}}
</style></head><body><main>
<header><p class="eyebrow">WEB3 AGENT 声誉平台 · 资料与证据</p><h1>候选可评价性检查</h1>
<p class="intro">{_text(explanation)} 这份报告说明哪些事实已经核实、还缺哪些资料，以及下一步怎样补齐。</p>
<p class="muted">检查时间：{_text(_when(report.assessed_at))}</p></header>
<section class="metrics" aria-label="本轮检查统计"><div class="metric"><strong>{ready}</strong><span>完整准入数</span></div>
<div class="metric"><strong>{len(report.candidates)}</strong><span>检查候选数</span></div><div class="metric"><strong>{len(observations)}</strong><span>真实请求记录数</span></div></section>
<aside class="notice"><p><strong>为什么这里没有声誉分数？</strong></p><p>可用性需要业务采样，功能一致性需要独立核验，交易可靠性需要能归属于 Agent 的执行证据。资料缺失不会算成 0 分；HTTP 请求成功也不会直接算作业务正确或满分。</p></aside>
{cards or '<p>本轮尚无候选记录。</p>'}
<details class="technical"><summary>技术证据：HTTP 请求记录与文件校验</summary><p class="muted">这些记录用于追溯采集过程。资料请求、业务调用和核验请求的用途分别列出，不共用评分样本。</p>
{requests or '<p>本轮没有实际请求记录。</p>'}</details>
<footer>本报告只描述本轮已取得的资料与准入判断。通过准入表示具备继续评价的前提，不表示已完成评价或保证服务表现。</footer>
</main></body></html>'''
