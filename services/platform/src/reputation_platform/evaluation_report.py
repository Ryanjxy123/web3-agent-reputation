"""Self-contained Chinese evaluation report; every displayed score is derived."""

from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import quote, urlsplit

from reputation_core.admission import MeasurementPurpose, Verdict
from reputation_core.reporting import EvaluationReport, SampleExplanation
from reputation_core.scoring import DimensionScore, MIN_DECISIVE_SAMPLES

PURPOSES = {
    MeasurementPurpose.AVAILABILITY: ("服务可用性", "30%"),
    MeasurementPurpose.FUNCTIONAL: ("功能声明一致性", "40%"),
    MeasurementPurpose.BEHAVIORAL: ("交易行为可靠性", "30%"),
}
VERDICTS = {
    Verdict.PASS: ("pass", "通过"), Verdict.FAIL: ("fail", "未通过"),
    Verdict.UNKNOWN: ("unknown", "无法判断"), Verdict.NOT_APPLICABLE: ("na", "不适用"),
}


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _source(value: str) -> str:
    """Only HTTPS links and repository runtime evidence can be clicked."""
    href = None
    if not any(ord(char) < 32 or ord(char) == 127 for char in value):
        try:
            parsed = urlsplit(value)
            if parsed.scheme.lower() == "https" and parsed.hostname and not parsed.username and not parsed.password:
                href = value
            else:
                path = value.replace("\\", "/")
                parts = path.split("/")
                if (len(parts) > 1 and parts[0] == "runtime"
                    and not any(part in ("", ".", "..") for part in parts)
                    and not any(char in path for char in ":?#")):
                    href = "../../" + quote(path, safe="/")
        except ValueError:
            pass
    if href is None:
        return f'<span class="source">{_text(value)}</span>'
    return f'<a href="{_text(href)}" rel="noopener noreferrer">{_text(value)}</a>'


def _items(values: list[str], *, sources: bool = False) -> str:
    if not values:
        return '<p class="muted">本轮没有记录。</p>'
    render = _source if sources else _text
    return "<ul>" + "".join(f"<li>{render(value)}</li>" for value in values) + "</ul>"


def _when(value: datetime | None) -> str:
    if value is None:
        return "具体时刻未记录"
    if value.tzinfo is None:
        return value.strftime("%Y-%m-%d %H:%M:%S") + "（时区未记录）"
    return value.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S") + "（北京时间）"


def _badge(verdict: Verdict) -> str:
    css, label = VERDICTS[verdict]
    return f'<span class="badge {css}">{label}</span>'


def _dimension(purpose: MeasurementPurpose, score: DimensionScore) -> str:
    label, weight = PURPOSES[purpose]
    value = f"{score.value:.2f}" if score.value is not None else "待评价"
    unit = '<span class="unit">/ 100</span>' if score.value is not None else ""
    denominator = score.passed + score.failed
    progress = f"已有 {denominator} 个确定结论，达到最低 {MIN_DECISIVE_SAMPLES[purpose]} 个要求。" if score.value is not None else f"至少需要 {MIN_DECISIVE_SAMPLES[purpose]} 个确定结论，目前有 {denominator} 个。"
    return (
        f'<article class="score-card"><div class="between"><h3>{label}</h3><span class="muted">权重 {weight}</span></div>'
        f'<p class="score-value">{value}{unit}</p><p class="counts">通过 {score.passed} · 未通过 {score.failed}<br>'
        f'无法判断 {score.unknown} · 不适用 {score.not_applicable}</p>'
        f'<p class="muted">已采 {score.observed} / 计划 {score.planned}；判分分母 {denominator}</p><p class="threshold">{progress}</p></article>'
    )


