// Gráfico de preços ao longo do tempo (SVG)

const Graf = {
    est: null,   // estado do gráfico atual, usado pelo cursor/toque

    // pts: [{d, v}] históricos
    desenhar(pts) {
        const W = 320, H = 176, ml = 42, mr = 12, mt = 8, mb = 26;
        const n = pts.length, n0 = n;
        const vals = pts.map(p => p.v);
        const all = vals;
        const datas = pts.map(p => p.d);
        let mn = Math.min(...vals), mx = Math.max(...vals);
        const pd = (mx - mn) * 0.12 || 0.1;
        mn -= pd; mx += pd;
        const x = (i) => ml + (n > 1 ? i * (W - ml - mr) / (n - 1) : (W - ml - mr) / 2);
        const y = (a) => H - mb - (a - mn) / (mx - mn) * (H - mb - mt);
        const linha = (a, b) => { const s = []; for (let i = a; i <= b; i++) s.push(x(i).toFixed(1) + ',' + y(all[i]).toFixed(1)); return s.join(' '); };
        const cor = vals[n0 - 1] >= vals[0] ? '#3BD777' : '#fb7185';
                this.est = { pts, all, datas, n0, n, W, ml, mr, y, x, cor };

        let o = `<div id="g-info" aria-live="polite" class="min-h-[68px]">${this.info(n0 - 1)}</div>`;
        o += `<svg id="g-svg" viewBox="0 0 ${W} ${H}" width="100%" style="touch-action:pan-y;display:block;cursor:crosshair" role="img" aria-label="Gráfico de preços. Passe o cursor ou toque para ver cada dia." onpointermove="Graf.hover(event)" onpointerdown="Graf.hover(event)" onpointerleave="if(event.pointerType==='mouse')Graf.sair()">`;
        [0, 0.5, 1].forEach(t => {
            const a = mn + (mx - mn) * t;
            o += `<line x1="${ml}" x2="${W - mr}" y1="${y(a).toFixed(1)}" y2="${y(a).toFixed(1)}" stroke="#1c4630"/>` +
                 `<text x="${ml - 5}" y="${(y(a) + 4).toFixed(1)}" font-size="11" text-anchor="end" fill="#94a3b8">${a.toFixed(2).replace('.', ',')}</text>`;
        });
        // linha tracejada no preço mais recente (referência: está alto ou baixo?)
        const yu = y(vals[n0 - 1]).toFixed(1);
        o += `<line x1="${ml}" x2="${W - mr}" y1="${yu}" y2="${yu}" stroke="#F2D411" stroke-width="1.5" stroke-dasharray="6 4" opacity="0.85"/>`;
        if (n0 > 1) o += `<polyline fill="none" stroke="${cor}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" points="${linha(0, n0 - 1)}"/>`;
        o += `<circle cx="${x(n0 - 1).toFixed(1)}" cy="${y(vals[n0 - 1]).toFixed(1)}" r="4" fill="${cor}"/>` +
             `<line id="g-lin" x1="0" x2="0" y1="${mt}" y2="${H - mb}" stroke="#94a3b8" stroke-dasharray="3 3" visibility="hidden"/>` +
             `<circle id="g-pto" r="6" cx="0" cy="0" fill="${cor}" stroke="#0a1f13" stroke-width="2" visibility="hidden"/>`;
        const marcas = n > 3 ? [0, Math.round((n - 1) / 3), Math.round((n - 1) * 2 / 3), n - 1] : [...Array(n).keys()];
        marcas.forEach((i, j) => {
            const anc = j === 0 ? 'start' : j === marcas.length - 1 ? 'end' : 'middle';
            o += `<text x="${x(i).toFixed(1)}" y="${H - 7}" font-size="12" text-anchor="${anc}" fill="#94a3b8">${dataCurta(datas[i])}</text>`;
        });
        return o + '</svg>';
    },

    // Painel de leitura de um ponto do gráfico
    info(i) {
        const c = this.est, p = c.all[i], ant = i ? c.all[i - 1] : null;
        return `<b class="text-[26px] text-white">${R$(p)}</b> ${ant !== null ? chipVar((p - ant) / ant * 100) : ''}` +
               `<div class="text-[15px] text-slate-400 mt-0.5">${dataBR(c.datas[i])} · Cotação</div>`;
    },

    hover(e) {
        const c = this.est;
        if (!c) return;
        const r = el('g-svg').getBoundingClientRect();
        const px = (e.clientX - r.left) / r.width * c.W;
        let i = c.n > 1 ? Math.round((px - c.ml) / ((c.W - c.ml - c.mr) / (c.n - 1))) : 0;
        i = Math.max(0, Math.min(c.n - 1, i));
        const X = c.x(i);
        const l = el('g-lin'), d = el('g-pto');
        l.setAttribute('x1', X); l.setAttribute('x2', X); l.setAttribute('visibility', 'visible');
        d.setAttribute('cx', X); d.setAttribute('cy', c.y(c.all[i])); d.setAttribute('visibility', 'visible');
        el('g-info').innerHTML = this.info(i);
    },

    sair() {
        const c = this.est;
        if (!c) return;
        el('g-lin').setAttribute('visibility', 'hidden');
        el('g-pto').setAttribute('visibility', 'hidden');
        el('g-info').innerHTML = this.info(c.n0 - 1);
    },

    // Várias praças no mesmo gráfico. series: [{id, cor, pts:[{d, v}]}]
    // Eixo X = todas as datas com cotação em alguma praça; cada linha liga só os dias da sua praça.
    multi(series) {
        const W = 320, H = 190, ml = 42, mr = 12, mt = 8, mb = 26;
        const datas = [...new Set(series.flatMap(s => s.pts.map(p => p.d)))].sort();
        const pos = new Map(datas.map((d, i) => [d, i]));
        const n = datas.length;
        const todos = series.flatMap(s => s.pts.map(p => p.v));
        let mn = Math.min(...todos), mx = Math.max(...todos);
        const pd = (mx - mn) * 0.12 || 0.1;
        mn -= pd; mx += pd;
        const x = (i) => ml + (n > 1 ? i * (W - ml - mr) / (n - 1) : (W - ml - mr) / 2);
        const y = (a) => H - mb - (a - mn) / (mx - mn) * (H - mb - mt);
        const valor = series.map(s => new Map(s.pts.map(p => [p.d, p.v])));
        this.estM = { series, datas, valor, n, W, ml, mr, x, y };

        let o = `<div class="flex flex-wrap gap-x-3 gap-y-1 mb-2">${series.map(s =>
            `<span class="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-300"><span class="w-4 h-1 rounded-full" style="background:${s.cor}"></span>${esc(s.id)}</span>`).join('')}</div>`;
        o += `<div id="gm-info" aria-live="polite" class="min-h-[52px]">${this.infoM(n - 1)}</div>`;
        o += `<svg id="gm-svg" viewBox="0 0 ${W} ${H}" width="100%" style="touch-action:pan-y;display:block;cursor:crosshair" role="img" aria-label="Gráfico comparando praças. Passe o cursor ou toque para ver cada dia." onpointermove="Graf.hoverM(event)" onpointerdown="Graf.hoverM(event)" onpointerleave="if(event.pointerType==='mouse')Graf.sairM()">`;
        [0, 0.5, 1].forEach(t => {
            const a = mn + (mx - mn) * t;
            o += `<line x1="${ml}" x2="${W - mr}" y1="${y(a).toFixed(1)}" y2="${y(a).toFixed(1)}" stroke="#1c4630"/>` +
                 `<text x="${ml - 5}" y="${(y(a) + 4).toFixed(1)}" font-size="11" text-anchor="end" fill="#94a3b8">${a.toFixed(2).replace('.', ',')}</text>`;
        });
        series.forEach(s => {
            const p = s.pts.map(q => `${x(pos.get(q.d)).toFixed(1)},${y(q.v).toFixed(1)}`);
            if (p.length > 1) o += `<polyline fill="none" stroke="${s.cor}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" points="${p.join(' ')}"/>`;
            const u = s.pts[s.pts.length - 1];
            o += `<circle cx="${x(pos.get(u.d)).toFixed(1)}" cy="${y(u.v).toFixed(1)}" r="3.5" fill="${s.cor}"/>`;
        });
        o += `<line id="gm-lin" x1="0" x2="0" y1="${mt}" y2="${H - mb}" stroke="#94a3b8" stroke-dasharray="3 3" visibility="hidden"/>`;
        series.forEach((s, k) => { o += `<circle id="gm-pto-${k}" r="5" cx="0" cy="0" fill="${s.cor}" stroke="#0a1f13" stroke-width="2" visibility="hidden"/>`; });
        const marcas = n > 3 ? [0, Math.round((n - 1) / 3), Math.round((n - 1) * 2 / 3), n - 1] : [...Array(n).keys()];
        marcas.forEach((i, j) => {
            const anc = j === 0 ? 'start' : j === marcas.length - 1 ? 'end' : 'middle';
            o += `<text x="${x(i).toFixed(1)}" y="${H - 7}" font-size="12" text-anchor="${anc}" fill="#94a3b8">${dataCurta(datas[i])}</text>`;
        });
        return o + '</svg>';
    },

    infoM(i) {
        const c = this.estM, d = c.datas[i];
        return `<div class="text-sm text-slate-400 mb-1">${dataBR(d, true)}</div><div class="flex flex-wrap gap-x-4 gap-y-1">` +
            c.series.map((s) => {
                // último preço da praça até este dia (nem toda praça tem boletim todo dia)
                let p = null;
                for (const q of s.pts) { if (q.d <= d) p = q; else break; }
                const dia = p && p.d !== d ? `<span class="text-[11px] text-slate-500">(${dataCurta(p.d)})</span>` : '';
                return `<span class="inline-flex items-center gap-1.5 text-[15px]"><span class="w-2.5 h-2.5 rounded-full" style="background:${s.cor}"></span><span class="text-slate-400 text-xs font-semibold">${esc(s.id)}</span><b class="text-white">${p ? R$(p.v) : '—'}</b>${dia}</span>`;
            }).join('') + '</div>';
    },

    hoverM(e) {
        const c = this.estM;
        if (!c) return;
        const r = el('gm-svg').getBoundingClientRect();
        const px = (e.clientX - r.left) / r.width * c.W;
        let i = c.n > 1 ? Math.round((px - c.ml) / ((c.W - c.ml - c.mr) / (c.n - 1))) : 0;
        i = Math.max(0, Math.min(c.n - 1, i));
        const X = c.x(i), d = c.datas[i];
        const l = el('gm-lin');
        l.setAttribute('x1', X); l.setAttribute('x2', X); l.setAttribute('visibility', 'visible');
        c.series.forEach((s, k) => {
            const p = el('gm-pto-' + k), v = c.valor[k].get(d);
            if (v == null) { p.setAttribute('visibility', 'hidden'); return; }
            p.setAttribute('cx', X); p.setAttribute('cy', c.y(v)); p.setAttribute('visibility', 'visible');
        });
        el('gm-info').innerHTML = this.infoM(i);
    },

    sairM() {
        const c = this.estM;
        if (!c) return;
        el('gm-lin').setAttribute('visibility', 'hidden');
        c.series.forEach((s, k) => el('gm-pto-' + k).setAttribute('visibility', 'hidden'));
        el('gm-info').innerHTML = this.infoM(c.n - 1);
    },

    // Anos sobrepostos (eixo X = semanas do ano, jan–dez) + previsão. A = calcularAnual(...)
    anual(A, ocultos) {
        const W = 320, H = 200, ml = 42, mr = 10, mt = 8, mb = 24;
        const vis = A.anos.map((a, k) => ({ a, k })).filter(o => !ocultos.has(o.a));
        const proj = A.proj;
        // se a previsão passa de dezembro, o eixo continua pelo começo do ano seguinte
        const wMax = Math.max(51, ...proj.map(p => p.w));
        const val = (a, w) => w <= 51 ? A.sem[a][w] : ((A.sem[a + 1] || [])[w - 52] ?? null);
        const vals = vis.flatMap(o => [...Array(wMax + 1).keys()].map(w => o.a === A.atual && w > 51 ? null : val(o.a, w)).filter(v => v != null))
            .concat(ocultos.has(A.atual) ? [] : proj.flatMap(p => [p.lo, p.hi]));
        let mn = vals.length ? Math.min(...vals) : 0, mx = vals.length ? Math.max(...vals) : 1;
        const pd = (mx - mn) * 0.1 || 0.1;
        mn -= pd; mx += pd;
        const x = (w) => ml + w * (W - ml - mr) / wMax;
        const y = (v) => H - mb - (v - mn) / (mx - mn) * (H - mb - mt);
        this.estA = { A, vis, proj, W, ml, mr, x, y, wMax, val };

        let o = `<div class="flex flex-wrap gap-1.5 mb-2" role="group" aria-label="Anos no gráfico">${A.anos.map((a, k) => {
            const on = !ocultos.has(a);
            return `<button data-act="anual-ano" data-arg="${a}" aria-pressed="${on}" class="inline-flex items-center gap-1.5 px-2 py-1 rounded-full border text-xs font-bold transition-colors ${on ? 'border-mata-700 text-slate-200' : 'border-mata-800 text-slate-500 line-through'}" style="opacity:${on ? opAno(k) : 0.6}"><span class="w-3 rounded-full" style="background:${corAno(k)};height:${espAno(k)}px"></span>${a}</button>`;
        }).join('')}</div>`;
        o += `<div id="ga-info" aria-live="polite" class="min-h-[44px]">${this.infoA(Math.min(A.w0, 51))}</div>`;
        o += `<svg id="ga-svg" viewBox="0 0 ${W} ${H}" width="100%" style="touch-action:pan-y;display:block;cursor:crosshair" role="img" aria-label="Preço semanal de cada ano sobreposto" onpointermove="Graf.hoverA(event)" onpointerdown="Graf.hoverA(event)" onpointerleave="if(event.pointerType==='mouse')Graf.sairA()">`;
        [0, 0.5, 1].forEach(t => {
            const v = mn + (mx - mn) * t;
            o += `<line x1="${ml}" x2="${W - mr}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="#1c4630"/>` +
                 `<text x="${ml - 5}" y="${(y(v) + 4).toFixed(1)}" font-size="11" text-anchor="end" fill="#94a3b8">${v.toFixed(2).replace('.', ',')}</text>`;
        });
        // meses no eixo X (e os do ano seguinte, se o eixo passar de dezembro)
        'JFMAMJJASONDJFMA'.split('').forEach((l, m) => {
            const w = (new Date(2001, m, 1) - new Date(2001, 0, 1)) / 864e5 / 7 + 2;
            if (w <= wMax) o += `<text x="${x(w).toFixed(1)}" y="${H - 7}" font-size="11" text-anchor="middle" fill="${m > 11 ? '#F2D411' : '#94a3b8'}">${l}</text>`;
        });
        if (wMax > 51) o += `<line x1="${x(51.5).toFixed(1)}" x2="${x(51.5).toFixed(1)}" y1="${mt}" y2="${H - mb}" stroke="#94a3b8" stroke-opacity="0.5" stroke-dasharray="2 3"/>`;
        // faixa e linha da previsão (só o trecho dentro do ano)
        if (proj.length && !ocultos.has(A.atual)) {
            const base = { w: A.w0, v: A.sem[A.atual][A.w0] ?? A.p0 };
            const cima = [{ w: base.w, v: base.v }, ...proj.map(p => ({ w: p.w, v: p.hi }))];
            const baixo = [...proj.map(p => ({ w: p.w, v: p.lo }))].reverse().concat([{ w: base.w, v: base.v }]);
            o += `<polygon points="${cima.concat(baixo).map(p => `${x(p.w).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ')}" fill="${corAno(0)}" fill-opacity="0.15"/>`;
            o += `<polyline fill="none" stroke="${corAno(0)}" stroke-width="2.5" stroke-dasharray="5 4" points="${[base, ...proj].map(p => `${x(p.w).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ')}"/>`;
        }
        // anos: do mais antigo para o atual (o atual fica por cima)
        [...vis].reverse().forEach(({ a, k }) => {
            const s = [...Array(wMax + 1).keys()].map(w => a === A.atual && w > 51 ? null : val(a, w));
            let seg = [], segs = [];
            s.forEach((v, w) => { if (v != null) seg.push(`${x(w).toFixed(1)},${y(v).toFixed(1)}`); else if (seg.length) { segs.push(seg); seg = []; } });
            if (seg.length) segs.push(seg);
            segs.forEach(sg => {
                o += sg.length > 1
                    ? `<polyline fill="none" stroke="${corAno(k)}" stroke-opacity="${opAno(k)}" stroke-width="${espAno(k)}" stroke-linejoin="round" stroke-linecap="round" points="${sg.join(' ')}"/>`
                    : `<circle cx="${sg[0].split(',')[0]}" cy="${sg[0].split(',')[1]}" r="2" fill="${corAno(k)}" fill-opacity="${opAno(k)}"/>`;
            });
        });
        o += `<line id="ga-lin" x1="0" x2="0" y1="${mt}" y2="${H - mb}" stroke="#94a3b8" stroke-dasharray="3 3" visibility="hidden"/>`;
        return o + '</svg>';
    },

    infoA(w) {
        const c = this.estA, A = c.A;
        const d = new Date(A.atual, 0, 1 + 7 * w, 12);
        const p = c.proj.find(q => q.w === w);
        const itens = c.vis.map(({ a, k }) => {
            const v = a === A.atual && w > 51 ? null : c.val(a, w);
            return `<span class="inline-flex items-center gap-1 text-sm" style="opacity:${opAno(k)}"><span class="w-2 h-2 rounded-full" style="background:${corAno(k)}"></span><span class="text-slate-400 text-xs font-semibold">${a}</span><b class="text-white">${v != null ? preco(v) : '–'}</b></span>`;
        });
        if (p && !ocultosAtual()) itens.push(`<span class="inline-flex items-center gap-1 text-sm"><span class="text-ouro text-xs font-bold">previsão</span><b class="text-white">${preco(p.v)}</b><span class="text-[11px] text-slate-500">(${preco(p.lo)}–${preco(p.hi)})</span></span>`);
        return `<div class="text-xs text-slate-400 mb-1">Semana de ${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')} · R$</div><div class="flex flex-wrap gap-x-3 gap-y-1">${itens.join('')}</div>`;

        function ocultosAtual() { return ANUAL.ocultos.has(A.atual); }
    },

    hoverA(e) {
        const c = this.estA;
        if (!c) return;
        const r = el('ga-svg').getBoundingClientRect();
        const px = (e.clientX - r.left) / r.width * c.W;
        const w = Math.max(0, Math.min(c.wMax, Math.round((px - c.ml) / ((c.W - c.ml - c.mr) / c.wMax))));
        const l = el('ga-lin');
        l.setAttribute('x1', c.x(w)); l.setAttribute('x2', c.x(w)); l.setAttribute('visibility', 'visible');
        el('ga-info').innerHTML = this.infoA(w);
    },

    sairA() {
        const c = this.estA;
        if (!c) return;
        el('ga-lin').setAttribute('visibility', 'hidden');
        el('ga-info').innerHTML = this.infoA(Math.min(c.A.w0, 51));
    },

    // Mini-gráfico para os cards
    mini(v, apagado) {
        if (v.length < 2) return '';
        const mn = Math.min(...v), mx = Math.max(...v), r = (mx - mn) || 1;
        const pts = v.map((y, i) => `${(i * 80 / (v.length - 1) + 2).toFixed(1)},${(30 - (y - mn) / r * 26).toFixed(1)}`).join(' ');
        const cor = apagado ? '#64748b' : (v[v.length - 1] >= v[0] ? '#3BD777' : '#fb7185');
        return `<svg width="56" height="24" viewBox="0 0 84 34" class="shrink-0" aria-hidden="true"><polyline fill="none" stroke="${cor}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" points="${pts}"/></svg>`;
    }
};
