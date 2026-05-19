# -*- coding: utf-8 -*-
"""Regenerate _report_core.html with UTF-8 and hierarchy-first layout."""
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "reports" / "templates" / "_report_core.html"

CONTENT = r'''{# Tab navigation + hierarchy-first sections #}

<nav class="report-tabs-wrap" id="report-tabs" aria-label="리포트 섹션">
  <div class="report-tabs" role="tablist">
    <a href="#section-market" class="tab-link active" role="tab" data-section="section-market" aria-selected="true">📊 시장 요약</a>
    <a href="#section-themes" class="tab-link" role="tab" data-section="section-themes">🔥 핫 테마</a>
    <a href="#section-stocks" class="tab-link" role="tab" data-section="section-stocks">🔍 종목 분석</a>
    {% if has_company_reports %}
    <a href="#section-company" class="tab-link" role="tab" data-section="section-company">🏢 기업 리포트</a>
    {% endif %}
    <a href="#section-risk" class="tab-link" role="tab" data-section="section-risk">⚠️ 리스크</a>
  </div>
</nav>

<section id="section-market" class="report-section" aria-label="시장 요약">
  {% set phase_labels = {
    'risk_off': '위험회피', 'risk-off': '위험회피', 'bearish': '약세', 'weak': '약세',
    'neutral': '중립', 'sideways': '중립',
    'bullish': '강세', 'risk_on': '강세', 'risk-on': '강세', 'strong': '강세'
  } %}
  {% set phase_key = (market_phase | string | lower) %}
  {% set phase_display = phase_labels.get(phase_key, market_phase) %}

  <header class="market-hero">
    <p class="hero-meta">{{ report_type_label | default(header_label) }} · {{ header_date | default(date) }}</p>
    <h1 class="hero-phase phase-{{ phase_key | replace('-', '_') }}">{{ phase_display }}</h1>
    <p class="hero-summary">{{ one_line_summary }}</p>
  </header>

  <div class="block">
    <h2 class="block-label">국내 지수</h2>
    <div class="idx-kr">
      {% for name in ['KOSPI', 'KOSDAQ'] %}
      {% if name in indices %}
      {% set idx = indices[name] %}
      <div class="idx-kr-item">
        <span class="idx-kr-name">{{ name }}</span>
        <span class="idx-kr-val {{ 'up' if idx.is_up else 'down' }}">{{ idx.value }}</span>
        <span class="idx-kr-chg {{ 'up' if idx.is_up else 'down' }}">{{ idx.change }}</span>
      </div>
      {% endif %}
      {% endfor %}
    </div>
  </div>

  <div class="block">
    <h2 class="block-label">해외 지수</h2>
    <table class="data-table">
      <tbody>
        {% for name in ['S&P500', 'NASDAQ', 'DOW', 'RUSSELL2000'] %}
        {% if name in indices %}
        {% set idx = indices[name] %}
        <tr>
          <th scope="row">{{ name }}</th>
          <td class="num {{ 'up' if idx.is_up else 'down' }}">{{ idx.value }}</td>
          <td class="chg {{ 'up' if idx.is_up else 'down' }}">{{ idx.change }}</td>
        </tr>
        {% endif %}
        {% endfor %}
      </tbody>
    </table>
  </div>

  <div class="block">
    <h2 class="block-label">매크로</h2>
    <table class="data-table data-table-macro">
      <thead>
        <tr>
          {% for key, label in indicator_labels.items() %}
          <th>{{ label }}</th>
          {% endfor %}
        </tr>
      </thead>
      <tbody>
        <tr>
          {% for key, label in indicator_labels.items() %}
          {% set ind = indicators.get(key, {}) %}
          <td>
            <span class="macro-val {{ 'up' if ind.is_up else 'down' }}">{{ ind.value | default('N/A') }}</span>
            <span class="macro-chg {{ 'up' if ind.is_up else 'down' }}">{{ ind.change | default('') }}</span>
          </td>
          {% endfor %}
        </tr>
      </tbody>
    </table>
  </div>

  <div class="block">
    <h2 class="block-label">섹터 자금 흐름</h2>
    <div class="sector-inline">
      <span class="sector-label">유입</span>
      {% for s in sector_flow.hot %}
      <span class="tag tag-in">{{ s }}</span>
      {% else %}
      <span class="ref">없음</span>
      {% endfor %}
      <span class="sector-sep">|</span>
      <span class="sector-label">유출</span>
      {% for s in sector_flow.cold %}
      <span class="tag tag-out">{{ s }}</span>
      {% else %}
      <span class="ref">없음</span>
      {% endfor %}
    </div>
  </div>
</section>

<section id="section-themes" class="report-section" aria-label="핫 테마">
  <h2 class="block-label">거래량 급등</h2>
  {% for theme in top_themes %}
  {% if theme.volume_leaders %}
  {% set hero = theme.volume_leaders[0] %}
  {% set rest = theme.volume_leaders[1:] %}
  <article class="theme-hero">
    <div class="theme-hero-top">
      <span class="theme-rank">1</span>
      <div>
        <h3 class="theme-hero-name">{{ hero.name }}</h3>
        <p class="theme-hero-ratio">{{ hero.ratio }} 거래량</p>
      </div>
    </div>
    <p class="theme-hero-meta">
      <span>{{ hero.price | default('N/A') }}</span>
      <span class="{{ 'up' if hero.is_up else 'down' }}">{{ hero.change | default('N/A') }}</span>
      <span class="ref">52주 {{ hero.range_52w | default(hero.position_52w | default('N/A')) }}</span>
    </p>
  </article>
  {% if rest %}
  <table class="data-table theme-table">
    <thead>
      <tr><th>#</th><th>종목</th><th>배수</th><th>현재가</th><th>등락</th><th>52주</th></tr>
    </thead>
    <tbody>
      {% for s in rest %}
      <tr>
        <td class="rank">{{ loop.index + 1 }}</td>
        <td class="name">{{ s.name }}</td>
        <td class="ratio">{{ s.ratio }}</td>
        <td>{{ s.price | default('N/A') }}</td>
        <td class="{{ 'up' if s.is_up else 'down' }}">{{ s.change | default('N/A') }}</td>
        <td class="ref">{{ s.range_52w | default(s.position_52w | default('N/A')) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
  {% else %}
  <p class="empty-state">급등 종목 없음</p>
  {% endif %}
  {% else %}
  <p class="empty-state">테마 데이터 없음</p>
  {% endfor %}
</section>

<section id="section-stocks" class="report-section" aria-label="종목 분석">
  <h2 class="block-label">종목 심층 분석</h2>
  {% for stock in stock_analysis %}
  <article class="stock-block">
    <div class="stock-head">
      <div class="stock-head-main">
        <h3 class="stock-title">{{ stock.name }}<span class="stock-code">{{ stock.code }}</span></h3>
        <p class="stock-price-line">
          <span class="stock-price">{{ stock.price }}</span>
          <span class="stock-change {{ 'up' if stock.is_up else 'down' }}">{{ stock.change | default('N/A') }}</span>
        </p>
      </div>
      <span class="verdict-badge {{ 'buy' if stock.verdict == '매수' else ('sell' if stock.verdict == '매도' else 'hold') }}">{{ stock.verdict }}</span>
    </div>
    <p class="stock-meta ref">
      52주 {{ stock.range_52w | default(stock.low_52 ~ ' ~ ' ~ stock.high_52) }}
      · 외국인순매수 {{ stock.foreign_net_eok | default('N/A') }}
      · {{ stock.vote_count }}
    </p>

    <div class="agent-row">
      {% for ag in stock.agent_votes %}
      <details class="agent-acc">
        <summary class="agent-chip vote-{{ 'buy' if ag.vote == '매수' else ('sell' if ag.vote == '매도' else 'hold') }}">
          <span class="agent-emoji">{{ ag.emoji }}</span>
          <span class="agent-name">{{ ag.name }}</span>
          <span class="vote-pill {{ 'buy' if ag.vote == '매수' else ('sell' if ag.vote == '매도' else 'hold') }}">{{ ag.vote }}</span>
        </summary>
        <div class="acc-panel">
          <p class="agent-title ref">{{ ag.title }}</p>
          {% for r in ag.reason %}
          {% if r %}<p class="acc-text">{{ r }}</p>{% endif %}
          {% endfor %}
        </div>
      </details>
      {% endfor %}
    </div>
  </article>
  {% else %}
  <p class="empty-state">종목 분석 데이터 없음</p>
  {% endfor %}
</section>

{% if has_company_reports %}
<section id="section-company" class="report-section" aria-label="기업 리포트">
  <h2 class="block-label">기업 리포트</h2>
  {% for c in company_reports %}
  <article class="company-block">
    <div class="company-top">
      <div>
        <h3 class="company-name">{{ c.name }}<span class="stock-code">{{ c.ticker }}</span></h3>
        <p class="company-oneliner">{{ c.one_liner }}</p>
        <p class="ref company-meta">{{ c.price_display }} · {{ c.volume_ratio }}</p>
      </div>
      <span class="verdict-badge {{ 'buy' if c.verdict == '매수' else ('sell' if c.verdict == '매도' else 'hold') }}">{{ c.verdict }}</span>
    </div>
    <p class="why-hot-text">{{ c.why_hot }}</p>
    <p class="body-text">{{ c.business }}</p>
    <p class="inline-fact"><span aria-hidden="true">📈</span> {{ c.strength }}</p>
    <p class="inline-fact risk-fact"><span aria-hidden="true">⚠️</span> {{ c.risk }}</p>
    <p class="ref">{{ c.target_comment }}</p>
  </article>
  {% endfor %}
</section>
{% endif %}

<section id="section-risk" class="report-section" aria-label="리스크">
  <h2 class="block-label">리스크 &amp; 액션</h2>
  <p class="risk-line">{{ risk_warning }}</p>

  <div class="block">
    <h3 class="block-label-sm">오늘 액션</h3>
    <ol class="action-ol">
      {% for item in action_items %}
      <li>{{ item }}</li>
      {% endfor %}
    </ol>
  </div>

  {% if glossary %}
  <details class="glossary-acc">
    <summary>용어 사전</summary>
    <div class="glossary-body">
      {% for g in glossary %}
      <div class="glossary-row">
        <dt>{{ g.term }}</dt>
        <dd>{{ g.definition }}</dd>
      </div>
      {% endfor %}
    </div>
  </details>
  {% endif %}
</section>
'''

if __name__ == "__main__":
    CORE.write_text(CONTENT, encoding="utf-8")
    print("wrote", CORE)
