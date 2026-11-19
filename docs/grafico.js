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
        o += `<line x1="${ml}" x2="${W - mr}" y1="${yu}" y2="${yu}" stroke="#FCFC30" stroke-width="1.5" stroke-dasharray="6 4" opacity="0.85"/>`;
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

    // Mini-gráfico para os cards
    mini(v, apagado) {
        if (v.length < 2) return '';
        const mn = Math.min(...v), mx = Math.max(...v), r = (mx - mn) || 1;
        const pts = v.map((y, i) => `${(i * 80 / (v.length - 1) + 2).toFixed(1)},${(30 - (y - mn) / r * 26).toFixed(1)}`).join(' ');
        const cor = apagado ? '#64748b' : (v[v.length - 1] >= v[0] ? '#3BD777' : '#fb7185');
        return `<svg width="56" height="24" viewBox="0 0 84 34" class="shrink-0" aria-hidden="true"><polyline fill="none" stroke="${cor}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" points="${pts}"/></svg>`;
    }
};