def _sample(explanation: SampleExplanation, index: int, *, expanded: bool) -> str:
    sample = explanation.sample
    findings = "".join(
        f'<li><div class="between"><strong>{_text(check.label)}</strong>{_badge(check.verdict)}</div>'
        f'<p class="multiline">{_text(check.explanation)}</p></li>' for check in explanation.checks
    ) or '<li>本轮未记录分项检查。</li>'
    timing = f" · 请求耗时 {sample.elapsed_ms:.2f} 毫秒" if sample.elapsed_ms is not None else ""
    return (
        f'<details class="sample" id="sample-{index}"{" open" if expanded else ""}><summary>'
        f'<span class="sample-title">{_text(explanation.title)}</span>{_badge(sample.verdict)}</summary>'
        f'<div class="sample-body"><p class="muted">{_text(_when(explanation.observed_at))}{timing}</p>'
        f'<div class="sample-facts"><section><h4>实际检查输入</h4><p class="multiline">{_text(explanation.input_summary)}</p></section>'
        f'<section><h4>服务声明或公布的结果</h4><p class="multiline">{_text(explanation.claimed_output)}</p></section>'
        f'<section class="independent"><h4>独立核验发现了什么</h4><p class="multiline">{_text(explanation.independent_result)}</p></section></div>'
        f'<h4>这条样本怎样得出结论</h4><ul class="checks">{findings}</ul>'
        f'<details class="evidence"><summary>查看原始证据、任务标识与规则原文</summary>'
        f'<p>样本标识：<code>{_text(sample.sample_id)}</code></p><p>任务标识：<code>{_text(sample.task_key)}</code></p>'
        f'<p class="multiline">规则原始结论：{_text(sample.reason)}</p>{_items(sample.evidence, sources=True)}</details></div></details>'
    )


