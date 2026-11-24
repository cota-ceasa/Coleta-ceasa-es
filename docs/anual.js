/* COTA CEA$A — Análise anualizada e previsão de preços
 * Sobrepõe até 6 anos (o atual + 5 anteriores) do preço comum de um produto numa praça,
 * em médias semanais (semana 1 = 1º a 7 de janeiro...). O ano atual fica com cor cheia;
 * cada ano anterior fica 10% mais apagado.
 * Previsão (próximas 12 semanas): parte do preço atual e aplica, semana a semana, a variação que
 * o produto teve no mesmo trecho de cada ano anterior. Linha = mediana; faixa = menor e maior caso.
 */
const ANUAL = {
    ANOS: 6,          // atual + 5 anteriores
    HORIZ: 12,        // semanas de previsão
    // escala do verde (ano atual, linha mais grossa) ao amarelo (ano mais antigo, mais fina)
    DE: [21, 160, 61], ATE: [242, 214, 0],
    ocultos: new Set(),
};

const semanaDoAno = (iso) => {
    const d = new Date(iso + 'T12:00:00'), ini = new Date(d.getFullYear(), 0, 1, 12);
    return Math.min(51, Math.floor((d - ini) / 864e5 / 7));   // 0..51 (os 1-2 últimos dias entram na 52ª)
};
const inicioSemana = (ano, w) => new Date(ano, 0, 1 + 7 * w, 12);
const mediana = (v) => { const s = [...v].sort((a, b) => a - b), n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; };

// {ano: [52 médias semanais ou null]}
function semanasPorAno(pts) {
    const acc = {};
    pts.forEach(({ d, v }) => {
        const a = +d.slice(0, 4), w = semanaDoAno(d);
        acc[a] = acc[a] || Array.from({ length: 52 }, () => []);
        acc[a][w].push(v);
    });
    const out = {};
    for (const a in acc) out[a] = acc[a].map(l => l.length ? l.reduce((x, y) => x + y, 0) / l.length : null);
    return out;
}
// valor da semana w do ano a (w pode passar de 51: vai para o ano seguinte); tolera 1 semana vazia
function valorSemana(sem, a, w) {
    while (w > 51) { a++; w -= 52; }
    const s = sem[a];
    if (!s) return null;
    for (const dw of [0, -1, 1]) { const v = s[w + dw]; if (v != null) return v; }
    return null;
}

function calcularAnual(it, mid) {
    const pts = serie(it, mid);
    const sem = semanasPorAno(pts);
    const ult = pts[pts.length - 1];
    const atual = +ult.d.slice(0, 4), w0 = semanaDoAno(ult.d);
    const anos = Object.keys(sem).map(Number).filter(a => a <= atual && a > atual - ANUAL.ANOS).sort((a, b) => b - a);
    // previsão: razões (semana w0+h / semana w0) em cada ano anterior
    const p0 = ult.v, proj = [];
    const anteriores = anos.filter(a => a < atual);
    const usados = new Set();
    for (let h = 1; h <= ANUAL.HORIZ; h++) {
        const r = [];
        anteriores.forEach(a => {
            const b = valorSemana(sem, a, w0), f = valorSemana(sem, a, w0 + h);
            if (b && f) { r.push(f / b); usados.add(a); }
        });
        if (r.length >= 2) proj.push({ h, w: w0 + h, v: p0 * mediana(r), lo: p0 * Math.min(...r), hi: p0 * Math.max(...r), n: r.length });
    }
    // resumo por ano: média, mín., máx. e o preço nesta mesma semana
    const resumo = anos.map(a => {
        const v = sem[a].filter(x => x != null);
        return { a, md: v.reduce((x, y) => x + y, 0) / v.length, mn: Math.min(...v), mx: Math.max(...v), nesta: valorSemana(sem, a, w0), parcial: a === atual };
    });
    return { sem, anos, atual, w0, p0, ult, proj, usados: [...usados].sort((a, b) => b - a), resumo };
}

function corAno(k) {
    const t = Math.min(1, k / (ANUAL.ANOS - 1));
    return '#' + ANUAL.DE.map((c, i) => Math.round(c + (ANUAL.ATE[i] - c) * t).toString(16).padStart(2, '0')).join('');
}
function opAno(k) { return Math.max(0.3, 1 - 0.1 * k); }            // atual 100%, depois 90%, 80%...
function espAno(k) { return Math.max(1.2, 3.6 - 0.5 * k); }         // atual mais grossa, as outras afinando

