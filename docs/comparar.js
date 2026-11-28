/* COTA CEA$A — Comparação histórica entre praças (até 5)
 * Abre a partir do detalhe de um produto. Uma linha por praça com o preço comum ao longo do tempo:
 * média semanal (período de até 1 ano) ou mensal (períodos maiores), para as linhas ficarem legíveis.
 * Abaixo, um quadro por praça com média, menor, maior e última cotação do período.
 */
const COMP = {
    MAX: 5,
    PERIODOS: [
        { rot: '1 ano', dias: 365 },
        { rot: '2 anos', dias: 730 },
        { rot: '5 anos', dias: 1826 },
        { rot: 'Tudo', dias: 0 }
    ]
};
const MES_ABR = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
const MES_NOME = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];

const pracasDoItem = (it) => dados.mercados.map(m => m.id).filter(id => it.m[id]);

// segunda-feira da semana de uma data ISO
function inicioSemanaISO(d) {
    const t = new Date(d + 'T12:00:00');
    t.setDate(t.getDate() - (t.getDay() + 6) % 7);
    return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
}
// [{d, v}] diário -> média por semana ou por mês ({d: início do período, v: média})
function agregarComp(pts, porMes) {
    const acc = new Map();
    for (const { d, v } of pts) {
        const k = porMes ? d.slice(0, 7) + '-01' : inicioSemanaISO(d);
        const a = acc.get(k) || [0, 0];
        a[0] += v; a[1]++;
        acc.set(k, a);
    }
    return [...acc.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([d, [s, n]]) => ({ d, v: s / n }));
}

function abrirComparar() {
    const it = itemPorChave(det.key), todas = pracasDoItem(it);
    let ids = det.mercs.filter(id => todas.includes(id)).slice(0, COMP.MAX);
    if (ids.length < 2) ids = [...new Set([...ids, ...todas])].slice(0, COMP.MAX);
    det.comp = { ids, dias: 365, aviso: '' };
    Graf.zoomH = null;
    history.pushState({ det: det.key, comp: true }, '');
    renderComparar();
    window.scrollTo(0, 0);
}
function fecharComparar() {
    det.comp = null;
    Graf.zoomH = null;
    Graf.fmtCurta = Graf.fmtLonga = null;
    renderDetalhe();
    window.scrollTo(0, 0);
}
function alternarPracaComp(id) {
    const c = det.comp, on = c.ids.includes(id);
    c.aviso = '';
    if (on) {
        if (c.ids.length === 1) return;
        c.ids = c.ids.filter(x => x !== id);
    } else if (c.ids.length >= COMP.MAX) {
        c.aviso = `Máximo de ${COMP.MAX} praças. Desmarque uma para incluir outra.`;
        return renderComparar();
    } else {
        c.ids = [...c.ids, id];
    }
    c.ids = dados.mercados.map(m => m.id).filter(x => c.ids.includes(x));
    Graf.zoomH = null;
    renderComparar();
}
function periodoComp(dias) {
    det.comp.dias = +dias;
    det.comp.aviso = '';
    Graf.zoomH = null;
    renderComparar();
}