def render_evaluation_report(report: EvaluationReport) -> str:
    """Render supplied real explanations; no demo samples or manual scores."""
    scores = report.scores
    dimensions = {MeasurementPurpose.AVAILABILITY: scores.availability,
                  MeasurementPurpose.FUNCTIONAL: scores.functional,
                  MeasurementPurpose.BEHAVIORAL: scores.behavioral}
    completed = sum(score.value is not None for score in dimensions.values())
    unknown = sum(score.unknown for score in dimensions.values())
    failed = sum(score.failed for score in dimensions.values())
    if scores.status == "COMPLETE":
        status = "本次范围内已完成评价"
        if scores.functional.failed == 0 and scores.behavioral.failed == 0:
            finding = "本次抽查的增仓结果披露和三步交易均能与链上证据对应。"
        else:
            finding = f"本次有 {scores.functional.failed + scores.behavioral.failed} 条历史任务未通过核验，具体差异在下方逐条说明。"
        if scores.availability.p95_ms is not None and scores.availability.p95_ms > 1000:
            finding += "记录入口的部分请求耗时较长，可用性分包含这次实际访问体验。"
        conclusion = finding + f"三个维度均达到既定样本要求，综合分为 {scores.overall:.2f} 分。"
    elif scores.status == "PARTIAL":
        status = "部分评价 · 暂无综合分"
        conclusion = f"本次已有 {len(report.samples)} 条评价样本，{completed} 个维度达到评分要求。其余维度仍缺足够的确定结论，暂不计算综合分。"
    else:
        status = "尚未形成评价"
        conclusion = "本次尚无进入评分的实际样本，三项维度和综合分均待评价。"
    representatives = set()
    for wanted in ((Verdict.PASS,), (Verdict.FAIL, Verdict.UNKNOWN)):
        first = next((index for index, item in enumerate(report.samples, 1) if item.sample.verdict in wanted), None)
        if first is not None:
            representatives.add(first)
    cards = "".join(_dimension(purpose, dimension) for purpose, dimension in dimensions.items())
    groups = []
    for purpose, (label, _) in PURPOSES.items():
        samples = [_sample(item, index, expanded=index in representatives)
                   for index, item in enumerate(report.samples, 1) if item.sample.purpose == purpose]
        groups.append(f'<section class="sample-group"><h3>{label} · {len(samples)} 条实际样本</h3>'
                      + ("".join(samples) if samples else '<p class="muted">本维度尚无实际样本。</p>') + '</section>')
    p95 = f"{scores.availability.p95_ms:.2f} 毫秒" if scores.availability.p95_ms is not None else "尚无成功响应可计算"
    overall = f"{scores.overall:.2f}" if scores.overall is not None else "待评价"
    sample_intro = (
        "首个通过样本，以及首个未通过或无法判断样本默认展开。其余样本点击标题查看；原始文件和标识收在各自的证据区。"
        if report.samples else "本轮尚无进入判分的样本；取得实际证据后会在这里逐条解释。"
    )
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light"><title>{_text(report.name)} · 声誉评价报告</title>
<style>
:root{{font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;color:#223348;background:#f3f5f7;line-height:1.75}}*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1120px;margin:auto;padding:48px 24px 64px}}
h1,h2,h3,h4,p{{margin:0}}h1{{font-size:clamp(30px,5vw,44px);letter-spacing:-.03em}}h2{{font-size:24px}}h3{{font-size:18px}}h4{{font-size:15px;margin-bottom:6px}}p+p{{margin-top:10px}}ul{{padding-left:22px;margin:10px 0}}li+li{{margin-top:7px}}
a{{color:#145e83;text-underline-offset:3px;overflow-wrap:anywhere}}a:focus-visible,summary:focus-visible{{outline:3px solid #00857d;outline-offset:4px}}.muted{{font-size:13px;color:#596b7b}}.eyebrow{{font-size:12px;letter-spacing:.1em;color:#426673;font-weight:700;margin-bottom:8px}}
.hero{{background:#fff;border:1px solid #dbe3e9;border-radius:20px;padding:30px}}.between{{display:flex;align-items:center;justify-content:space-between;gap:14px}}.status{{color:#0e6264;font-size:14px;font-weight:700;margin-bottom:12px}}.conclusion{{font-size:18px;margin-top:16px;max-width:850px}}
.identity{{margin-top:14px;overflow-wrap:anywhere}}.scope{{padding-top:20px;margin-top:22px;border-top:1px solid #e2e8ed}}.scope h2{{font-size:17px;margin-bottom:8px}}.scope p{{white-space:pre-wrap;overflow-wrap:anywhere}}.summary-metrics{{display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:16px;margin-top:24px}}
.metric{{padding:15px 18px;border-radius:12px;background:#edf5f4}}.metric strong{{display:block;font-size:30px;line-height:1.3;color:#135c5c}}.metric span{{font-size:13px}}.scores{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:22px 0}}
.score-card{{background:#fff;border:1px solid #dbe3e9;border-radius:16px;padding:22px}}.score-card .between{{align-items:flex-start}}.score-card h3{{font-size:17px}}.score-value{{font-size:38px;color:#135c5c;font-weight:750;margin:12px 0}}.unit{{font-size:14px;color:#596b7b;font-weight:400;margin-left:6px}}
.counts{{font-size:14px}}.threshold{{font-size:13px;margin-top:10px;padding-top:10px;border-top:1px solid #e8edf1}}.panel{{padding:26px;background:#fff;border:1px solid #dbe3e9;border-radius:18px;margin-top:24px}}.panel>h2{{margin-bottom:12px}}
.methods{{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}}.methods h3{{margin-bottom:8px}}.methods p{{font-size:14px}}.methods .p95{{padding:10px 12px;border-radius:8px;background:#edf5f4;margin-top:12px}}
.sample-group{{margin-top:24px}}.sample-group>h3{{margin-bottom:12px}}details.sample{{border:1px solid #dce4eb;border-radius:12px;margin-top:12px;background:#fff}}summary{{cursor:pointer;font-weight:600;color:#284e65}}.sample>summary{{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:16px 18px}}
.sample-title{{overflow-wrap:anywhere}}.sample[open]>summary{{border-bottom:1px solid #e4eaf0;background:#f7fafb;border-radius:12px 12px 0 0}}.sample-body{{padding:18px}}.sample-facts{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:18px 0}}.sample-facts section{{padding:15px;border-radius:10px;background:#f5f7fa}}
.sample-facts .independent{{grid-column:1/-1;background:#edf5f4}}.multiline{{white-space:pre-wrap;overflow-wrap:anywhere}}.sample-facts p,.checks p{{font-size:14px}}.checks{{list-style:none;padding:0;margin:10px 0 0}}.checks li{{padding:12px 0;border-bottom:1px solid #e9edf1}}.checks p{{margin-top:7px}}
.badge{{font-size:12px;font-weight:650;border-radius:999px;padding:3px 10px;white-space:nowrap}}.pass{{background:#dff2e9;color:#1d6248}}.fail{{background:#fbe5e1;color:#893c2d}}.unknown{{background:#fff0d1;color:#7b5619}}.na{{background:#e9edf1;color:#4e5c6c}}
.evidence{{font-size:13px;padding:14px 16px;background:#f2f5f8;border-radius:10px;margin-top:18px}}.evidence summary{{font-size:13px}}.evidence p{{overflow-wrap:anywhere;margin-top:10px}}.source,code{{overflow-wrap:anywhere}}.boundaries{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}.boundaries h3{{margin-bottom:8px}}footer{{font-size:12px;color:#596b7b;margin-top:24px}}
@media(max-width:720px){{main{{padding:22px 14px 40px}}.hero,.panel{{padding:20px 16px}}.scores,.methods,.boundaries,.sample-facts{{grid-template-columns:1fr}}.scores{{gap:12px}}.score-card{{padding:18px}}.summary-metrics{{gap:8px}}.metric{{padding:12px 9px}}.metric strong{{font-size:25px}}.metric span{{font-size:11px}}.sample>summary{{padding:14px 12px}}.sample-body{{padding:14px 12px}}.sample-facts .independent{{grid-column:auto}}.conclusion{{font-size:16px}}}}
@media print{{body{{background:#fff}}main{{padding:0}}.hero,.panel,.score-card{{break-inside:avoid}}details.sample{{break-inside:avoid}}}}
</style></head><body><main>
<header class="hero"><p class="eyebrow">WEB3 AGENT · 基于多源证据的声誉评价</p><p class="status">{status}</p>
<h1>{_text(report.name)} 的评价报告</h1><p class="conclusion">{_text(conclusion)}</p>
<p class="muted identity">注册身份：{_text(report.registration_reference)}<br>报告生成：{_text(_when(report.generated_at))}</p>
<section class="scope" aria-label="本次评价范围"><h2>这次具体评了什么</h2><p>{_text(report.scope)}</p>
<p class="muted">样本时间范围：{_text(report.evaluation_window)}</p><p class="muted">评价方式：{_text(report.approach)}</p></section>
<div class="summary-metrics" aria-label="结果概览"><div class="metric"><strong>{overall}</strong><span>综合分 · 三维证据齐全才计算</span></div>
<div class="metric"><strong>{len(report.samples)}</strong><span>实际评价样本</span></div><div class="metric"><strong>{unknown}</strong><span>无法判断 · 另有 {failed} 条未通过</span></div></div></header>
<section class="scores" aria-label="三维评分">{cards}</section>
<section class="panel"><h2>怎样理解这三个分数</h2><div class="methods">
<section><h3>服务可用性</h3><p>检查公开运行记录入口能否返回约定格式。得分由 80% 成功率与 20% 延迟表现组成；成功率的分母仅包括通过和未通过。</p>
<p class="p95">本次成功响应 p95：{p95}</p><p>p95 表示至少 95% 的成功请求在这一耗时内完成，按样本排序取最近秩。不超过 1000 毫秒时延迟项满分，达到 10000 毫秒为零，中间线性计算。这是本机经既定代理线路的访问体验，包含网络和代理耗时。</p></section>
<section><h3>功能声明一致性</h3><p>使用预先固定的一组历史运行记录，核对指定仓位、公布的真实资产用量和执行后流动性。独立读取固定区块状态，并按同区块事件顺序重建目标交易后的结果。</p>
<p>本维度只评价这些实际结果披露。得分为通过任务数 ÷ 确定结论任务数 × 100，需 7 个确定结论。</p></section>
<section><h3>交易行为可靠性</h3><p>使用与功能维度互不重复的完整运行记录，逐笔核实包装原生币、兑换、最终增仓这三项公开操作，包括身份、调用目标、资产流向、参数限制与链上结果。</p>
<p>三笔操作需要完整证据。得分为通过任务数 ÷ 确定结论任务数 × 100，需 7 个确定结论。</p></section></div>
<p class="muted">“无法判断（UNKNOWN）”表示证据或核验条件不足，不记为失败，也不进入判分分母；“不适用”单独保留。可用性至少需 8 个确定结论。三维齐全后，综合分按 30% / 40% / 30% 加权。</p></section>
<section class="panel"><h2>每条样本实际发生了什么</h2><p class="muted">{_text(sample_intro)}</p>{"".join(groups)}</section>
<section class="panel"><h2>报告的适用边界与当前限制</h2><div class="boundaries"><section><h3>本次未覆盖</h3>{_items(report.scope_exclusions)}</section>
<section><h3>本轮仍存在的限制</h3>{_items(report.limitations)}</section></div>
<details class="evidence"><summary>查看资料来源与背景证据</summary>{_items(report.source_references, sources=True)}</details></section>
<footer>本机静态评价报告原型 · 政策 {_text(scores.policy_version)} · 报告格式 {_text(report.schema_version)}<br>分数由本报告中的实际样本计算，证据和历史报告保留为独立版本。</footer>
</main></body></html>'''