function renderAnual() {
    const y = window.scrollY;
    const it = itemPorChave(det.key), mid = det.anual.mid, merc = mercadoPor(mid);
    const A = calcularAnual(it, mid);
    const detalhe = it.d.replace(/\bLonga Vida\b/g, 'LV');
    const sub = [UNIDADE[it.u], it.e !== 'kg' ? it.e : ''].filter(Boolean).join(' · ');
    const box = 'bg-mata-900 border border-mata-800 rounded-2xl p-4';
    const pracas = dados.mercados.filter(x => it.m[x.id]);
    const p4 = A.proj.find(p => p.h === 4), p8 = A.proj.find(p => p.h === 8), p12 = A.proj.find(p => p.h === 12);
    const dataSem = (w) => { const d = inicioSemana(A.atual, w); return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`; };
    const linhaProj = (rot, p) => p ? `<tr class="border-t border-mata-800"><td class="py-2.5 text-slate-300">${rot} <span class="text-slate-500 text-xs">(sem. de ${dataSem(p.w)})</span></td><td class="text-right font-bold text-white whitespace-nowrap">${R$(p.v)}</td><td class="text-right text-xs text-slate-400 whitespace-nowrap pl-2">${preco(p.lo)}–${preco(p.hi)}</td></tr>` : '';

    el('vista-detalhe').innerHTML = `
        <div class="flex items-center justify-between">
            <button data-act="voltar" class="text-slate-200 hover:text-white font-semibold py-2 pr-3 -ml-1"><i class="fa-solid fa-arrow-left mr-1.5"></i>Voltar</button>
        </div>

        <div>
            <p class="text-xs font-bold text-ouro uppercase tracking-wide"><i class="fa-solid fa-chart-line mr-1"></i>Análise anualizada e previsão</p>
            <h2 class="text-2xl font-bold text-white leading-tight mt-1">${esc(it.p)}${detalhe ? ` <span class="font-semibold text-slate-300">${esc(detalhe)}</span>` : ''}</h2>
            <p class="text-sm text-slate-400 mt-1">${esc(sub)} · ${esc(nomeCurto(merc))}</p>
        </div>

        ${pracas.length > 1 ? `<div class="flex flex-wrap gap-1.5 bg-mata-900 border border-mata-800 rounded-2xl p-1.5" role="group" aria-label="Praça da análise">
            ${pracas.map(x => `<button data-act="anual-merc" data-arg="${x.id}" aria-pressed="${x.id === mid}" class="flex-1 basis-[22%] py-2.5 rounded-xl text-sm font-semibold transition-colors ${x.id === mid ? 'bg-ouro text-mata-950' : 'text-slate-300 hover:bg-mata-800'}">${x.id}</button>`).join('')}
        </div>` : ''}

        <div class="${box}">
            ${Graf.anual(A, ANUAL.ocultos)}
            <p class="text-xs text-slate-500 mt-2">Médias semanais do preço comum. Toque nos anos para mostrar ou esconder. Tracejado: previsão; faixa: menor e maior caso dos anos anteriores. ${A.proj.some(p => p.w > 51) ? 'Meses em amarelo: começo do ano seguinte.' : ''}</p>
        </div>

        <div class="${box}">
            <h3 class="font-bold text-white mb-1">Previsão de preço</h3>
            ${A.proj.length ? `
            <p class="text-xs text-slate-400 mb-2">A partir de ${R$(A.p0)} (${dataCurta(A.ult.d)}), repetindo o comportamento de ${A.usados.join(', ')} nas mesmas semanas.</p>
            <table class="w-full text-[15px]">
                <tr><th></th><th class="text-right text-xs text-slate-400 font-semibold pb-1">Previsto</th><th class="text-right text-xs text-slate-400 font-semibold pb-1 pl-2">Faixa</th></tr>
                ${linhaProj('Em 4 semanas', p4)}${linhaProj('Em 8 semanas', p8)}${linhaProj('Em 12 semanas', p12)}
            </table>
            <p class="text-[11px] text-slate-500 mt-2">Estimativa estatística a partir dos anos anteriores. Não considera clima, safra ou mercado deste ano; use como referência, não como garantia.</p>`
            : `<p class="text-sm text-slate-400">Histórico insuficiente para prever: são necessários pelo menos 2 anos anteriores com cotação nas mesmas semanas${A.anos.length < 2 ? ` (esta praça tem dados desde ${A.anos[A.anos.length - 1] || A.atual})` : ''}.</p>`}
        </div>

        <div class="${box} overflow-x-auto">
            <h3 class="font-bold text-white mb-2">Comparação entre os anos</h3>
            <table class="w-full text-sm">
                <tr class="text-xs text-slate-400"><th class="text-left font-semibold pb-1">Ano</th><th class="text-right font-semibold">Nesta semana</th><th class="text-right font-semibold">Média</th><th class="text-right font-semibold">Mín.</th><th class="text-right font-semibold">Máx.</th></tr>
                ${A.resumo.map((r, k) => `<tr class="border-t border-mata-800" style="opacity:${opAno(k)}">
                    <td class="py-2 font-bold text-white whitespace-nowrap"><span class="inline-block w-2.5 h-2.5 rounded-full mr-1.5" style="background:${corAno(k)}"></span>${r.a}${r.parcial ? '<span class="text-[10px] text-slate-500 font-semibold ml-1">até agora</span>' : ''}</td>
                    <td class="text-right font-bold text-white">${r.nesta != null ? preco(r.nesta) : '–'}</td>
                    <td class="text-right text-slate-200">${preco(r.md)}</td>
                    <td class="text-right text-slate-200">${preco(r.mn)}</td>
                    <td class="text-right text-slate-200">${preco(r.mx)}</td></tr>`).join('')}
            </table>
        </div>`;
    window.scrollTo(0, y);
}

function abrirAnual() {
    det.anual = { mid: det.mercs[0] };
    history.pushState({ det: det.key, anual: true }, '');
    renderAnual();
    window.scrollTo(0, 0);
}
function fecharAnual() {
    det.anual = null;
    renderDetalhe();
    window.scrollTo(0, 0);
}
function alternarAnoAnual(a) {
    a = +a;
    if (ANUAL.ocultos.has(a)) ANUAL.ocultos.delete(a); else ANUAL.ocultos.add(a);
    renderAnual();
}