function renderComparar() {
    const y = window.scrollY;
    const c = det.comp, it = itemPorChave(det.key), todas = pracasDoItem(it);
    const fim = c.ids.map(id => { const p = serie(it, id); return p[p.length - 1].d; }).sort().pop();
    const ini = c.dias ? somarDias(fim, -c.dias) : '0000-00-00';
    const porMes = !c.dias || c.dias > 365;
    const series = c.ids.map(id => {
        const bruto = serie(it, id).filter(p => p.d >= ini);
        return { id, cor: corMercado(id), bruto, pts: agregarComp(bruto, porMes) };
    }).filter(s => s.pts.length);
    // rótulos do gráfico: mês/ano (médias mensais) ou "semana de dd/mm/aaaa"
    Graf.fmtCurta = porMes ? (d => `${MES_ABR[+d.slice(5, 7) - 1]}/${d.slice(2, 4)}`) : null;
    Graf.fmtLonga = porMes ? (d => `Média de ${MES_NOME[+d.slice(5, 7) - 1]} de ${d.slice(0, 4)}`) : (d => `Semana de ${dataBR(d)}`);

    const detalhe = it.d.replace(/\bLonga Vida\b/g, 'LV');
    const sub = [UNIDADE[it.u], it.e !== 'kg' ? it.e : ''].filter(Boolean).join(' · ');
    const box = 'bg-mata-900 border border-mata-800 rounded-2xl p-4';
    const est = series.map(s => {
        const v = s.bruto.map(p => p.v), u = s.bruto[s.bruto.length - 1];
        return { id: s.id, cor: s.cor, md: v.reduce((a, b) => a + b, 0) / v.length, mn: Math.min(...v), mx: Math.max(...v), n: v.length, u };
    });
    const maisBarata = est.length > 1 ? est.reduce((a, b) => (b.md < a.md ? b : a)) : null;
    const per = COMP.PERIODOS.find(p => p.dias === c.dias) || COMP.PERIODOS[0];

    el('vista-detalhe').innerHTML = `
        <div class="flex items-center justify-between">
            <button data-act="voltar" class="text-slate-200 hover:text-white font-semibold py-2 pr-3 -ml-1"><i class="fa-solid fa-arrow-left mr-1.5"></i>Voltar</button>
        </div>

        <div>
            <p class="text-xs font-bold text-verde-claro uppercase tracking-wide"><i class="fa-solid fa-scale-balanced mr-1"></i>Comparação entre praças</p>
            <h2 class="text-2xl font-bold text-white leading-tight mt-1">${esc(it.p)}${detalhe ? ` <span class="font-semibold text-slate-300">${esc(detalhe)}</span>` : ''}</h2>
            <p class="text-sm text-slate-400 mt-1">${esc(sub)} · preço comum</p>
        </div>

        <div>
            <div class="flex flex-wrap gap-1.5 bg-mata-900 border border-mata-800 rounded-2xl p-1.5" role="group" aria-label="Praças comparadas">
                ${todas.map(id => {
                    const on = c.ids.includes(id);
                    return `<button data-act="comp-merc" data-arg="${id}" aria-pressed="${on}" title="${esc(mercadoPor(id).nome)}" class="flex-1 basis-[22%] py-2.5 rounded-xl text-sm font-semibold transition-colors flex items-center justify-center gap-1.5 ${on ? 'bg-ouro text-mata-950' : 'text-slate-300 hover:bg-mata-800'}"><span class="w-2.5 h-2.5 rounded-full" style="background:${corMercado(id)}"></span>${id}</button>`;
                }).join('')}
            </div>
            <p class="text-xs ${c.aviso ? 'text-rose-400 font-semibold' : 'text-slate-500'} mt-1.5 px-1">${c.aviso || `Toque nas praças para comparar (até ${COMP.MAX}). Marcadas: ${c.ids.length}.`}</p>
        </div>

        <div class="flex flex-wrap gap-1.5" role="group" aria-label="Período da comparação">
            ${COMP.PERIODOS.map(p => `<button data-act="comp-per" data-arg="${p.dias}" aria-pressed="${p === per}" class="flex-none px-3 py-1.5 rounded-full text-xs font-semibold border whitespace-nowrap transition-colors ${p === per ? 'bg-ouro text-mata-950 border-ouro' : 'bg-mata-900 text-slate-300 border-mata-700 hover:border-verde/60'}">${p.rot}</button>`).join('')}
        </div>

        <div class="${box}">
            ${series.length ? Graf.historico('multi', series.map(({ id, cor, pts }) => ({ id, cor, pts }))) : '<p class="text-sm text-slate-400">Sem cotações neste período.</p>'}
            <p class="text-xs text-slate-500 mt-1">${porMes ? 'Média mensal' : 'Média semanal'} do preço comum de cada praça. Passe o cursor ou deslize o dedo no gráfico para ver os valores.</p>
        </div>

        <div class="${box}">
            <h3 class="font-bold text-white mb-2">Resumo do período (${per.rot.toLowerCase()})</h3>
            <table class="w-full text-sm">
                <tr class="text-xs text-slate-400"><th class="text-left font-semibold pb-1">Praça</th><th class="text-right font-semibold">Média</th><th class="text-right font-semibold">Menor</th><th class="text-right font-semibold">Maior</th><th class="text-right font-semibold">Última</th></tr>
                ${est.map(e => `<tr class="border-t border-mata-800">
                    <td class="py-2 font-bold text-white whitespace-nowrap"><span class="inline-block w-2.5 h-2.5 rounded-full mr-1.5" style="background:${e.cor}"></span>${e.id}</td>
                    <td class="text-right font-bold text-white">${preco(e.md)}${maisBarata && maisBarata.id === e.id ? ' <i class="fa-solid fa-arrow-down text-verde-claro text-[10px]" title="Menor média"></i>' : ''}</td>
                    <td class="text-right text-slate-200">${preco(e.mn)}</td>
                    <td class="text-right text-slate-200">${preco(e.mx)}</td>
                    <td class="text-right text-slate-200 whitespace-nowrap">${preco(e.u.v)}<span class="block text-[10px] text-slate-500">${dataCurta(e.u.d)}</span></td></tr>`).join('')}
            </table>
            ${maisBarata ? `<p class="text-xs text-slate-400 mt-2"><i class="fa-solid fa-arrow-down text-verde-claro mr-1"></i>Menor preço médio no período: <b class="text-white">${esc(nomeCurto(mercadoPor(maisBarata.id)))}</b>${est.filter(e => e.id !== maisBarata.id).map(e => ` · ${e.id} ${e.md > maisBarata.md ? '+' : ''}${((e.md / maisBarata.md - 1) * 100).toFixed(0)}%`).join('')}</p>` : ''}
        </div>`;
    window.scrollTo(0, y);
}
